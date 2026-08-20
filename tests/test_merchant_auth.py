"""商家独立认证测试（三端架构阶段2）：

验收点（任务书）：
- merchant 手机号走 /auth/merchant-login 成功且拿 JWT；
- 该手机号走 C 端 /auth/register 被拒（409）；
- admin 账号走 /auth/merchant-login 被拒（403）；
- 手机号全局唯一：被 user 占用后商家注册被拒，反之亦然；
- C 端 /auth/login、/auth/phone-login 拒绝 merchant 角色（角色隔离）。
"""

import backend.api as api
import backend.security as security
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as c:  # 触发 lifespan：init_db
        yield c


def test_merchant_register_success_issues_jwt(client: TestClient) -> None:
    """商家注册成功：返回可校验 JWT，且 users 行 role=merchant。"""
    r = client.post("/auth/merchant-register", json={
        "phone": "13800000001", "password": "secret1", "shop_name": "测试花店",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "merchant"
    assert security.verify_token(body["token"]) == body["user_id"]
    assert security.get_user_role(body["user_id"]) == "merchant"


def test_merchant_register_duplicate_phone_conflict(client: TestClient) -> None:
    """同一手机号重复注册商家返回 409。"""
    payload = {"phone": "13800000002", "password": "secret1"}
    assert client.post("/auth/merchant-register", json=payload).status_code == 200
    r = client.post("/auth/merchant-register", json=payload)
    assert r.status_code == 409
    assert "已注册商家" in r.json()["message"]


def test_merchant_register_phone_taken_by_user_conflict(client: TestClient) -> None:
    """手机号已被 C 端用户占用时，商家注册被拒（全局唯一）。"""
    assert client.post("/auth/register", json={
        "username": "u_phone_owner", "password": "secret1",
    }).status_code == 200
    # 该用户随后用手机号登录建档（username=phone）
    client.post("/auth/phone-code", json={"phone": "13800000003"})
    assert client.post("/auth/phone-login", json={
        "phone": "13800000003", "code": "123456",
    }).status_code == 200
    r = client.post("/auth/merchant-register", json={
        "phone": "13800000003", "password": "secret1",
    })
    assert r.status_code == 409
    assert "手机号已被使用" in r.json()["message"]


def test_merchant_login_success_and_role_gate(client: TestClient) -> None:
    """商家登录成功拿 JWT；普通用户/admin 走商家登录被 403。"""
    r = client.post("/auth/merchant-register", json={
        "phone": "13800000004", "password": "secret1",
    })
    mid = r.json()["user_id"]
    r = client.post("/auth/merchant-login", json={
        "username": "13800000004", "password": "secret1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "merchant"
    assert security.verify_token(r.json()["token"]) == mid
    # 密码错误 401
    assert client.post("/auth/merchant-login", json={
        "username": "13800000004", "password": "wrong1",
    }).status_code == 401
    # 普通用户 403
    client.post("/auth/register", json={"username": "m_gate_user", "password": "secret1"})
    assert client.post("/auth/merchant-login", json={
        "username": "m_gate_user", "password": "secret1",
    }).status_code == 403


def test_merchant_login_rejects_admin(client: TestClient) -> None:
    """admin 账号走 /auth/merchant-login 被拒（403）。"""
    client.post("/auth/register", json={"username": "m_admin_seed", "password": "secret1"})
    uid = security.verify_token(client.post("/auth/login", json={
        "username": "m_admin_seed", "password": "secret1",
    }).json()["token"])
    security.set_user_role(uid, "admin")
    r = client.post("/auth/merchant-login", json={
        "username": "m_admin_seed", "password": "secret1",
    })
    assert r.status_code == 403


def test_c_end_rejects_merchant_login_and_register(client: TestClient) -> None:
    """商家手机号走 C 端登录被 403；同名 C 端注册被 409（角色隔离）。"""
    client.post("/auth/merchant-register", json={
        "phone": "13800000005", "password": "secret1",
    })
    # C 端账号密码登录（username=手机号）→ 403 引导商家端
    r = client.post("/auth/login", json={"username": "13800000005", "password": "secret1"})
    assert r.status_code == 403
    assert "商家端" in r.json()["message"]
    # C 端手机号验证码登录 → 400（拒绝借道）
    client.post("/auth/phone-code", json={"phone": "13800000005"})
    r = client.post("/auth/phone-login", json={"phone": "13800000005", "code": "123456"})
    assert r.status_code == 400
    # C 端注册同名账号 → 409 用户名已存在
    r = client.post("/auth/register", json={
        "username": "13800000005", "password": "secret1",
    })
    assert r.status_code == 409


def test_merchant_token_can_call_merchant_api(client: TestClient) -> None:
    """商家 JWT 可调用受 _require_merchant 守护的商家端接口（端到端闭环）。"""
    r = client.post("/auth/merchant-register", json={
        "phone": "13800000006", "password": "secret1",
    })
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/merchant/shops", headers=h)
    assert r.status_code == 200, r.text


def test_merchant_aftersales_scoped(client: TestClient) -> None:
    """商家售后单列表按绑定店铺隔离；未绑定商家返回空而非泄漏全局数据。"""
    r = client.post("/auth/merchant-register", json={
        "phone": "13800000007", "password": "secret1",
    })
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/merchant/aftersales", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aftersales"] == []
    assert body["total"] == 0
