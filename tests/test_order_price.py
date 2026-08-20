"""订单价格防篡改测试（review P0）：POST /orders 价格以目录为准。

- 客户端传低价 → 服务端按目录价计总额（P001=199，传 0.01 也按 199）
- 方案不存在 → 400（拒绝下单而非信任客户端）
"""
import backend.api as api
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def _register(client, username):
    r = client.post(
        "/auth/register",
        json={"username": username, "password": "secret123", "nickname": username},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_order_price_forced_to_catalog(client):
    """客户端传 0.01 元 → 订单总额按目录价 P001=199 计算。"""
    token = _register(client, "price_a")
    r = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "items": [
                {"plan_id": "P001", "name": "恶意低价", "price": 0.01, "qty": 2, "shop": "S001"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order["total_price"] == 199 * 2
    assert order["items"][0]["price"] == 199  # 快照价格也被服务端覆盖
    assert order["items"][0]["name"] == "康乃馨感恩花束"


def test_order_rejects_unknown_plan(client):
    """方案不存在 → 400，绝不按客户端价格成交。"""
    token = _register(client, "price_b")
    r = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "items": [
                {"plan_id": "NOPE999", "name": "幽灵商品", "price": 1, "qty": 1},
            ]
        },
    )
    assert r.status_code == 400


def test_order_rejects_empty_items(client):
    """空订单（items=[]）→ 422，拒绝创建 0 元单并套用新人券。"""
    token = _register(client, "price_c")
    r = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": []},
    )
    assert r.status_code == 422


def test_order_rejects_oversized_qty(client):
    """超量下单（qty=999）→ 422，拒绝超量。"""
    token = _register(client, "price_d")
    r = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "items": [
                {"plan_id": "P001", "name": "超量", "price": 199, "qty": 999},
            ]
        },
    )
    assert r.status_code == 422
