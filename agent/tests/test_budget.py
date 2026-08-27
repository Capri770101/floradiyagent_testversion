"""tests/test_budget.py —— P6.2 token 成本预算（Redis 计数器，best-effort）。

用 FakeRedis 验证：预算内放行、超预算拦截、调用后累加、未启用/无客户端时静默放行。
不依赖真实 Redis。
"""
from __future__ import annotations

import datetime

from agent.engine import budget as budget_mod
from backend.config import Settings


class FakeRedis:
    """极简内存 Redis 桩，仅实现 budget 用到的 get/incrby/expire。"""

    def __init__(self, data: dict[str, str] | None=None) -> None:
        self.data = dict(data or {})

    def get(self, key: str):
        return self.data.get(key)

    def incrby(self, key: str, n: int):
        self.data[key] = str(int(self.data.get(key, '0')) + n)
        return int(self.data[key])

    def expire(self, key: str, ttl: int):
        return 1

def _today_key(suffix: str) -> str:
    return f'llm:budget:{suffix}:{datetime.date.today().isoformat()}'

def test_disabled_budget_always_allows(monkeypatch) -> None:
    monkeypatch.setattr(budget_mod, 'settings', Settings(llm_cost_enabled=False))
    assert budget_mod.check('u1') == (True, None)
    budget_mod.record('u1', 10, 20)

def test_no_redis_client_falls_through(monkeypatch) -> None:
    monkeypatch.setattr(budget_mod, 'settings', Settings(llm_cost_enabled=True, llm_global_daily_token_budget=100))
    monkeypatch.setattr(budget_mod, '_make_client', lambda: None)
    assert budget_mod.check('u1') == (True, None)

def test_global_over_budget_denies(monkeypatch) -> None:
    key = _today_key('global')
    monkeypatch.setattr(budget_mod, 'settings', Settings(llm_cost_enabled=True, llm_global_daily_token_budget=100))
    monkeypatch.setattr(budget_mod, '_make_client', lambda: FakeRedis({key: '100'}))
    allowed, reason = budget_mod.check('u1')
    assert allowed is False
    assert reason == 'global'

def test_record_increments_and_allows_when_under(monkeypatch) -> None:
    key = _today_key('global')
    monkeypatch.setattr(budget_mod, 'settings', Settings(llm_cost_enabled=True, llm_global_daily_token_budget=1000, llm_user_daily_token_budget=500))
    client = FakeRedis()
    monkeypatch.setattr(budget_mod, '_make_client', lambda: client)
    assert budget_mod.check('u1') == (True, None)
    budget_mod.record('u1', 10, 20)
    assert int(client.get(key)) == 30
    user_key = _today_key('user:u1')
    assert int(client.get(user_key)) == 30
    budget_mod.record('u1', 5, 5)
    assert int(client.get(key)) == 40
    assert int(client.get(user_key)) == 40
    assert budget_mod.check('u1') == (True, None)

def test_user_over_budget_denies(monkeypatch) -> None:
    user_key = _today_key('user:u1')
    monkeypatch.setattr(budget_mod, 'settings', Settings(llm_cost_enabled=True, llm_user_daily_token_budget=50))
    monkeypatch.setattr(budget_mod, '_make_client', lambda: FakeRedis({user_key: '50'}))
    allowed, reason = budget_mod.check('u1')
    assert allowed is False
    assert reason == 'user'
