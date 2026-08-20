"""站内消息通知中心（NEW_FEATURES 模块一）接口与数据层测试。

覆盖（任务书 §2.3/§2.4/§2.5）：
- 业务埋点：下单/支付 → order_status；发货 → order_status；商家追加物流 → logistics；
  售后审核 → aftersale；评价回复 → review_reply；公告发布 → announcement
- 列表：type/is_read 过滤 + 分页；未读计数
- 标记已读：单条/批量/all；只影响本人通知
- 详情：本人可见、他人 404；未读计数联动
- 越权：mark-read 不能改他人通知；admin 广播仅 admin 可用
- 容错（验收 2.5）：try_create 失败不影响主业务
"""
import backend.api as api
import pytest
from backend.security import set_user_role
from backend.storage import catalog
from backend.storage import notify as notify_store
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
    if r.status_code == 409:
        # 用户名已存在（临时 DB 残留）：按目标角色走对应登录（admin → admin-login）
        path = "/auth/admin-login" if role == "admin" else "/auth/login"
        r = client.post(path, json={"username": username, "password": "secret123"})
        assert r.status_code == 200, r.text
        token, uid = r.json()["token"], r.json()["user_id"]
        if role != "user":
            set_user_role(uid, role)
        return token, uid
    assert r.status_code == 200, r.text
    token, uid = r.json()["token"], r.json()["user_id"]
    if role != "user":
        set_user_role(uid, role)
    return token, uid


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_order(client, token, shop="S001"):
    r = client.post(
        "/orders",
        headers=_h(token),
        json={"items": [{"plan_id": "P001", "name": "测试花束", "price": 99, "qty": 1, "shop": shop}]},
    )
    assert r.status_code == 200, r.text
    return r.json()["order"]["order_id"]


