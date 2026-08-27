"""tests/test_llm_reliability.py —— P6.1 LLM 可靠性（重试/退避、多 provider 兜底、熔断、预算）。

全程 monkeypatch ``agent.engine.llm._raw_call`` 与 ``settings``，不触真实网络 / 不依赖 openai。
"""
from __future__ import annotations

import pytest
from agent.engine import llm as llm_mod
from agent.engine.llm import LLMBudgetExceeded, LLMUnavailableError
from backend.config import Settings


class FakeErr(Exception):
    """带 status_code 的假错误，用于驱动 _is_retryable 的 status_code 分支。"""

    def __init__(self, status_code: int) -> None:
        super().__init__(f'status={status_code}')
        self.status_code = status_code

def _settings(**overrides) -> Settings:
    base = dict(llm_base_url='http://primary', llm_api_key='primary-key', llm_model='primary-model', llm_circuit_breaker_enabled=True, llm_cb_failure_threshold=5, llm_cb_open_seconds=30, llm_retry_max_attempts=3, llm_cost_enabled=False, llm_global_daily_token_budget=0, llm_user_daily_token_budget=0)
    base.update(overrides)
    return Settings(**base)

@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(llm_mod, 'settings', _settings())
    monkeypatch.setattr(llm_mod, '_CBS', {})
    monkeypatch.setattr(llm_mod.time, 'sleep', lambda *_a, **_k: None)
    calls = {'n': 0}
    return calls

def test_multi_provider_fallback(patched, monkeypatch) -> None:
    """primary 持续 503，应自动切到 secondary 并成功。"""
    s = _settings(llm_providers='[{"name":"secondary","base_url":"http://sec","api_key":"k2","model":"m2"}]')
    monkeypatch.setattr(llm_mod, 'settings', s)
    monkeypatch.setattr(llm_mod, '_CBS', {})

    def fake(provider, messages, tools, stream, response_format):
        if provider['name'] == 'primary':
            raise FakeErr(503)
        return f"OK:{provider['name']}"
    monkeypatch.setattr(llm_mod, '_raw_call', fake)
    result = llm_mod.call_llm([{'role': 'user', 'content': 'hi'}])
    assert result == 'OK:secondary'

def test_retry_then_success(patched, monkeypatch) -> None:
    """可重试错误先失败后成功，应在重试内恢复。"""
    attempts = {'n': 0}

    def fake(provider, messages, tools, stream, response_format):
        attempts['n'] += 1
        if attempts['n'] < 3:
            raise FakeErr(503)
        return 'OK'
    monkeypatch.setattr(llm_mod, '_raw_call', fake)
    assert llm_mod.call_llm([{'role': 'user', 'content': 'hi'}]) == 'OK'
    assert attempts['n'] == 3

def test_non_retryable_switches_provider_immediately(patched, monkeypatch) -> None:
    """401 鉴权错误不可重试，primary 失败应立即切 secondary（不重试）。"""
    s = _settings(llm_retry_max_attempts=3, llm_providers='[{"name":"secondary","base_url":"http://sec","api_key":"k2","model":"m2"}]')
    monkeypatch.setattr(llm_mod, 'settings', s)
    monkeypatch.setattr(llm_mod, '_CBS', {})
    attempts = {'primary': 0, 'secondary': 0}

    def fake(provider, messages, tools, stream, response_format):
        attempts[provider['name']] += 1
        if provider['name'] == 'primary':
            raise FakeErr(401)
        return 'OK:secondary'
    monkeypatch.setattr(llm_mod, '_raw_call', fake)
    result = llm_mod.call_llm([{'role': 'user', 'content': 'hi'}])
    assert result == 'OK:secondary'
    assert attempts['primary'] == 1
    assert attempts['secondary'] == 1

def test_circuit_breaker_opens_and_short_circuits(patched, monkeypatch) -> None:
    """连续失败达阈值后熔断：第二次调用不再触达 _raw_call，直接 LLMUnavailableError。"""
    s = _settings(llm_retry_max_attempts=2, llm_cb_failure_threshold=2, llm_cb_open_seconds=30)
    monkeypatch.setattr(llm_mod, 'settings', s)
    monkeypatch.setattr(llm_mod, '_CBS', {})
    attempts = {'n': 0}

    def fake(provider, messages, tools, stream, response_format):
        attempts['n'] += 1
        raise FakeErr(503)
    monkeypatch.setattr(llm_mod, '_raw_call', fake)
    with pytest.raises(LLMUnavailableError):
        llm_mod.call_llm([{'role': 'user', 'content': 'hi'}])
    assert attempts['n'] == 2
    with pytest.raises(LLMUnavailableError):
        llm_mod.call_llm([{'role': 'user', 'content': 'hi'}])
    assert attempts['n'] == 2

def test_budget_exceeded_raises(patched, monkeypatch) -> None:
    """全局日预算超限时，call_llm 抛 LLMBudgetExceeded（不触达 _raw_call）。"""
    from agent.engine import budget as budget_mod
    s = _settings(llm_cost_enabled=True, llm_global_daily_token_budget=1000)
    monkeypatch.setattr(llm_mod, 'settings', s)
    monkeypatch.setattr(budget_mod, 'settings', s)

    class FakeRedis:

        def get(self, key):
            return '100000'

        def incrby(self, key, n):
            return 0

        def expire(self, key, ttl):
            return 0
    monkeypatch.setattr(budget_mod, '_make_client', lambda: FakeRedis())
    with pytest.raises(LLMBudgetExceeded):
        llm_mod.call_llm([{'role': 'user', 'content': 'hi'}], user_id='u1')
