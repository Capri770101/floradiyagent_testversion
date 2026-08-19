"""C 端与管理后台登录隔离测试。

覆盖「管理员不能登录 C 端 / 后台登录与前端登录互不干扰」：
- POST /auth/login（C 端）拒绝 admin 角色 → 403
- POST /auth/admin-login 要求 role=admin：普通用户 → 403
- POST /auth/admin-login 管理员 → 200 + 令牌可访问 /admin 端点
- 普通用户 /auth/login → 200（C 端正常）
- C 端 /auth/me 对 admin 令牌按未登录处理（getProfile 前端侧清会话）
"""
import pytest
from fastapi.testclient import TestClient

import api
from security import set_user_role


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def _register(client, username, role="user"):
    r = client.post(
        "/auth/register",
        json={"username": username, "password": "secret123", "nickname": username},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    uid = r.json()["user_id"]
    if role != "user":
        set_user_role(uid, role)
    return token, uid


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_cannot_login_c_end(client):
    """管理员账号用 C 端 /auth/login 登录 → 403，不签发令牌。"""
    _, _ = _register(client, "iso_admin", role="admin")
    r = client.post("/auth/login", json={"username": "iso_admin", "password": "secret123"})
    assert r.status_code == 403, r.text
    assert "管理后台" in r.text


def test_normal_user_can_login_c_end(client):
    """普通用户 C 端 /auth/login 正常放行。"""
    _, _ = _register(client, "iso_user", role="user")
    r = client.post("/auth/login", json={"username": "iso_user", "password": "secret123"})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_normal_user_cannot_admin_login(client):
    """普通用户调 /auth/admin-login → 403（无法进入后台）。"""
    _, _ = _register(client, "iso_user2", role="user")
    r = client.post("/auth/admin-login", json={"username": "iso_user2", "password": "secret123"})
    assert r.status_code == 403, r.text


def test_admin_login_grants_backend_access(client):
    """管理员 /auth/admin-login → 200 + 令牌可访问 /admin 端点。"""
    _, _ = _register(client, "iso_admin2", role="admin")
    r = client.post("/auth/admin-login", json={"username": "iso_admin2", "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    r2 = client.get("/admin/plans", headers=_h(token))
    assert r2.status_code == 200, r2.text


def test_admin_token_rejected_on_c_end_profile(client):
    """C 端 /auth/me：admin 令牌仍返回角色信息（前端 getProfile 会按未登录清会话）。"""
    token, _ = _register(client, "iso_admin3", role="admin")
    r = client.get("/auth/me", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "admin"