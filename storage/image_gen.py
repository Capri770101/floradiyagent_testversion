"""AI 生图供应商适配。按 config.image_provider 切换：

- mock     : 返回占位图 URL（本地测试用）；
- api2img  : 低价中转商的 OpenAI 兼容 /images/generations 接口
              （参考 github.com/MrVoler/api2img-skill，成本约 0.01 元/张）；
- dashscope: 通义万相真实施图（创建异步任务 + 轮询）；
- zhipu    : 智谱 CogView-3-Flash 生图（免费，共享额度易 429，内置退避重试）。

当前默认使用智谱 cogview-3-flash 免费生图；未配置密钥时回退 mock，避免本地链路不可用。
"""
import base64
import logging
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import httpx

from config import Config

logger = logging.getLogger(__name__)

_CREATE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"


def build_image_gen(config: Config) -> Callable[[str], str]:
    """返回生图回调（入参方案文本，出参效果图 URL），供 TaskManager 后台线程调用。"""
    if config.image_provider in ("api2img", "openai-img"):
        return lambda plan_text: _openai_compatible_generate(config, plan_text)
    if config.image_provider in ("dashscope", "tongyi"):
        return lambda plan_text: _dashscope_generate(config, plan_text)
    if config.image_provider in ("zhipu", "cogview"):
        return lambda plan_text: _zhipu_generate(config, plan_text)
    return lambda plan_text: _mock_generate(plan_text)


def _mock_generate(plan_text: str) -> str:
    """mock 生图：按输入文本派生一个稳定的占位 URL。"""
    import hashlib
    digest = hashlib.md5((plan_text or "flower").encode("utf-8")).hexdigest()[:12]
    return f"https://mock.flower/gen/{digest}.png"


def _openai_compatible_generate(config: Config, plan_text: str,
                                http: Optional[httpx.Client] = None) -> str:
    """api2img 中转商生图：OpenAI 兼容 POST {base}/images/generations。

    返回 data[0].url（中转商直链）；若为 b64_json 则本地落盘后以
    {image_result_base}/images/xxx.png 对外提供。http 参数供测试注入 MockTransport。
    """
    if not config.image_openai_base_url or not config.image_openai_api_key:
        raise RuntimeError(
            "IMAGE_PROVIDER=api2img 但未配置 IMAGE_OPENAI_BASE_URL / IMAGE_OPENAI_API_KEY"
            "（见 .env.example，需向中转商申请）")
    client = http
    own_client = http is None
    if own_client:
        client = httpx.Client(timeout=120)
    try:
        url = f"{config.image_openai_base_url.rstrip('/')}/images/generations"
        body = {"model": config.image_openai_model, "prompt": plan_text,
                "size": config.image_size, "n": 1}
        resp = client.post(url, json=body,
                           headers={"Authorization": f"Bearer {config.image_openai_api_key}"})
        resp.raise_for_status()
        items = (resp.json() or {}).get("data") or []
        if not items:
            raise RuntimeError(f"生图接口无返回数据: {resp.text[:200]}")
        item = items[0]
        if item.get("url"):
            logger.info("api2img 生图完成（中转直链）")
            return item["url"]
        if item.get("b64_json"):
            result = _save_b64_image(config.image_cache_dir, item["b64_json"])
            logger.info("api2img 生图完成（b64 落盘）: %s", result)
            return f"{config.image_result_base.rstrip('/')}/images/{result.name}"
        raise RuntimeError(f"生图接口返回结构未知: {resp.text[:200]}")
    finally:
        if own_client:
            client.close()


def _save_b64_image(cache_dir: Path, b64: str) -> Path:
    """base64 图片落盘到缓存目录（api.py 已将该目录静态挂载到 /images）。"""
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        raise RuntimeError(f"生图结果 base64 解码失败: {exc}") from exc
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = f"agent_img_{uuid.uuid4().hex[:10]}.png"
    path = cache_dir / name
    path.write_bytes(raw)
    return path


def _zhipu_generate(config: Config, plan_text: str,
                    http: Optional[httpx.Client] = None) -> str:
    """智谱 CogView-3-Flash 生图：POST {base}/images/generations。

    免费模型共享额度，命中 429 时按 15s*attempt 退避重试。
    成功响应形如 {"data": [{"url": "https://..."}]}，直链透传。
    http 参数供测试注入 MockTransport。
    """
    if not config.image_zhipu_api_key:
        raise RuntimeError(
            "IMAGE_PROVIDER=zhipu 但未配置 IMAGE_ZHIPU_API_KEY"
            "（智谱开放平台申请：https://open.bigmodel.cn）")
    client = http
    own_client = http is None
    if own_client:
        client = httpx.Client(timeout=180)
    try:
        url = f"{config.image_zhipu_base_url.rstrip('/')}/images/generations"
        body = {"model": config.image_zhipu_model, "prompt": plan_text}
        last_error = None
        for attempt in range(1, config.image_zhipu_max_retries + 1):
            resp = client.post(
                url, json=body,
                headers={"Authorization": f"Bearer {config.image_zhipu_api_key}"})
            if resp.status_code == 429:
                last_error = RuntimeError(f"智谱生图限流(429): {resp.text[:160]}")
                wait = config.image_zhipu_retry_base * attempt
                logger.warning("智谱 429 限流，第 %s/%s 次，%.0fs 后重试",
                               attempt, config.image_zhipu_max_retries, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            items = (resp.json() or {}).get("data") or []
            if not items or not items[0].get("url"):
                raise RuntimeError(f"智谱生图接口返回结构异常: {resp.text[:200]}")
            logger.info("智谱生图完成（免费 cogview，带角标水印）")
            return items[0]["url"]
        raise last_error or RuntimeError("智谱生图重试次数用尽")
    finally:
        if own_client:
            client.close()


def _dashscope_generate(config: Config, plan_text: str) -> str:
    """通义万相（DashScope）文生图：创建异步任务并轮询至成功，返回效果图 URL。"""
    if not config.image_api_key:
        raise RuntimeError("IMAGE_PROVIDER=dashscope 但未配置 IMAGE_API_KEY（见 .env）")
    headers = {
        "Authorization": f"Bearer {config.image_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": config.image_model,
        "input": {"prompt": plan_text},
        "parameters": {"size": "1024*1024", "n": 1},
    }
    with httpx.Client(timeout=30) as client:
        # 1) 创建异步任务
        resp = client.post(
            _CREATE_URL, headers={**headers, "X-DashScope-Async": "enable"}, json=body)
        resp.raise_for_status()
        task_id = resp.json()["output"]["task_id"]
        logger.info("DashScope 生图任务已创建 task_id=%s", task_id)

        # 2) 轮询任务状态
        deadline = time.time() + config.image_task_timeout
        while time.time() < deadline:
            t = client.get(_TASK_URL.format(task_id=task_id), headers=headers)
            t.raise_for_status()
            output = t.json()["output"]
            status = output.get("task_status", "")
            if status == "SUCCEEDED":
                results = output.get("results") or []
                if results and results[0].get("url"):
                    url = results[0]["url"]
                    logger.info("DashScope 生图完成 task_id=%s", task_id)
                    return url
                raise RuntimeError(f"生图成功但未返回结果 URL: {output}")
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(
                    f"DashScope 生图任务失败: {t.json().get('message') or output}")
            time.sleep(config.image_poll_interval)
        raise TimeoutError(f"DashScope 生图超时（> {config.image_task_timeout}s）")