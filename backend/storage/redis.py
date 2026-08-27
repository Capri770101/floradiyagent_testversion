"""storage/redis.py —— Redis 异步连接池（P0 基础设施）。

设计要点：
- 懒加载：模块导入不建立任何连接；首次 get_redis() 才建池，避免无 Redis 环境 import 即报错。
- 配置驱动：REDIS_URL 留空（dev/test 默认）→ get_redis() 抛 RedisUnavailable，调用方据此降级到本地实现。
- 日志不打印含密码的 URL（_mask 脱敏）。
- 后续 P4 限流 / 缓存 / P3 任务队列均复用本模块，避免多处处建连接。
"""
from __future__ import annotations

import logging

from backend.config import settings

logger = logging.getLogger('redis')
_pool = None
_pool_url: str | None = None

class RedisUnavailable(Exception):
    """Redis 未配置或不可用时抛出，调用方据此降级到本地实现。"""

def _mask(url: str) -> str:
    """对 redis://user:pass@host 脱敏，避免日志泄露密码。"""
    if '@' not in url:
        return url
    head, _, host = url.rpartition('@')
    scheme_sep = head.find('://')
    if scheme_sep == -1:
        return url
    scheme = head[:scheme_sep + 3]
    return f'{scheme}***:***@{host}'

def _build_pool():
    """建立（或复用）连接池。REDIS_URL 为空时抛 RedisUnavailable。"""
    global _pool, _pool_url
    url = settings.redis_url
    if not url:
        raise RedisUnavailable('REDIS_URL 未配置，Redis 相关能力不可用（dev/test 应走本地降级）')
    if _pool is not None and _pool_url == url:
        return _pool
    import redis.asyncio as aioredis
    _pool = aioredis.from_url(url, max_connections=settings.redis_pool_max_connections, decode_responses=True, socket_connect_timeout=settings.redis_socket_timeout)
    _pool_url = url
    logger.info('[redis] 连接池已建立 -> %s', _mask(url))
    return _pool

async def get_redis():
    """获取 Redis 客户端（async）。未配置时抛 RedisUnavailable。"""
    return _build_pool()

async def close_redis() -> None:
    """关闭连接池（在 lifespan 关闭钩子调用）。幂等。"""
    global _pool, _pool_url
    if _pool is not None:
        await _pool.aclose()
        logger.info('[redis] 连接池已关闭')
    _pool = None
    _pool_url = None
