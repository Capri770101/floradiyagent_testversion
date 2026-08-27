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

import asyncio
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
from backend.storage import db_async as dba
from backend.storage.object_store import save_generated
from backend.tasks import queue as taskq

logger = logging.getLogger('tasks')

def _now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds')

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
    rows = []
    for y in range(size):
        r = int(244 - 42 * y / size)
        g = int(235 - 44 * y / size)
        b = int(222 - 40 * y / size)
        rows.append(b'\x00' + bytes([r, g, b]) * size)
    raw = b''.join(rows)

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return len(data).to_bytes(4, 'big') + c + zlib.crc32(c).to_bytes(4, 'big')
    ihdr = b''.join([size.to_bytes(4, 'big'), size.to_bytes(4, 'big'), b'\x08\x02\x00\x00\x00'])
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')
    return save_generated(f'{task_id}.png', png)

def _save_base64_image(b64: str, task_id: str, ext: str='png') -> str:
    """把中转商返回的 base64 图片解码落盘，返回本地可访问 URL（维持 result_url 契约）。

    Args:
        b64: base64 编码的图片数据。
        task_id: 本地生图任务 id（用作文件名，保证与 DB 记录一致）。
        ext: 图片扩展名（png/jpeg/webp）。

    Returns:
        /generated/{task_id}.{ext} 形式的本地 URL。
    """
    data = base64.b64decode(b64)
    return save_generated(f'{task_id}.{ext}', data)

