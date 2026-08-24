"""storage/tasks.py —— 异步生图任务管理与轮询。

当前生图由 config.image_provider 决定承接方（mock | dashscope | api2img | zhipu）：
- Mock 模式（默认）：立即生成占位效果图 URL，任务直接置为 done。
- dashscope（通义万相）：异步提交返回 task_id，由 /tasks 轮询结果。
- api2img（第三方中转商，OpenAI 兼容）：同步调用 /v1/images/generations 返回 base64/url，
  落盘后由本服务托管 /generated/{id}.png URL，任务直接置为 done。
- zhipu（智谱 CogView，cogview-3-flash 免费）：同步调用 {base}/images/generations，
  返回图片直链，下载落盘到 /generated/{id}.png，任务直接置为 done。
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import socket
import uuid
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from backend.config import settings
from backend.storage.db import get_conn, transaction

logger = logging.getLogger("tasks")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ensure_generated_dir() -> Path:
    d = Path(settings.generated_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_mock_placeholder(task_id: str) -> str:
    size = 256
    rows = []
    for y in range(size):
        r = int(244 - 42 * y / size)
        g = int(235 - 44 * y / size)
        b = int(222 - 40 * y / size)
        rows.append(b"\x00" + bytes([r, g, b]) * size)
    raw = b"".join(rows)

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return len(data).to_bytes(4, "big") + c + zlib.crc32(c).to_bytes(4, "big")

    ihdr = b"".join([size.to_bytes(4, "big"), size.to_bytes(4, "big"), b"\x08\x02\x00\x00\x00"])
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
    data = base64.b64decode(b64)
    path = _ensure_generated_dir() / f"{task_id}.{ext}"
    path.write_bytes(data)
    return f"/generated/{path.name}"


def _is_safe_image_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    allowed = settings.image_download_hosts
    if not any(host == h or host.endswith("." + h) for h in allowed):
        return False
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except Exception:
        if any(host == h or host.endswith("." + h) for h in settings.image_download_allowed_hosts):
            return True
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return False
    return True


def _safe_get(url: str, max_redirects: int = 3) -> httpx.Response:
    current = url
    for _ in range(max_redirects + 1):
        resp = httpx.get(current, timeout=60.0, follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location")
            if not loc:
                resp.raise_for_status()
                return resp
            if not loc.startswith("http"):
                loc = urljoin(current, loc)
            if not _is_safe_image_url(loc):
                raise RuntimeError(f"Unsafe redirect: {loc}")
            current = loc
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("Too many redirects")


def _detect_image_ext(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


def _download_image_to_local(url: str, task_id: str) -> str:
    if not _is_safe_image_url(url):
        raise RuntimeError(f"Unsafe image URL: {url}")
    try:
        resp = _safe_get(url)
    except Exception as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc
    data = resp.content
    ext = _detect_image_ext(data)
    if ext is None:
        ct = resp.headers.get("content-type", "").lower()
        if "jpeg" in ct or "jpg" in ct:
            ext = "jpg"
        elif "png" in ct:
            ext = "png"
        elif "webp" in ct:
            ext = "webp"
        else:
            raise RuntimeError(f"Unsupported image format (ct={ct or 'empty'})")
    path = _ensure_generated_dir() / f"{task_id}.{ext}"
    path.write_bytes(resp.content)
    return f"/generated/{path.name}"


_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks"


def _image_client_submit(prompt: str) -> str:
    headers = {"Authorization": f"Bearer {settings.image_api_key}", "Content-Type": "application/json", "X-DashScope-Async": "enable"}
    payload = {"model": settings.image_model, "input": {"prompt": prompt}, "parameters": {"size": "1024*1024", "n": 1}}
    try:
        resp = httpx.post(settings.image_base_url, headers=headers, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Wanxiang submit failed: {exc}") from exc
    task_id = data.get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"Wanxiang no task_id: {data}")
    return task_id


def _image_client_poll(task_id: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {settings.image_api_key}"}
    try:
        resp = httpx.get(f"{_DASHSCOPE_TASK_URL}/{task_id}", headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Wanxiang poll failed: {exc}") from exc
    status = data.get("output", {}).get("task_status", "")
    if status == "SUCCEEDED":
        results = data.get("output", {}).get("results", [])
        url = results[0]["url"] if results else ""
        return "done", url
    if status in ("FAILED", "UNKNOWN"):
        return "failed", ""
    return "pending", ""


def _image_client_submit_api2img(prompt: str, task_id: str) -> str:
    base = settings.api2img_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    endpoint = f"{base}/images/generations"
    headers = {"Authorization": f"Bearer {settings.api2img_api_key}", "Content-Type": "application/json"}
    payload = {"model": settings.api2img_model, "prompt": prompt, "n": 1, "size": settings.api2img_size, "quality": settings.api2img_quality, "output_format": settings.api2img_output_format, "response_format": "b64_json"}
    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:
        raise RuntimeError(f"api2img submit failed: {exc}") from exc
    items = result.get("data") or []
    if not items:
        raise RuntimeError(f"api2img no image data: {result}")
    item = items[0]
    if item.get("b64_json"):
        ext = settings.api2img_output_format or "png"
        return _save_base64_image(item["b64_json"], task_id, ext)
    if item.get("url"):
        return _download_image_to_local(item["url"], task_id)
    raise RuntimeError("api2img returned neither b64_json nor url")


def _image_client_submit_zhipu(prompt: str, task_id: str, size: str | None = None) -> str:
    base = settings.zhipu_base_url.rstrip("/")
    endpoint = f"{base}/images/generations"
    headers = {"Authorization": f"Bearer {settings.zhipu_api_key}", "Content-Type": "application/json"}
    payload = {"model": settings.zhipu_model, "prompt": prompt, "size": size or settings.zhipu_size}
    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Zhipu submit failed: {exc}") from exc
    items = result.get("data") or []
    if not items:
        raise RuntimeError(f"Zhipu no image data: {result}")
    item = items[0]
    url = item.get("url") or item.get("file_url")
    if url:
        return _download_image_to_local(url, task_id)
    raise RuntimeError("Zhipu returned neither url nor file_url")


def create_image_task(prompt: str) -> str:
    if settings.image_enabled:
        provider = settings.image_provider
        if provider == "dashscope":
            task_id = _image_client_submit(prompt)
            status = "pending"
            result_url = ""
        elif provider == "api2img":
            task_id = uuid.uuid4().hex
            try:
                result_url = _image_client_submit_api2img(prompt, task_id)
            except RuntimeError:
                task_id = uuid.uuid4().hex
                status = "done"
                result_url = _write_mock_placeholder(task_id)
                with transaction() as c:
                    c.execute("INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)", (task_id, status, prompt, result_url, _now()))
                return task_id
            status = "done"
        elif provider == "zhipu":
            task_id = uuid.uuid4().hex
            try:
                result_url = _image_client_submit_zhipu(prompt, task_id)
            except RuntimeError:
                task_id = uuid.uuid4().hex
                status = "done"
                result_url = _write_mock_placeholder(task_id)
                with transaction() as c:
                    c.execute("INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)", (task_id, status, prompt, result_url, _now()))
                return task_id
            status = "done"
        else:
            task_id = uuid.uuid4().hex
            status = "done"
            result_url = _write_mock_placeholder(task_id)
    else:
        task_id = uuid.uuid4().hex
        status = "done"
        result_url = _write_mock_placeholder(task_id)
    with transaction() as c:
        c.execute("INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)", (task_id, status, prompt, result_url, _now()))
    return task_id


def get_image_task(task_id: str) -> dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT task_id, status, result_url FROM image_tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return {"task_id": task_id, "status": "not_found", "result_url": ""}
    if settings.image_enabled and row["status"] in ("pending", "running"):
        try:
            new_status, url = _image_client_poll(task_id)
        except RuntimeError:
            return {"task_id": task_id, "status": row["status"], "result_url": ""}
        if new_status in ("done", "failed"):
            with transaction() as c:
                c.execute("UPDATE image_tasks SET status=?, result_url=? WHERE task_id=?", (new_status, url, task_id))
        return {"task_id": task_id, "status": new_status, "result_url": url}
    return {"task_id": row["task_id"], "status": row["status"], "result_url": row["result_url"] or ""}
