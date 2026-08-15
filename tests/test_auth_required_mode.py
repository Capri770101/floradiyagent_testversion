"""生产鉴权模式（AUTH_REQUIRED=true）：全端点强制 Bearer 令牌。

覆盖「生产鉴权切换」后端链路：开启 auth_required + 固定 JWT_SECRET 后，
- 无令牌访问业务端点 → 401（/chat /cart /orders /points /reviews POST 等）
- 无效令牌 → 401
- 有效令牌 → 200 且身份以令牌为准（body user_id 不可冒用）
- admin / merchant 端点同样受 JWT 约束
"""
import pytest
from fastapi.testclient import TestClient

import api
import security


@pytest.fixture()
def strict_settings(monkeypatch):
    """模拟生产配置：强制鉴权 + 固定 JWT 密钥。"""
    monkeypatch.setattr(security.settings, "auth_required", True)
    monkeypatch.setattr(security.settings, "jwt_secret", "prod-test-secret-0123456789")
    monkeypatch.setattr(api.settings, "auth_required", True)
    return security.settings


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def test_unauthorized_requests_rejected(strict_settings, client):
    for method, path, body in [
        ("POST", "/chat", {"message": "你好", "user_id": "anonymous"}),
        ("GET", "/cart", None),
        ("GET", "/orders", None),
        ("GET", "/points", None),
        ("GET", "/coupons", None),
        ("GET", "/favorites", None),
        ("GET", "/addresses", None),
        ("GET", "/admin/plans", None),
        ("GET", "/merchant/stats", None),
        ("POST", "/reviews", {"order_id": "O_x", "rating": 5}),
    ]:
        r = client.request(method, path, json=body)
        assert r.status_code == 401, f"{method} {path} 应 401, 实际 {r.status_code}"


def test_invalid_token_rejected(strict_settings, client):
    r = client.get("/orders", headers={"Authorization": "Bearer bad.token.here"})
    assert r.status_code == 401


def test_identity_from_token_not_body(strict_settings, client):
    # 注册拿真实令牌
    r = client.post(
        "/auth/register",
        json={"username": "strict_user", "password": "secret123", "nickname": "鉴权"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    real_uid = r.json()["user_id"]
    # 携带他人 user_id 也无法冒用：/orders 按令牌身份返回
    r = client.get("/orders", params={"user_id": "someone_else"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert all(o["user_id"] == real_uid for o in r.json()["orders"])


def test_public_endpoints_still_open(strict_settings, client):
    # 只读目录 / 生图任务状态等公开端点不强制鉴权
    assert client.get("/plans").status_code == 200
    assert client.get("/shops").status_code == 200
    assert client.get("/reviews").status_code == 200
    assert client.get("/coupon-offers").status_code == 200


def test_chat_requires_token_even_with_body_user(strict_settings, client):
    r = client.post("/chat", json={"message": "你好", "user_id": "anonymous"})
    assert r.status_code == 401
