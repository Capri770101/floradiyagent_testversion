"""tests/test_ratelimit.py —— P4 限流 Redis 化测试（内存实现无需外部依赖即可跑）。"""
from __future__ import annotations

from backend.config import Settings
from backend.routers import common as common_mod
from backend.routers.common import MemoryRateLimiter, RateLimiter, _build_limiter


def test_memory_limiter_allows_up_to_limit_then_rejects() -> None:
    """内存限流器：窗口内允许 limit 次，第 limit+1 次拒绝。"""
    lim = MemoryRateLimiter()
    for _ in range(5):
        assert lim.allow('k', limit=5, window=60) is True
    assert lim.allow('k', limit=5, window=60) is False
    assert lim.allow('other', limit=5, window=60) is True

def test_memory_limiter_limit_zero_rejects() -> None:
    assert MemoryRateLimiter().allow('k', limit=0) is False

def test_build_limiter_defaults_to_memory(monkeypatch) -> None:
    """未配置 redis_url 时装配内存限流器（接口不变，调用点无需改动）。"""
    monkeypatch.setattr(common_mod, 'settings', Settings(redis_url=''))
    limiter = _build_limiter()
    assert isinstance(limiter, MemoryRateLimiter)
    assert isinstance(limiter, RateLimiter)

def test_existing_limiter_is_rate_limiter() -> None:
    """模块级 _limiter 是 RateLimiter 实例（无 redis_url 时为内存实现）。"""
    assert isinstance(common_mod._limiter, RateLimiter)
