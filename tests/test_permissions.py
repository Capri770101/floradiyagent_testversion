"""权限模型：admin/merchant 角色鉴权 + 评价。

覆盖「权限区分」后端链路：
- 管理后台：未登录 401、普通用户 403、admin 角色放行 CRUD
- 商家端：普通用户 403、merchant 角色放行（admin 亦可）
- 评价：仅订单主人 + 已签收订单可评，重复评价更新，公开列表带昵称
"""
import backend.api as api
import pytest
from backend.security import set_user_role
from fastapi.testclient import TestClient


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
    data = r.json()
    if role != "user":
        set_user_role(data["user_id"], role)
    return data["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_and_complete(client, token, shop="S001", price=99):
    r = client.post(
        "/orders",
        headers=_h(token),
        json={"items": [{"plan_id": "P001", "name": "测试花束", "price": price, "qty": 1, "shop": shop}]},
    )
    oid = r.json()["order"]["order_id"]
    client.post("/pay", headers=_h(token), json={"order_id": oid})
    client.post(f"/orders/{oid}/action", headers=_h(token), json={"action": "ship"})
    client.post(f"/orders/{oid}/action", headers=_h(token), json={"action": "complete"})
    return oid


# --------------------------------------------------------------------------- #
# 管理后台权限
# --------------------------------------------------------------------------- #


def test_admin_requires_login(client):
    r = client.get("/admin/plans")
    assert r.status_code == 401


def test_admin_forbids_normal_user(client):
    token = _register(client, "perm_plain")
    r = client.get("/admin/plans", headers=_h(token))
    assert r.status_code == 403


def test_admin_role_allows_crud(client):
    token = _register(client, "perm_admin", role="admin")
    r = client.get("/admin/plans", headers=_h(token))
    assert r.status_code == 200
    # 写入（增改删一个临时方案）
    r = client.post(
        "/admin/plans",
        headers=_h(token),
        json={"plan_id": "P999", "name": "权限测试方案", "price": 66},
    )
    assert r.status_code == 200
    pid = r.json()["plan"]["plan_id"]
    r = client.put(
        f"/admin/plans/{pid}",
        headers=_h(token),
        json={"price": 88},
    )
    assert r.json()["plan"]["price"] == 88
    r = client.delete(f"/admin/plans/{pid}", headers=_h(token))
    assert r.status_code == 200


def test_admin_cannot_access_merchant(client):
    """平台管理员走独立管理后台，无权访问商家工作台（2026-08 决策）。"""
    token = _register(client, "perm_admin2", role="admin")
    r = client.get("/merchant/stats", headers=_h(token))
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 评价
# --------------------------------------------------------------------------- #


def test_review_requires_done_order_and_owner(client):
    token = _register(client, "rev_a")
    oid = _create_and_complete(client, token)
    # 非本人
    other = _register(client, "rev_b")
    r = client.post("/reviews", headers=_h(other), json={"order_id": oid, "rating": 5})
    assert r.status_code == 400
    # 未完成订单不可评
    r2 = client.post(
        "/orders",
        headers=_h(token),
        json={"items": [{"plan_id": "P001", "name": "x", "price": 10, "qty": 1, "shop": "S001"}]},
    )
    oid2 = r2.json()["order"]["order_id"]
    r = client.post("/reviews", headers=_h(token), json={"order_id": oid2, "rating": 5})
    assert r.status_code == 400
    # 本人 + done 成功
    r = client.post("/reviews", headers=_h(token), json={"order_id": oid, "rating": 5, "content": "很满意"})
    assert r.status_code == 200, r.text
    assert r.json()["review"]["rating"] == 5
    # 重复评价 = 更新
    r = client.post("/reviews", headers=_h(token), json={"order_id": oid, "rating": 4, "content": "还行"})
    assert r.json()["review"]["rating"] == 4


def test_review_list_public_with_nickname(client):
    token = _register(client, "rev_c")
    oid = _create_and_complete(client, token)
    client.post("/reviews", headers=_h(token), json={"order_id": oid, "rating": 5})
    r = client.get("/reviews", params={"plan_id": "P001"})
    assert r.status_code == 200
    reviews = r.json()["reviews"]
    assert any(rev["order_id"] == oid and rev["nickname"] for rev in reviews)
