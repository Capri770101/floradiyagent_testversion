"""收货地址 + 收藏：CRUD、默认地址规则、下单关联地址、收藏幂等/列表/状态。

覆盖「地址管理 / 收藏」后端链路：地址增删改查（首个自动默认、设默认清其他、
删默认自动顺延）、下单传 address_id 自动落收货人；收藏幂等、取消、列表带方案信息、
商品详情状态查询。
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


# --------------------------------------------------------------------------- #
# 地址
# --------------------------------------------------------------------------- #


def _add_addr(client, token, name="木木", addr="深圳市南山区xx路1号", default=False):
    r = client.post(
        "/addresses",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "phone": "13800000000", "address": addr, "is_default": default},
    )
    assert r.status_code == 200, r.text
    return r.json()["address"]


def test_address_crud_and_first_default(client):
    token = _register(client, "addr_a")
    a1 = _add_addr(client, token)
    assert a1["is_default"] == 1  # 首个地址自动默认
    a2 = _add_addr(client, token, addr="广州市天河区xx路2号")
    assert a2["is_default"] == 0

    # 设 a2 为默认 → a1 默认被清除
    r = client.put(
        f"/addresses/{a2['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_default": True},
    )
    assert r.status_code == 200
    assert r.json()["address"]["is_default"] == 1
    items = client.get("/addresses", headers={"Authorization": f"Bearer {token}"}).json()["addresses"]
    assert [a["id"] for a in items] == [a2["id"], a1["id"]]

    # 编辑字段
    r = client.put(
        f"/addresses/{a1['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"phone": "13900000000"},
    )
    assert r.json()["address"]["phone"] == "13900000000"

    # 删默认地址 → 最新一条顺延为默认
    r = client.delete(f"/addresses/{a2['id']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    items = client.get("/addresses", headers={"Authorization": f"Bearer {token}"}).json()["addresses"]
    assert len(items) == 1
    assert items[0]["id"] == a1["id"]
    assert items[0]["is_default"] == 1


def test_address_isolated_by_user(client):
    t1 = _register(client, "addr_b1")
    t2 = _register(client, "addr_b2")
    a = _add_addr(client, t1)
    items = client.get("/addresses", headers={"Authorization": f"Bearer {t2}"}).json()["addresses"]
    assert items == []
    # 他人不能改我的地址（404 兜底：id 不存在于本人名下）
    r = client.put(
        f"/addresses/{a['id']}",
        headers={"Authorization": f"Bearer {t2}"},
        json={"phone": "13900000000"},
    )
    assert r.status_code == 404


def test_order_with_address_id(client):
    token = _register(client, "addr_c")
    a = _add_addr(client, token)
    r = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "items": [{"plan_id": "P001", "name": "测试花束", "price": 99, "qty": 1, "shop": "S001"}],
            "address_id": a["id"],
        },
    )
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["recipient"]["name"] == "木木"
    assert o["recipient"]["address"] == "深圳市南山区xx路1号"


# --------------------------------------------------------------------------- #
# 收藏
# --------------------------------------------------------------------------- #


def test_favorite_toggle_and_list(client):
    token = _register(client, "fav_a")
    r = client.post(
        "/favorites",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_id": "P001"},
    )
    assert r.status_code == 200
    # 幂等：重复收藏不报错
    r = client.post(
        "/favorites",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_id": "P001"},
    )
    assert r.status_code == 200
    # 状态查询
    r = client.get("/favorites/P001/status", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["favorited"] is True
    # 列表带方案信息
    items = client.get("/favorites", headers={"Authorization": f"Bearer {token}"}).json()
    assert items["count"] == 1
    assert items["favorites"][0]["plan_id"] == "P001"
    assert items["favorites"][0]["name"]
    # 取消
    r = client.delete("/favorites/P001", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["favorited"] is False
    items = client.get("/favorites", headers={"Authorization": f"Bearer {token}"}).json()
    assert items["count"] == 0
    # 状态同步
    r = client.get("/favorites/P001/status", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["favorited"] is False
