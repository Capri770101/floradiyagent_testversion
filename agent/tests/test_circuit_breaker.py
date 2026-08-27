"""tests/test_circuit_breaker.py —— 熔断器状态机测试。"""
from __future__ import annotations

from agent.engine.circuit_breaker import OPEN, CircuitBreaker


def test_cb_opens_after_threshold_then_recovers() -> None:
    t = [0.0]
    cb = CircuitBreaker('x', failure_threshold=3, open_seconds=10, clock=lambda: t[0])
    assert cb.allow() is True
    cb.on_failure()
    cb.on_failure()
    assert cb.state == 'closed'
    cb.on_failure()
    assert cb.state == OPEN
    assert cb.allow() is False
    t[0] = 5.0
    assert cb.allow() is False
    t[0] = 11.0
    assert cb.allow() is True
    cb.on_success()
    assert cb.state == 'closed'

def test_cb_failure_reset_on_success() -> None:
    cb = CircuitBreaker('y', failure_threshold=2, open_seconds=10, clock=lambda: 0.0)
    cb.on_failure()
    cb.on_success()
    assert cb.state == 'closed'
    assert cb.allow() is True
