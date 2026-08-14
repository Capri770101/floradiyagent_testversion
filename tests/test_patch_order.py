"""PATCH /orders/{id} 收货信息更新：owner 校验 + 字段落库 + 跨用户 403。

直接走 TestClient（不调 LLM），覆盖 review 点名的「收货人假交互」后端链路。
"""
import pytest
from fastapi.testclient import TestClient

import api


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


def _create_order(client, token):
    r = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "items": [
                {"plan_id": "P001", "name": "测试花束", "price": 99, "qty": 1, "shop": "S001"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["order"]["order_id"]


def test_patch_updates_recipient_and_persists(client):
    token = _register(client, "patch_a")
    oid = _create_order(client, token)

    # 更新收货人 / 配送时间 / 备注
    r = client.patch(
        f"/orders/{oid}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "recipient": {"name": "木木", "phone": "13800000000", "address": "深圳市盐田区xx路1号"},
            "delivery": "今天 18:00–20:00",
            "note": "请放门口",
        },
    )
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["recipient"]["name"] == "木木"
    assert o["recipient"]["phone"] == "13800000000"
    assert o["recipient"]["address"] == "深圳市盐田区xx路1号"
    assert o["delivery_time"] == "今天 18:00–20:00"
    assert o["note"] == "请放门口"

    # 重新拉取，确认已落库（非仅内存）
    r2 = client.get(f"/orders/{oid}", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["order"]["recipient"]["name"] == "木木"


def test_patch_partial_only_updates_given_fields(client):
    token = _register(client, "patch_b")
    oid = _create_order(client, token)
    client.patch(
        f"/orders/{oid}",
        headers={"Authorization": f"Bearer {token}"},
        json={"recipient": {"name": "仅改名字"}},
    )
    o = client.get(f"/orders/{oid}", headers={"Authorization": f"Bearer {token}"}).json()["order"]
    assert o["recipient"]["name"] == "仅改名字"
    # 未传字段不被覆盖为 None
    assert o["recipient"]["phone"] is None


def test_patch_other_user_order_is_forbidden(client):
    token_a = _register(client, "patch_c")
    token_b = _register(client, "patch_d")
    oid = _create_order(client, token_a)

    r = client.patch(
        f"/orders/{oid}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"note": "偷改"},
    )
    assert r.status_code == 403
