"""接口限流测试：/chat（防刷 LLM 账单）与 /auth（防撞库/轰炸）。

用 monkeypatch 把限额调低，避免真实请求；/chat 限流检查在 handler 之前执行，
限额=0 时首请求即 429，不触发 LLM 调用（离线零成本）。
"""
import backend.api as api
import pytest
from backend.config import settings
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c

@pytest.fixture(autouse=True)
def _reset_limiter():
    """每个测试前清空限流计数（TestClient 共享同一 IP，避免跨测试污染）。"""
    api._limiter._hits.clear()
    yield
    api._limiter._hits.clear()

def test_chat_rate_limit_429(client, monkeypatch):
    """限额为 0 时 /chat 首请求即 429（限流检查先于 LLM 执行）。"""
    monkeypatch.setattr(settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(settings, 'rate_limit_chat_per_minute', 0)
    r = client.post('/chat', json={'user_id': 'u_rl', 'message': '你好'})
    assert r.status_code == 429
    assert '频繁' in r.json()['message']

def test_chat_rate_limit_disabled_bypass(client, monkeypatch):
    """关闭限流时 /chat 不再 429（handler 会因无 LLM 报 500，但绝不是 429）。"""
    monkeypatch.setattr(settings, 'rate_limit_enabled', False)
    monkeypatch.setattr(settings, 'rate_limit_chat_per_minute', 0)
    r = client.post('/chat', json={'user_id': 'u_rl2', 'message': '你好'})
    assert r.status_code != 429

def test_phone_code_rate_limit(client, monkeypatch):
    """每手机号每分钟限额 1：第二次获取验证码即 429（防短信轰炸）。"""
    monkeypatch.setattr(settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(settings, 'rate_limit_phone_per_minute', 1)
    first = client.post('/auth/phone-code', json={'phone': '13900000001'})
    assert first.status_code == 200
    second = client.post('/auth/phone-code', json={'phone': '13900000001'})
    assert second.status_code == 429

def test_auth_login_rate_limit(client, monkeypatch):
    """登录接口每 IP 限额 1：第二次即 429（防撞密码）。"""
    monkeypatch.setattr(settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(settings, 'rate_limit_auth_per_minute', 1)
    r1 = client.post('/auth/login', json={'username': 'nobody', 'password': 'x'})
    assert r1.status_code in (200, 401)
    r2 = client.post('/auth/login', json={'username': 'nobody', 'password': 'x'})
    assert r2.status_code == 429

def test_image_generate_rate_limit(client, monkeypatch):
    """付费生图接口每 IP 限额 0：首请求即 429（防刷单，限流先于任务创建）。"""
    monkeypatch.setattr(settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(settings, 'rate_limit_image_per_minute', 0)
    r = client.post('/image/generate', json={'prompt': '测试生图'})
    assert r.status_code == 429
    assert '频繁' in r.json()['message']
