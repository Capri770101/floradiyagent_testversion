"""手机号验证码登录/注册 + 微信绑定测试（不触网，patch code2session）。"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api
import security


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as c:  # 触发 lifespan：init_db
        yield c


def test_phone_code_dev_returns_fixed_code(client: TestClient) -> None:
    """dev 模式：获取验证码返回固定码（sms_dev_code），不真实发送。"""
    r = client.post("/auth/phone-code", json={"phone": "13800001111"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["dev_code"] == security.settings.sms_dev_code
    assert body["ttl_seconds"] == security.settings.phone_code_ttl_seconds


def test_phone_login_wrong_code_401(client: TestClient) -> None:
    """验证码错误 → 401。"""
    client.post("/auth/phone-code", json={"phone": "13800002222"})
    r = client.post("/auth/phone-login", json={"phone": "13800002222", "code": "000000"})
    assert r.status_code == 401


def test_phone_login_auto_registers_and_reuses(client: TestClient) -> None:
    """手机号验证码登录：无账号自动注册；再次登录复用同一账号。"""
    client.post("/auth/phone-code", json={"phone": "13800003333"})
    r = client.post("/auth/phone-login", json={"phone": "13800003333", "code": security.settings.sms_dev_code})
    assert r.status_code == 200
    body = r.json()
    assert body["is_new"] is True
    assert body["phone"] == "13800003333"
    assert security.verify_token(body["token"]) == body["user_id"]

    # 同号再次登录：不再新建
    client.post("/auth/phone-code", json={"phone": "13800003333"})
    r2 = client.post("/auth/phone-login", json={"phone": "13800003333", "code": security.settings.sms_dev_code})
    assert r2.status_code == 200
    assert r2.json()["is_new"] is False
    assert r2.json()["user_id"] == body["user_id"]

    # /auth/me 可查到资料（phone 已落库）
    r3 = client.get("/auth/me", headers={"Authorization": f"Bearer {r2.json()['token']}"})
    assert r3.status_code == 200
    assert r3.json()["user"]["phone"] == "13800003333"


def test_phone_code_used_once(client: TestClient) -> None:
    """验证码一次性：校验成功后销毁，同码重放应失败（不重新获取）。"""
    client.post("/auth/phone-code", json={"phone": "13800004444"})
    code = security.settings.sms_dev_code
    assert client.post("/auth/phone-login", json={"phone": "13800004444", "code": code}).status_code == 200
    assert client.post("/auth/phone-login", json={"phone": "13800004444", "code": code}).status_code == 401


def test_wx_login_auto_provisions_profile(client: TestClient) -> None:
    """wx-login：openid 无账号时自动建档，/auth/me 可查，第二次登录不重复建。"""
    fake = {"openid": "oBindTest", "session_key": "sk"}
    with patch.object(security.settings, "wechat_appid", "appid"), \
         patch.object(security.settings, "wechat_secret", "secret"), \
         patch.object(api, "wx_code2session", return_value=fake):
        r = client.post("/auth/wx-login", json={"code": "abc"})
        assert r.status_code == 200
        assert r.json()["is_new"] is True
        token = r.json()["token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["user"]["id"] == "oBindTest"

        r2 = client.post("/auth/wx-login", json={"code": "abc"})
        assert r2.json()["is_new"] is False


def test_wx_bind_requires_login(client: TestClient) -> None:
    """wx-bind：未登录 → 401。"""
    with patch.object(security.settings, "wechat_appid", "appid"), \
         patch.object(security.settings, "wechat_secret", "secret"):
        r = client.post("/auth/wx-bind", json={"code": "abc"})
        assert r.status_code == 401


def test_wx_bind_success_and_conflict(client: TestClient) -> None:
    """wx-bind：登录后可绑定 openid；openid 已被他人占用 → 409。"""
    fake = {"openid": "oBindMe", "session_key": "sk"}
    token_a = client.post("/auth/register", json={"username": "bind_a", "password": "pass123456"}).json()["token"]
    token_b = client.post("/auth/register", json={"username": "bind_b", "password": "pass123456"}).json()["token"]

    with patch.object(security.settings, "wechat_appid", "appid"), \
         patch.object(security.settings, "wechat_secret", "secret"), \
         patch.object(api, "wx_code2session", return_value=fake):
        r = client.post("/auth/wx-bind", json={"code": "abc"}, headers={"Authorization": f"Bearer {token_a}"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # 第二个账号绑定同一 openid → 409
        r2 = client.post("/auth/wx-bind", json={"code": "abc"}, headers={"Authorization": f"Bearer {token_b}"})
        assert r2.status_code == 409
