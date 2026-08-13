"""storage/tasks.py —— 异步生图任务管理与轮询。

当前生图由 config.image_provider 决定承接方（mock | dashscope | api2img | zhipu）：
- Mock 模式（默认）：立即生成占位效果图 URL，任务直接置为 done。
- dashscope（通义万相）：异步提交返回 task_id，由 /tasks 轮询结果。
- api2img（第三方中转商，OpenAI 兼容）：同步调用 /v1/images/generations 返回 base64/url，
  落盘后由本服务托管 /generated/{id}.png URL，任务直接置为 done。
- zhipu（智谱 CogView，cogview-3-flash 免费）：同步调用 {base}/images/generations，
  返回图片直链，下载落盘到 /generated/{id}.png，任务直接置为 done。

对外：create_image_task(prompt) -> task_id；get_image_task(task_id) -> {status, result_url}。
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import uuid
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config import settings
from storage.db import get_conn, transaction

logger = logging.getLogger("tasks")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ensure_generated_dir() -> Path:
    """确保中转商 base64 落盘目录存在（data/generated）。"""
    d = Path(settings.generated_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_mock_placeholder(task_id: str) -> str:
    """生成一张本地占位 PNG（纯 Python zlib，无第三方依赖），返回 /generated/{id}.png。

    替代 example.com 占位 URL：example.com 是保留域名无法渲染，前端 <image> 拿到的是
    本服务托管地址 /generated/{id}.png，Mock / 出图失败降级时也能正常显示。
    """
    size = 256
    # 竖向渐变（浅粉 → 米白），256 色 RGB，无隔行
    rows = []
    for y in range(size):
        r = int(255 - 90 * y / size)
        g = int(228 - 60 * y / size)
        b = int(228 - 60 * y / size)
        rows.append(b"\x00" + bytes([r, g, b]) * size)
    raw = b"".join(rows)

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return len(data).to_bytes(4, "big") + c + zlib.crc32(c).to_bytes(4, "big")

    ihdr = b"".join(
        [
            size.to_bytes(4, "big"),
            size.to_bytes(4, "big"),
            b"\x08\x02\x00\x00\x00",  # 8-bit, RGB, 无隔行
        ]
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path = _ensure_generated_dir() / f"{task_id}.png"
    path.write_bytes(png)
    return f"/generated/{path.name}"


def _save_base64_image(b64: str, task_id: str, ext: str = "png") -> str:
    """把中转商返回的 base64 图片解码落盘，返回本地可访问 URL（维持 result_url 契约）。

    Args:
        b64: base64 编码的图片数据。
        task_id: 本地生图任务 id（用作文件名，保证与 DB 记录一致）。
        ext: 图片扩展名（png/jpeg/webp）。

    Returns:
        /generated/{task_id}.{ext} 形式的本地 URL。
    """
    data = base64.b64decode(b64)
    path = _ensure_generated_dir() / f"{task_id}.{ext}"
    path.write_bytes(data)
    return f"/generated/{path.name}"


def _download_image_to_local(url: str, task_id: str) -> str:
    """把中转商直接返回的图片 URL 下载到本地，统一返回本地 URL。

    部分中转商（如 cc-vibe）生图接口返回的是图片直链而非 base64。为维持
    result_url 契约（本地稳定可托管，不依赖外部临时链接时效/访问限制），
    这里把远程图片拉取到 data/generated/{task_id}.{ext}。

    Args:
        url: 中转商返回的图片直链。
        task_id: 本地生图任务 id，用作落盘文件名。

    Returns:
        /generated/{task_id}.{ext} 形式的本地 URL。

    Raises:
        RuntimeError: 下载失败或返回非图片时抛出。
    """
    try:
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tasks] api2img 图片下载失败")
        raise RuntimeError(f"api2img 图片下载失败: {exc}") from exc
    ct = resp.headers.get("content-type", "")
    if "png" in ct:
        ext = "png"
    elif "jpeg" in ct or "jpg" in ct:
        ext = "jpg"
    elif "webp" in ct:
        ext = "webp"
    else:
        ext = (mimetypes.guess_extension(ct) or ".png").lstrip(".")
    path = _ensure_generated_dir() / f"{task_id}.{ext}"
    path.write_bytes(resp.content)
    logger.info("[tasks] api2img 远程图片已落盘 %s (%d bytes)", path.name, len(resp.content))
    return f"/generated/{path.name}"


_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks"


def _image_client_submit(prompt: str) -> str:
    """调用通义万相异步文生图接口，返回万相 task_id。

    真实模式（image_provider=dashscope 且配置了 key）才调用。提交后由
    _image_client_poll 轮询最终结果 URL。

    Args:
        prompt: 文生图提示词。

    Returns:
        万相侧 task_id（直接作为本地 task_id 落库）。

    Raises:
        RuntimeError: 提交失败（鉴权/网络/API 错误）时抛出。
    """
    headers = {
        "Authorization": f"Bearer {settings.image_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": settings.image_model,  # "wanx-v1"
        "input": {"prompt": prompt},
        "parameters": {"size": "1024*1024", "n": 1},
    }
    try:
        resp = httpx.post(settings.image_base_url, headers=headers, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tasks] 万相提交失败")
        raise RuntimeError(f"万相生图提交失败: {exc}") from exc
    task_id = data.get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"万相未返回 task_id: {data}")
    logger.info("[tasks] 万相任务已提交 task_id=%s", task_id)
    return task_id


def _image_client_poll(task_id: str) -> tuple[str, str]:
    """轮询万相任务结果。

    Args:
        task_id: 万相 task_id。

    Returns:
        (status, result_url)，status 为本地语义的 pending/done/failed。
    """
    headers = {"Authorization": f"Bearer {settings.image_api_key}"}
    try:
        resp = httpx.get(f"{_DASHSCOPE_TASK_URL}/{task_id}", headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tasks] 万相轮询失败")
        raise RuntimeError(f"万相轮询失败: {exc}") from exc
    status = data.get("output", {}).get("task_status", "")
    if status == "SUCCEEDED":
        results = data.get("output", {}).get("results", [])
        url = results[0]["url"] if results else ""
        return "done", url
    if status in ("FAILED", "UNKNOWN"):
        return "failed", ""
    return "pending", ""  # PENDING / RUNNING


def _image_client_submit_api2img(prompt: str, task_id: str) -> str:
    """调用第三方中转商（OpenAI 兼容 /images/generations）同步生图。

    与 api2img-skill 的 cli 行为一致：POST {base}/v1/images/generations，Bearer 鉴权，
    返回 data[].b64_json。本函数解码后落盘，返回本地可访问 URL（任务置为 done）。

    Args:
        prompt: 文生图提示词。
        task_id: 本地生图任务 id，确保落盘文件名与 DB 记录一致。

    Returns:
        本地图片 URL（/generated/{task_id}.png）。

    Raises:
        RuntimeError: 提交失败或返回结构异常时抛出。
    """
    base = settings.api2img_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    endpoint = f"{base}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.api2img_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.api2img_model,
        "prompt": prompt,
        "n": 1,
        "size": settings.api2img_size,
        "quality": settings.api2img_quality,
        "output_format": settings.api2img_output_format,
        "response_format": "b64_json",
    }
    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tasks] api2img 提交失败")
        raise RuntimeError(f"api2img 生图提交失败: {exc}") from exc

    items = result.get("data") or []
    if not items:
        raise RuntimeError(f"api2img 未返回图片数据: {result}")
    item = items[0]
    if item.get("b64_json"):
        ext = settings.api2img_output_format or "png"
        return _save_base64_image(item["b64_json"], task_id, ext)
    if item.get("url"):
        # 中转商直接返回图片直链（cc-vibe 行为）：下载到本地，统一返回本地 URL
        return _download_image_to_local(item["url"], task_id)
    raise RuntimeError("api2img 返回中既无 b64_json 也无 url")


def _image_client_submit_zhipu(prompt: str, task_id: str) -> str:
    """调用智谱 AI 文生图接口（CogView，cogview-3-flash 免费）。

    智谱图像生成 API 路径为 {base}/images/generations（**不含 /v1**，与 api2img
    网关不同）。请求体仅需 model/prompt/size；响应 data[].url 为图片直链（30 天有效）。
    本函数把直链下载到本地，统一返回 /generated/{task_id}.{ext}，维持 result_url 契约。

    Args:
        prompt: 文生图提示词。
        task_id: 本地生图任务 id，用作落盘文件名。

    Returns:
        本地图片 URL（/generated/{task_id}.{ext}）。

    Raises:
        RuntimeError: 提交失败或返回结构异常时抛出。
    """
    base = settings.zhipu_base_url.rstrip("/")
    endpoint = f"{base}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.zhipu_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.zhipu_model,  # "cogview-3-flash"
        "prompt": prompt,
        "size": settings.zhipu_size,
    }
    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tasks] 智谱生图提交失败")
        raise RuntimeError(f"智谱生图提交失败: {exc}") from exc
    items = result.get("data") or []
    if not items:
        raise RuntimeError(f"智谱未返回图片数据: {result}")
    item = items[0]
    url = item.get("url") or item.get("file_url")
    if url:
        return _download_image_to_local(url, task_id)
    raise RuntimeError("智谱返回中既无 url 也无 file_url")


def create_image_task(prompt: str) -> str:
    """提交生图任务，立即返回 task_id。

    真实模式返回万相 task_id（落库时即该 id），状态 pending；
    Mock 模式返回本地随机 id，状态直接 done 并带占位 URL。
    """
    if settings.image_enabled:
        provider = settings.image_provider
        if provider == "dashscope":
            task_id = _image_client_submit(prompt)
            status = "pending"
            result_url = ""
        elif provider == "api2img":
            # 中转商同步出图，落盘后直接 done，无需轮询
            task_id = uuid.uuid4().hex
            try:
                result_url = _image_client_submit_api2img(prompt, task_id)
            except RuntimeError:
                # 出图失败时退化为本地占位，保证对话流程不中断且前端可渲染
                task_id = uuid.uuid4().hex
                status = "done"
                result_url = _write_mock_placeholder(task_id)
                logger.warning("[tasks] api2img 出图失败，降级为本地占位图")
                with transaction() as c:
                    c.execute(
                        "INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)",
                        (task_id, status, prompt, result_url, _now()),
                    )
                return task_id
            status = "done"
        elif provider == "zhipu":
            # 智谱同步出图，下载直链落盘后直接 done，无需轮询
            task_id = uuid.uuid4().hex
            try:
                result_url = _image_client_submit_zhipu(prompt, task_id)
            except RuntimeError:
                task_id = uuid.uuid4().hex
                status = "done"
                result_url = _write_mock_placeholder(task_id)
                logger.warning("[tasks] 智谱出图失败，降级为本地占位图")
                with transaction() as c:
                    c.execute(
                        "INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)",
                        (task_id, status, prompt, result_url, _now()),
                    )
                return task_id
            status = "done"
        else:
            # 未知 provider → 兜底本地占位
            task_id = uuid.uuid4().hex
            status = "done"
            result_url = _write_mock_placeholder(task_id)
    else:
        task_id = uuid.uuid4().hex
        status = "done"
        result_url = _write_mock_placeholder(task_id)
    with transaction() as c:
        c.execute(
            "INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)",
            (task_id, status, prompt, result_url, _now()),
        )
    logger.info("[tasks] 生图任务 %s 提交，状态=%s", task_id, status)
    return task_id


def get_image_task(task_id: str) -> dict[str, Any]:
    """轮询任务结果。

    真实模式且任务未完成时，实时回源万相轮询一次并更新本地状态；
    Mock 模式直接返回落库结果。
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT task_id, status, result_url FROM image_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if not row:
        return {"task_id": task_id, "status": "not_found", "result_url": ""}

    # 真实模式且尚未完成 → 回源万相轮询一次
    if settings.image_enabled and row["status"] in ("pending", "running"):
        try:
            new_status, url = _image_client_poll(task_id)
        except RuntimeError:
            return {"task_id": task_id, "status": row["status"], "result_url": ""}
        if new_status in ("done", "failed"):
            with transaction() as c:
                c.execute(
                    "UPDATE image_tasks SET status=?, result_url=? WHERE task_id=?",
                    (new_status, url, task_id),
                )
        return {"task_id": task_id, "status": new_status, "result_url": url}

    return {"task_id": row["task_id"], "status": row["status"], "result_url": row["result_url"] or ""}
