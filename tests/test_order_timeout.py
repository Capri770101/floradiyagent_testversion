"""订单支付超时：懒过期自动取消 + 优惠券返还。

覆盖「支付超时真实化」后端链路：
- 订单带 expires_at / remaining_seconds
- 超时后读取订单/列表/支付/取消动作均触发懒过期 → canceled + 物流事件
- 过期订单不可支付（400 状态机保护）
- 过期自动取消时返还已占用优惠券
"""
import backend.api as api
import pytest
from backend.config import settings
from backend.storage import commerce
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def _register(client, username):
    r = client.post(
        "/auth/register",
        json={"username": username, "password": "secret123", "nickname": "超时测试"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user_id"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_order(client, token, price=99):
    r = client.post(
        "/orders",
        headers=_h(token),
        json={"items": [{"plan_id": "P001", "name": "测试花束", "price": price, "qty": 1, "shop": "S001"}]},
    )
    assert r.status_code == 200, r.text
    return r.json()["order"]


def test_order_carries_expiry_and_remaining(client):
    token, _ = _register(client, "exp_a")
    order = _create_order(client, token)
    assert order["expires_at"]
    assert order["remaining_seconds"] > 0
    assert order["remaining_seconds"] <= settings.order_pay_timeout_minutes * 60


def _expired_now():
    """模拟「时间已走到 30 分钟之后」（远大于订单创建时间戳）。"""
    return 2_000_000_000


def test_expired_order_auto_cancels_on_read(monkeypatch, client):
    token, uid = _register(client, "exp_b")
    order = _create_order(client, token)
    # 把过期时间拨到过去
    monkeypatch.setattr(commerce, "_now_ts", _expired_now)
    r = client.get(f"/orders/{order['order_id']}", headers=_h(token))
    assert r.status_code == 200, r.text
    got = r.json()["order"]
    assert got["status"] == "canceled"
    assert got["remaining_seconds"] == 0
    assert any("自动取消" in e["text"] for e in got["logistics"])


def test_expired_order_cannot_pay(monkeypatch, client):
    token, _ = _register(client, "exp_c")
    order = _create_order(client, token)
    monkeypatch.setattr(commerce, "_now_ts", _expired_now)
    r = client.post("/pay", headers=_h(token), json={"order_id": order["order_id"]})
    assert r.status_code == 400


def test_expiry_returns_coupon(monkeypatch, client):
    token, _ = _register(client, "exp_d")
    # 下单自动抵扣新人券 → 券被标记 used
    order = _create_order(client, token, price=99)
    assert order["coupon_id"]
    coupons = client.get("/coupons", headers=_h(token)).json()["coupons"]
    used = [c for c in coupons if c["id"] == order["coupon_id"]]
    assert used and used[0]["status"] == "used"
    # 超时自动取消 → 券返还 unused
    monkeypatch.setattr(commerce, "_now_ts", _expired_now)
    client.get(f"/orders/{order['order_id']}", headers=_h(token))
    coupons = client.get("/coupons", headers=_h(token)).json()["coupons"]
    back = [c for c in coupons if c["id"] == order["coupon_id"]]
    assert back and back[0]["status"] == "unused"
    assert back[0]["order_id"] is None