def _notifies(client, token, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/notifications?{qs}", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["notifications"]


def _unread(client, token):
    r = client.get("/notifications/unread-count", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["unread"]


def test_order_pay_ship_hooks_create_notifications(client):
    token, uid = _register(client, "noti_buyer1")
    oid = _create_order(client, token)
    # 下单即落一条 order_status
    items = _notifies(client, token, type="order_status")
    assert len(items) >= 1
    assert items[0]["type"] == "order_status"
    assert items[0]["ref_type"] == "order" and items[0]["ref_id"] == oid
    assert _unread(client, token) >= 1
    # 支付再落一条
    r = client.post("/pay", headers=_h(token), json={"order_id": oid})
    assert r.status_code == 200, r.text
    assert _notifies(client, token, type="order_status")[0]["title"] == "支付成功"
    # 商家发货再落一条
    r = client.post(f"/orders/{oid}/action", json={"action": "ship"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert _notifies(client, token, type="order_status")[0]["title"] == "订单已发货"


def test_merchant_logistics_node_creates_logistics_notify(client):
    token, uid = _register(client, "noti_buyer2")
    oid = _create_order(client, token)
    r = client.post("/pay", headers=_h(token), json={"order_id": oid})
    assert r.status_code == 200, r.text
    r = client.post(f"/orders/{oid}/action", json={"action": "ship"}, headers=_h(token))
    assert r.status_code == 200, r.text
    mtok, muid = _register(client, "noti_m1", role="merchant")
    mtok, muid = _register(client, "noti_m2", role="merchant")
    assert catalog.merchant_bind(muid, "S001")
    r = client.post(f"/merchant/orders/{oid}/logistics", headers=_h(mtok), json={"text": "包裹已揽收"})
    assert r.status_code == 200, r.text
    items = _notifies(client, token, type="logistics")
    assert items and items[0]["title"] == "物流更新"
    assert "包裹已揽收" in items[0]["body"]


def test_aftersale_and_review_hooks(client):
    token, uid = _register(client, "noti_buyer3")
    oid = _create_order(client, token)
    r = client.post("/pay", headers=_h(token), json={"order_id": oid})
    assert r.status_code == 200, r.text
    r = client.post(f"/orders/{oid}/action", json={"action": "ship"}, headers=_h(token))
    assert r.status_code == 200, r.text
    r = client.post(f"/orders/{oid}/action", json={"action": "complete"}, headers=_h(token))
    assert r.status_code == 200, r.text
    # 售后审核 → aftersale 通知
    r = client.post(
        f"/orders/{oid}/aftersale",
        headers=_h(token),
        json={"reason": "花材枯萎", "type": "refund"},
    )
    assert r.status_code == 200, r.text
    as_id = r.json()["aftersale"]["id"]
    atok, _ = _register(client, "noti_admin1", role="admin")
    r = client.post(f"/admin/aftersales/{as_id}/approve", headers=_h(atok))
    assert r.status_code == 200, r.text
    items = _notifies(client, token, type="aftersale")
    assert items and items[0]["title"] == "售后已通过"
    # 商家回复评价 → review_reply 通知
    mtok, muid = _register(client, "noti_m3", role="merchant")
    catalog.merchant_bind(muid, "S001")
    r = client.post("/reviews", headers=_h(token), json={"order_id": oid, "rating": 5, "content": "很香"})
    assert r.status_code == 200, r.text
    rv = client.get("/reviews", headers=_h(token))
    # 公开评价列表按秒级 created_at 排序可能与本秒其他测试评价并列 → 按订单精确锁定本人评价
    mine = [r for r in rv.json()["reviews"] if r["order_id"] == oid]
    assert mine, "应能找到本订单的评价"
    review_id = mine[0]["id"]
    r = client.post(f"/merchant/reviews/{review_id}/reply", headers=_h(mtok), json={"reply": "谢谢喜欢"})
    assert r.status_code == 200, r.text
    items = _notifies(client, token, type="review_reply")
    assert items and items[0]["title"] == "商家回复了你的评价"


def test_admin_broadcast_announcement(client):
    atok, _ = _register(client, "noti_admin2", role="admin")
    # 指定群体投放
    btok, buid = _register(client, "noti_buyer4")
    r = client.post(
        "/admin/notifications",
        headers=_h(atok),
        json={"title": "仅买家可见", "body": "", "user_ids": [buid]},
    )
    assert r.status_code == 200 and r.json()["sent"] == 1
    assert len(_notifies(client, btok, type="announcement", is_read=0)) == 1
    # 普通用户调 admin 广播 → 403
    r = client.post(
        "/admin/notifications", headers=_h(btok), json={"title": "越权", "body": ""}
    )
    assert r.status_code == 403


def test_list_filter_pagination_and_mark_read(client):
    token, uid = _register(client, "noti_buyer5")
    for i in range(5):
        notify_store.create_notification(uid, "system", f"消息{i}", f"正文{i}")
    # 类型过滤
    assert len(_notifies(client, token, type="system")) == 5
    assert len(_notifies(client, token, type="announcement")) == 0
    # 已读过滤
    assert len(_notifies(client, token, is_read=0)) == 5
    # 分页
    page1 = _notifies(client, token, limit=2, offset=0)
    page2 = _notifies(client, token, limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert page1[0]["id"] != page2[0]["id"]
    # 单条标记已读
    r = client.post("/notifications/mark-read", headers=_h(token), json={"ids": [page1[0]["id"]]})
    assert r.status_code == 200 and r.json()["updated"] == 1
    assert _unread(client, token) == 4
    # 重复标记不计数
    r = client.post("/notifications/mark-read", headers=_h(token), json={"ids": [page1[0]["id"]]})
    assert r.json()["updated"] == 0
    # 全部已读
    r = client.post("/notifications/mark-read", headers=_h(token), json={"all": True})
    assert r.status_code == 200 and r.json()["updated"] == 4
    assert _unread(client, token) == 0


def test_detail_ownership_and_cross_user_mark_read(client):
    ta, ua = _register(client, "noti_user_a")
    tb, ub = _register(client, "noti_user_b")
    notify_store.create_notification(ua, "system", "A的消息", "仅A可见")
    items = _notifies(client, ta)
    nid = items[0]["id"]
    # 本人详情 200
    r = client.get(f"/notifications/{nid}", headers=_h(ta))
    assert r.status_code == 200 and r.json()["notification"]["title"] == "A的消息"
    # 他人详情 404
    r = client.get(f"/notifications/{nid}", headers=_h(tb))
    assert r.status_code == 404
    # B 标记 A 的通知 → 0 条（不能影响他人）
    r = client.post("/notifications/mark-read", headers=_h(tb), json={"ids": [nid]})
    assert r.status_code == 200 and r.json()["updated"] == 0
    assert _unread(client, ta) == 1
    # 未登录 401
    assert client.get("/notifications").status_code == 401


def test_try_create_never_breaks_business(client, monkeypatch):
    """验收 2.5：通知写入失败只记日志，订单主流程不受影响。"""
    token, uid = _register(client, "noti_buyer6")
    calls = []

    def boom(*a, **kw):
        calls.append(a)
        raise RuntimeError("db down")

    monkeypatch.setattr(notify_store, "create_notification", boom)
    oid = _create_order(client, token)
    assert calls  # 通知确实被尝试写入过
    assert client.get(f"/orders/{oid}", headers=_h(token)).status_code == 200
