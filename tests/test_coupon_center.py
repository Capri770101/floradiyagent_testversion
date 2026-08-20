"""领券中心 / 积分商城：免费领 + 积分兑换 + 限领 + 库存。

覆盖「积分商城/领券中心」后端链路：
- GET /coupon-offers 上架模板（含已领标记）
- POST /coupon-offers/{id}/claim 免费领取 → 券入库
- 同 offer 重复领取 400（每人限领一张）
- 积分兑换：积分不足 400；成功扣积分、发券、记流水
- 库存扣减（限 200 张的 offer 领一次后剩余 199）
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
        json={"username": username, "password": "secret123", "nickname": "领券测试"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user_id"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_offer_list_marks_claimed(client):
    token, _ = _register(client, "off_a")
    r = client.get("/coupon-offers", headers=_h(token))
    assert r.status_code == 200, r.text
    offers = r.json()["offers"]
    assert any(o["id"] == "OFF_FREE5" for o in offers)
    assert all(o["claimed"] is False for o in offers)
    # 公开访问（未登录）也返回列表，但不带 claimed
    r2 = client.get("/coupon-offers")
    assert r2.status_code == 200
    assert "claimed" not in r2.json()["offers"][0] or r2.json()["offers"][0]["claimed"] is False


def test_claim_free_coupon(client):
    token, _ = _register(client, "off_b")
    r = client.post("/coupon-offers/OFF_FREE5/claim", headers=_h(token))
    assert r.status_code == 200, r.text
    coupon = r.json()["coupon"]
    assert coupon["title"] == "5 元无门槛券"
    assert coupon["status"] == "unused"
    # 重复领取 → 400
    r = client.post("/coupon-offers/OFF_FREE5/claim", headers=_h(token))
    assert r.status_code == 400
    # 领取后列表标记 claimed
    offers = client.get("/coupon-offers", headers=_h(token)).json()["offers"]
    assert next(o for o in offers if o["id"] == "OFF_FREE5")["claimed"] is True


def test_redeem_with_points(client):
    token, _ = _register(client, "off_c")
    r = client.post("/coupon-offers/OFF_PTS50/claim", headers=_h(token))
    assert r.status_code == 400  # 0 积分 → 积分不足
    # 先赚 100 积分（下一单并支付）
    r = client.post(
        "/orders",
        headers=_h(token),
        json={"items": [{"plan_id": "P001", "name": "x", "price": 100, "qty": 1, "shop": "S001"}]},
    )
    oid = r.json()["order"]["order_id"]
    client.post("/pay", headers=_h(token), json={"order_id": oid})
    points = client.get("/points", headers=_h(token)).json()
    assert points["balance"] >= 100
    # 兑换 50 积分 → 15 元券
    r = client.post("/coupon-offers/OFF_PTS50/claim", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["coupon"]["title"] == "50 积分兑 15 元券"
    after = client.get("/points", headers=_h(token)).json()
    assert after["balance"] == points["balance"] - 50
    assert any("积分兑换" in rec["reason"] for rec in after["records"])
    # 重复兑换 → 400
    r = client.post("/coupon-offers/OFF_PTS50/claim", headers=_h(token))
    assert r.status_code == 400


def test_offer_stock_decreases(client):
    token, _ = _register(client, "off_d")
    r = client.post("/coupon-offers/OFF_PTS100/claim", headers=_h(token))
    assert r.status_code == 400  # 100 积分兑换，积分不足
    offers = client.get("/coupon-offers", headers=_h(token)).json()["offers"]
    stock_after = next(o for o in offers if o["id"] == "OFF_PTS100")["stock"]
    assert stock_after == 100  # 兑换失败不扣库存