def _is_safe_image_url(url: str) -> bool:
    """SSRF 防护：校验第三方返回的图片直链是否可安全下载。

    规则：
    - 仅允许 http/https 协议；
    - 主机名必须落在白名单（settings.image_download_hosts：官方 host + 已配置 provider base 派生）内；
    - 解析出的所有 IP 不得为私网 / 回环 / 链路本地 / 保留 / 组播地址。

    Args:
        url: 待下载的图片直链。

    Returns:
        安全则为 True。
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        logger.warning('[tasks] 拒绝非 http(s) 图片地址: %s', url)
        return False
    host = parsed.hostname
    if not host:
        return False
    allowed = settings.image_download_hosts
    if not any(host == h or host.endswith('.' + h) for h in allowed):
        logger.warning('[tasks] 拒绝白名单外图片 host: %s (allowed=%s)', host, allowed)
        return False
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except Exception:
        if any(host == h or host.endswith('.' + h) for h in settings.image_download_allowed_hosts):
            return True
        logger.warning('[tasks] 自定义 host 解析失败，拒绝下载（fail-closed）: %s', host)
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            logger.warning('[tasks] 拒绝内网/保留 IP 图片地址: %s -> %s', url, ip)
            return False
    return True

def _safe_get(url: str, max_redirects: int=3) -> httpx.Response:
    """带 SSRF 防护的 GET：不自动跟随重定向。

    遇到 3xx 时手动取出 Location 并重新经 _is_safe_image_url 校验后再请求，
    防止「首跳白名单安全、重定向跳到内网」的绕过。

    Args:
        url: 已校验安全的图片直链。
        max_redirects: 最大手动跟随次数。

    Returns:
        最终响应（已 raise_for_status）。

    Raises:
        RuntimeError: 重定向目标不可信或请求失败时抛出。
    """
    current = url
    for _ in range(max_redirects + 1):
        resp = httpx.get(current, timeout=60.0, follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get('location')
            if not loc:
                resp.raise_for_status()
                return resp
            if not loc.startswith('http'):
                loc = urljoin(current, loc)
            if not _is_safe_image_url(loc):
                raise RuntimeError(f'重定向目标不可信，已拒绝: {loc}')
            current = loc
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError('图片下载重定向次数过多')

def _detect_image_ext(data: bytes) -> str | None:
    """按文件魔数识别真实图片格式（不信任上游 content-type，防止错标扩展名）。

    Returns:
        "png" / "jpg" / "webp"，无法识别时返回 None。
    """
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'webp'
    return None

def _download_image_to_local(url: str, task_id: str) -> str:
    """把中转商直接返回的图片 URL 下载到本地，统一返回本地 URL。

    部分中转商（如 cc-vibe）生图接口返回的是图片直链而非 base64。为维持
    result_url 契约（本地稳定可托管，不依赖外部临时链接时效/访问限制），
    这里把远程图片拉取到 data/generated/{task_id}.{ext}。

    安全闸门（SSRF）：先经 _is_safe_image_url 校验 host 白名单 + IP 非内网，
    再经 _safe_get 手动逐跳校验重定向后才写入本地磁盘。

    Args:
        url: 中转商返回的图片直链。
        task_id: 本地生图任务 id，用作落盘文件名。

    Returns:
        /generated/{task_id}.{ext} 形式的本地 URL。

    Raises:
        RuntimeError: URL 不可信或下载失败 / 返回非图片时抛出。
    """
    if not _is_safe_image_url(url):
        raise RuntimeError(f'图片地址不可信，已拒绝下载: {url}')
    try:
        resp = _safe_get(url)
    except Exception as exc:
        logger.exception('[tasks] 图片下载失败')
        raise RuntimeError(f'图片下载失败: {exc}') from exc
    data = resp.content
    ext = _detect_image_ext(data)
    if ext is None:
        ct = resp.headers.get('content-type', '').lower()
        if 'jpeg' in ct or 'jpg' in ct:
            ext = 'jpg'
        elif 'png' in ct:
            ext = 'png'
        elif 'webp' in ct:
            ext = 'webp'
        else:
            raise RuntimeError(f"下载内容不是受支持的图片格式（content-type={ct or '空'}，前 8 字节 {data[:8]!r}）")
    logger.info('[tasks] api2img 远程图片已落盘 %s.%s (%d bytes)', task_id, ext, len(resp.content))
    return save_generated(f'{task_id}.{ext}', resp.content)
_DASHSCOPE_TASK_URL = 'https://dashscope.aliyuncs.com/api/v1/tasks'

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
    headers = {'Authorization': f'Bearer {settings.image_api_key}', 'Content-Type': 'application/json', 'X-DashScope-Async': 'enable'}
    payload = {'model': settings.image_model, 'input': {'prompt': prompt}, 'parameters': {'size': '1024*1024', 'n': 1}}
    try:
        resp = httpx.post(settings.image_base_url, headers=headers, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.exception('[tasks] 万相提交失败')
        raise RuntimeError(f'万相生图提交失败: {exc}') from exc
    task_id = data.get('output', {}).get('task_id')
    if not task_id:
        raise RuntimeError(f'万相未返回 task_id: {data}')
    logger.info('[tasks] 万相任务已提交 task_id=%s', task_id)
    return task_id

def _image_client_poll(task_id: str) -> tuple[str, str]:
    """轮询万相任务结果。

    Args:
        task_id: 万相 task_id。

    Returns:
        (status, result_url)，status 为本地语义的 pending/done/failed。
    """
    headers = {'Authorization': f'Bearer {settings.image_api_key}'}
    try:
        resp = httpx.get(f'{_DASHSCOPE_TASK_URL}/{task_id}', headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.exception('[tasks] 万相轮询失败')
        raise RuntimeError(f'万相轮询失败: {exc}') from exc
    status = data.get('output', {}).get('task_status', '')
    if status == 'SUCCEEDED':
        results = data.get('output', {}).get('results', [])
        url = results[0]['url'] if results else ''
        return ('done', url)
    if status in ('FAILED', 'UNKNOWN'):
        return ('failed', '')
    return ('pending', '')

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
    base = settings.api2img_base_url.rstrip('/')
    if not base.endswith('/v1'):
        base += '/v1'
    endpoint = f'{base}/images/generations'
    headers = {'Authorization': f'Bearer {settings.api2img_api_key}', 'Content-Type': 'application/json'}
    payload = {'model': settings.api2img_model, 'prompt': prompt, 'n': 1, 'size': settings.api2img_size, 'quality': settings.api2img_quality, 'output_format': settings.api2img_output_format, 'response_format': 'b64_json'}
    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:
        logger.exception('[tasks] api2img 提交失败')
        raise RuntimeError(f'api2img 生图提交失败: {exc}') from exc
    items = result.get('data') or []
    if not items:
        raise RuntimeError(f'api2img 未返回图片数据: {result}')
    item = items[0]
    if item.get('b64_json'):
        ext = settings.api2img_output_format or 'png'
        return _save_base64_image(item['b64_json'], task_id, ext)
    if item.get('url'):
        return _download_image_to_local(item['url'], task_id)
    raise RuntimeError('api2img 返回中既无 b64_json 也无 url')

def _image_client_submit_zhipu(prompt: str, task_id: str, size: str | None=None) -> str:
    """调用智谱 AI 文生图接口（CogView，cogview-3-flash 免费）。

    智谱图像生成 API 路径为 {base}/images/generations（**不含 /v1**，与 api2img
    网关不同）。请求体仅需 model/prompt/size；响应 data[].url 为图片直链（30 天有效）。
    本函数把直链下载到本地，统一返回 /generated/{task_id}.{ext}，维持 result_url 契约。

    Args:
        prompt: 文生图提示词。
        task_id: 本地生图任务 id，用作落盘文件名。
        size: 出图尺寸（如 "1344x768" 宽幅）；缺省用配置 zhipu_size。

    Returns:
        本地图片 URL（/generated/{task_id}.{ext}）。

    Raises:
        RuntimeError: 提交失败或返回结构异常时抛出。
    """
    base = settings.zhipu_base_url.rstrip('/')
    endpoint = f'{base}/images/generations'
    headers = {'Authorization': f'Bearer {settings.zhipu_api_key}', 'Content-Type': 'application/json'}
    payload = {'model': settings.zhipu_model, 'prompt': prompt, 'size': size or settings.zhipu_size}
    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:
        logger.exception('[tasks] 智谱生图提交失败')
        raise RuntimeError(f'智谱生图提交失败: {exc}') from exc
    items = result.get('data') or []
    if not items:
        raise RuntimeError(f'智谱未返回图片数据: {result}')
    item = items[0]
    url = item.get('url') or item.get('file_url')
    if url:
        return _download_image_to_local(url, task_id)
    raise RuntimeError('智谱返回中既无 url 也无 file_url')

async def get_task_prompt(task_id: str) -> str:
    """按 task_id 取生图任务的 prompt（worker 消费时回填使用）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT prompt FROM image_tasks WHERE task_id=?', (task_id,))
    return rows[0]['prompt'] if rows else ''

