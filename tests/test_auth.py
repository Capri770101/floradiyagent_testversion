"""鉴权模块测试：微信登录 + JWT 签发校验 + dev 模式兼容。

注意：微信登录依赖 code2session 网络调用，这里用 patch 替换为本地假数据，不触网。
/dev 模式（AUTH_REQUIRED=false）下 /chat 仍可用 user_id 直连，保证现有 23 测试无感。
"""
from unittest.mock import patch

import backend.api as api
import backend.security as security
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as c:
        yield c

def test_wx_login_unconfigured_returns_503(client: TestClient) -> None:
    """微信 appid/secret 未配置时，登录接口明确返回 503（提示先填真实小程序数据）。"""
    with patch.object(security.settings, 'wechat_appid', ''), patch.object(security.settings, 'wechat_secret', ''):
        r = client.post('/auth/wx-login', json={'code': 'abc'})
        assert r.status_code == 503

def test_wx_login_success_issues_verifiable_jwt(client: TestClient) -> None:
    """配置齐全时：成功换 openid 并签发可被 verify_token 校验的 JWT。"""
    fake = {'openid': 'oABC123', 'session_key': 'sk', 'unionid': 'u1'}
    with patch.object(security.settings, 'wechat_appid', 'appid'), patch.object(security.settings, 'wechat_secret', 'secret'), patch('backend.routers.auth.wx_code2session', return_value=fake):
        r = client.post('/auth/wx-login', json={'code': 'abc'})
        assert r.status_code == 200
        body = r.json()
        assert body['openid'] == 'oABC123'
        assert security.verify_token(body['token']) == 'oABC123'
        assert body['expires_in'] == security.settings.jwt_expire_minutes * 60

def test_wx_login_wechat_error_propagates(client: TestClient) -> None:
    """微信返回 errcode 时透传为 400，不静默成功。"""
    fake = {'errcode': 40029, 'errmsg': 'invalid code'}
    with patch.object(security.settings, 'wechat_appid', 'appid'), patch.object(security.settings, 'wechat_secret', 'secret'), patch('backend.routers.auth.wx_code2session', return_value=fake):
        r = client.post('/auth/wx-login', json={'code': 'bad'})
        assert r.status_code == 400

def test_jwt_roundtrip_and_tamper(client: TestClient) -> None:
    """JWT 可签发/校验，且篡改后校验失败。"""
    token = security.create_token('oXYZ')
    assert security.verify_token(token) == 'oXYZ'
    bad = token[:-3] + 'zzz'
    import jwt
    try:
        security.verify_token(bad)
        pytest.fail('篡改令牌应校验失败')
    except jwt.PyJWTError:
        pass

def test_dev_mode_chat_uses_body_user_id(client: TestClient) -> None:
    """dev 模式（AUTH_REQUIRED=false）下，/chat 仍以请求体 user_id 作为身份。"""
    r = client.post('/chat', json={'user_id': 'tester', 'message': '你好'})
    assert r.status_code == 200
    assert r.json()['user_id'] == 'tester'

def test_auth_mode_reset_requires_token_and_uses_openid(client: TestClient) -> None:
    """鉴权模式下 /chat/reset 必须带 Bearer；身份以 JWT openid 为准，忽略请求体 user_id（防越权清他人会话）。"""
    with patch.object(security.settings, 'auth_required', True):
        r = client.post('/chat/reset', json={'user_id': 'victim'})
        assert r.status_code == 401
        token = security.create_token('real_openid')
        r = client.post('/chat/reset', json={'user_id': 'victim'}, headers={'Authorization': f'Bearer {token}'})
        assert r.status_code == 200
        assert r.json()['user_id'] == 'real_openid'

def test_auth_mode_tasks_requires_token(client: TestClient) -> None:
    """鉴权模式下 /tasks 必须带 Bearer，防止越权轮询他人生图任务。"""
    with patch.object(security.settings, 'auth_required', True):
        r = client.get('/tasks/whatever')
        assert r.status_code == 401
        token = security.create_token('real_openid')
        r = client.get('/tasks/whatever', headers={'Authorization': f'Bearer {token}'})
        assert r.status_code == 200
