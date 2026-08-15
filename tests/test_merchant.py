"""商家端接口：经营统计、订单列表（任意用户）、代发货、评价列表。

覆盖「商家端」后端链路：/merchant/stats 汇总订单/GMV/待发货/评价、
/merchant/orders 按店铺/状态过滤、/merchant/orders/{id}/ship 代发货（不受归属限制）、
/merchant/reviews 列表；权限：未登录 401、普通用户 403、merchant 角色放行。
"""
import pytest
from fastapi.testclient import TestClient

import api
from security import set_user_role


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def _register(client, username, role="merchant"):
    r = client.post(
        "/auth/register",
        json={"username": username, "password": "secret123", "nickname": username},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    if role != "user":
        set_user_role(r.json()["user_id"], role)
    return token


def _merchant_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_and_pay(client, token, shop="S001", price=99):
    r = client.post(
        "/orders",
        headers=_merchant_headers(token),
        json={"items": [{"plan_id": "P001", "name": "测试花束", "price": price, "qty": 1, "shop": shop}]},
    )
    assert r.status_code == 200, r.text
    oid = r.json()["order"]["order_id"]
    r = client.post("/pay", headers=_merchant_headers(token), json={"order_id": oid})
    assert r.status_code == 200, r.text
    return oid


def test_merchant_requires_login(client):
    r = client.get("/merchant/stats")
    assert r.status_code == 401


def test_merchant_forbids_normal_user(client):
    token = _register(client, "mer_plain", role="user")
    r = client.get("/merchant/stats", headers=_merchant_headers(token))
    assert r.status_code == 403


def test_merchant_stats(client):
    token = _register(client, "mer_a")
    _create_and_pay(client, token, shop="巷陌花集", price=99)
    r = client.get("/merchant/stats", headers=_merchant_headers(token))
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["order_count"] >= 1
    assert stats["gmv"] >= 99
    assert stats["pending_ship"] >= 1
    assert "shops" in stats


def test_merchant_orders_filter_by_shop_and_status(client):
    token = _register(client, "mer_b")
    _create_and_pay(client, token, shop="兰庭花礼", price=199)
    r = client.get(
        "/merchant/orders",
        params={"shop_id": "兰庭花礼", "status": "paid"},
        headers=_merchant_headers(token),
    )
    assert r.status_code == 200
    orders = r.json()["orders"]
    assert all(o["shop_id"] == "兰庭花礼" and o["status"] == "paid" for o in orders)
    # 状态过滤：done 为空
    r = client.get("/merchant/orders", params={"status": "done"}, headers=_merchant_headers(token))
    assert all(o["status"] == "done" for o in r.json()["orders"])


def test_merchant_ship_any_user_order(client):
    token = _register(client, "mer_c")
    oid = _create_and_pay(client, token)
    r = client.post(f"/merchant/orders/{oid}/ship", headers=_merchant_headers(token))
    assert r.status_code == 200, r.text
    assert r.json()["order"]["status"] == "shipped"
    # 已发货再代发 → 400 状态机拒绝
    r = client.post(f"/merchant/orders/{oid}/ship", headers=_merchant_headers(token))
    assert r.status_code == 400


def test_merchant_reviews(client):
    token = _register(client, "mer_d")
    _create_and_pay(client, token)
    r = client.get("/merchant/reviews", headers=_merchant_headers(token))
    assert r.status_code == 200
    assert isinstance(r.json()["reviews"], list)