async def _persist_result(task_id: str, status: str, result_url: str, prompt: str) -> None:
    """写入或更新生图任务结果（幂等，供 worker 与同步路径共用）。"""
    async with dba.transaction() as c:
        await c.execute('INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET status=excluded.status, result_url=excluded.result_url', (task_id, status, prompt, result_url, _now()))

def _generate_image(task_id: str, prompt: str) -> tuple[str, str]:
    """同步执行生图（api2img / zhipu / mock），失败时降级占位图。

    返回 (status, result_url)。失败时保持同一 task_id（与原逻辑新建 id 不同，轮询一致性更好）。
    """
    provider = settings.image_provider
    try:
        if provider == 'api2img':
            url = _image_client_submit_api2img(prompt, task_id)
        elif provider == 'zhipu':
            url = _image_client_submit_zhipu(prompt, task_id)
        else:
            url = _write_mock_placeholder(task_id)
        return ('done', url)
    except RuntimeError:
        logger.warning('[tasks] 出图失败，降级为本地占位图 task=%s', task_id)
        return ('done', _write_mock_placeholder(task_id))

async def create_image_task(prompt: str) -> str:
    """提交生图任务，立即返回 task_id。

    - dashscope（异步）：提交后状态 pending，由 get_image_task 轮询万相结果（不变）。
    - 其余 provider（api2img / zhipu / mock）：默认在请求内同步生成（现状）；
      若开启任务队列（task_queue_enabled=True 且 Redis 可达），则改为「入队 + 立即返回
      task_id」，由 worker 异步生成，前端仍经 GET /tasks/{task_id} 轮询。
    """
    if settings.image_enabled:
        provider = settings.image_provider
        if provider == 'dashscope':
            task_id = _image_client_submit(prompt)
            status = 'pending'
            result_url = ''
        else:
            task_id = uuid.uuid4().hex
            if taskq.queue_enabled():
                async with dba.transaction() as c:
                    await c.execute('INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)', (task_id, 'pending', prompt, '', _now()))
                await asyncio.to_thread(taskq.enqueue_image_task, task_id)
                logger.info('[tasks] 生图任务 %s 已入队（异步生成）', task_id)
                return task_id
            status, result_url = await asyncio.to_thread(_generate_image, task_id, prompt)
    else:
        task_id = uuid.uuid4().hex
        if taskq.queue_enabled():
            async with dba.transaction() as c:
                await c.execute('INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)', (task_id, 'pending', prompt, '', _now()))
            await asyncio.to_thread(taskq.enqueue_image_task, task_id)
            logger.info('[tasks] 生图任务 %s 已入队（异步生成）', task_id)
            return task_id
        status, result_url = await asyncio.to_thread(_generate_image, task_id, prompt)
    async with dba.transaction() as c:
        await c.execute('INSERT INTO image_tasks(task_id, status, prompt, result_url, created_at) VALUES (?,?,?,?,?)', (task_id, status, prompt, result_url, _now()))
    logger.info('[tasks] 生图任务 %s 提交，状态=%s', task_id, status)
    return task_id

async def get_image_task(task_id: str) -> dict[str, Any]:
    """轮询任务结果。

    真实模式且任务未完成时，实时回源万相轮询一次并更新本地状态；
    Mock 模式直接返回落库结果。
    """
    async with dba.transaction() as c:
        rows = await c.execute('SELECT task_id, status, result_url FROM image_tasks WHERE task_id = ?', (task_id,))
    row = rows[0] if rows else None
    if not row:
        return {'task_id': task_id, 'status': 'not_found', 'result_url': ''}
    if settings.image_enabled and row['status'] in ('pending', 'running'):
        try:
            new_status, url = _image_client_poll(task_id)
        except RuntimeError:
            return {'task_id': task_id, 'status': row['status'], 'result_url': ''}
        if new_status in ('done', 'failed'):
            async with dba.transaction() as c:
                await c.execute('UPDATE image_tasks SET status=?, result_url=? WHERE task_id=?', (new_status, url, task_id))
            try:
                from backend import observability
                observability.record_image(new_status == 'done')
            except Exception:
                pass
        return {'task_id': task_id, 'status': new_status, 'result_url': url}
    return {'task_id': row['task_id'], 'status': row['status'], 'result_url': row['result_url'] or ''}
