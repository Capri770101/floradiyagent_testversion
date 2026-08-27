"""tests/test_redis_pool.py —— P0 Redis 连接池基础测试（无需真实 Redis 即可跑）。"""
from __future__ import annotations

import asyncio

from backend.config import Settings
from backend.storage import redis as redis_mod
from backend.storage.redis import RedisUnavailable


def _reset_pool() -> None:
    """清空模块级连接池缓存，避免跨测试污染。"""
    redis_mod._pool = None
    redis_mod._pool_url = None

def test_module_imports_without_redis_server() -> None:
    """导入模块不应建立连接或抛错（懒加载）。"""
    assert redis_mod.get_redis is not None
    assert redis_mod.close_redis is not None

def test_get_redis_raises_when_url_empty(monkeypatch) -> None:
    """REDIS_URL 留空时 get_redis 抛 RedisUnavailable，调用方据此降级。"""
    _reset_pool()
    monkeypatch.setattr(redis_mod, 'settings', Settings(redis_url=''))
    try:
        asyncio.run(redis_mod.get_redis())
        raise AssertionError('应抛出 RedisUnavailable')
    except RedisUnavailable:
        pass
    finally:
        _reset_pool()

def test_get_redis_builds_pool_when_url_set(monkeypatch) -> None:
    """配置了 REDIS_URL 时建立连接池（不实际发命令，仅验证池对象生成）。"""
    _reset_pool()
    monkeypatch.setattr(redis_mod, 'settings', Settings(redis_url='redis://127.0.0.1:6379/0'))
    try:
        client = asyncio.run(redis_mod.get_redis())
        assert client is not None
        assert redis_mod._pool is not None
    finally:
        asyncio.run(redis_mod.close_redis())
        _reset_pool()
