"""管理后台新增模块（M0/M2/M3/M4/M5）接口测试。

覆盖：
- M0：admin 提权端点（越权 403、非法角色 400）
- M2：用户列表/禁用/启用（禁用后登录被拒）
- M3：全局订单列表/状态干预
- M4：用户发起售后 → admin 列表 → 审核通过/拒绝/退款（payments 联动）
- M5：提交入驻 → admin 列表 → 通过（提权+建店）/拒绝
"""
import pytest
from fastapi.testclient import TestClient

import api
from security import set_user_role
from storage import catalog


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
        token = r.json()["token"]
        uid = r.json()["user_id"]
        if role != "user":
            set_user_role(uid, role)
        return token, uid
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    uid = r.json()["user_id"]
    if role != "user":
        set_user_role(uid, role)
    return token, uid


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client):
    token, _ = _register(client, "adm_o", role="admin")
    return token


def _create_and_pay(client, token, shop="S001", price=99):
    r = client.post(
        "/orders",
        headers=_h(token),
        json={"items": [{"plan_id": "P001", "name": "测试花束", "price": price, "qty": 1, "shop": shop}]},
    )
    assert r.status_code == 200, r.text
    oid = r.json()["order"]["order_id"]
    r = client.post("/pay", headers=_h(token), json={"order_id": oid})
    assert r.status_code == 200, r.text
    return oid


# ---------- M0 权限 ----------


def test_admin_role_endpoint_requires_admin(client):
    token, _ = _register(client, "adm_a")
    r = client.post("/admin/users/u1/role", json={"role": "admin"}, headers=_h(token))
    assert r.status_code == 403


def test_admin_set_role(client):
    admin_t = _admin_token(client)
    _, uid = _register(client, "adm_b")
    r = client.post(f"/admin/users/{uid}/role", json={"role": "merchant"}, headers=_h(admin_t))
    assert r.status_code == 200
    r = client.post(f"/admin/users/{uid}/role", json={"role": "hacker"}, headers=_h(admin_t))
    assert r.status_code == 400


# ---------- M2 用户管理 ----------


def test_admin_users_list_and_ban(client):
    admin_t = _admin_token(client)
    token, uid = _register(client, "adm_c")
    r = client.get("/admin/users", params={"keyword": "adm_c"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    # 禁用 → 登录被拒
    r = client.post(f"/admin/users/{uid}/ban", headers=_h(admin_t))
    assert r.status_code == 200
    r = client.post("/auth/login", json={"username": "adm_c", "password": "secret123"})
    assert r.status_code == 401
    # 解禁 → 恢复登录
    r = client.post(f"/admin/users/{uid}/unban", headers=_h(admin_t))
    assert r.status_code == 200
    r = client.post("/auth/login", json={"username": "adm_c", "password": "secret123"})
    assert r.status_code == 200


def test_banned_merchant_token_invalidated_immediately(client):
    """封禁即时生效：已发令牌在 merchant 端点被 403（不等 7 天过期）。"""
    admin_t = _admin_token(client)
    token, uid = _register(client, "adm_ban_m", role="merchant")
    assert catalog.merchant_bind(uid, "S001")
    # 封禁前：商家端点可访问
    r = client.get("/merchant/shops", headers=_h(token))
    assert r.status_code == 200
    # 封禁：现有令牌立即失效
    r = client.post(f"/admin/users/{uid}/ban", headers=_h(admin_t))
    assert r.status_code == 200
    r = client.get("/merchant/shops", headers=_h(token))
    assert r.status_code == 403
    r = client.get("/merchant/stats", headers=_h(token))
    assert r.status_code == 403


# ---------- M3 全局订单 ----------


def test_admin_orders_and_status_override(client):
    admin_t = _admin_token(client)
    user_t, _ = _register(client, "adm_d")
    oid = _create_and_pay(client, user_t)
    r = client.get("/admin/orders", headers=_h(admin_t))
    assert r.status_code == 200
    assert any(o["order_id"] == oid for o in r.json()["orders"])
    r = client.post(f"/admin/orders/{oid}/status", json={"status": "done"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert r.json()["order"]["status"] == "done"
    # 非法状态 400
    r = client.post(f"/admin/orders/{oid}/status", json={"status": "bogus"}, headers=_h(admin_t))
    assert r.status_code == 400


# ---------- M4 售后 ----------


def test_aftersale_flow(client):
    admin_t = _admin_token(client)
    user_t, _ = _register(client, "adm_e")
    oid = _create_and_pay(client, user_t)
    # 用户发起售后
    r = client.post(
        f"/orders/{oid}/aftersale",
        json={"type": "refund", "reason": "不想要了", "description": "花材品质不符"},
        headers=_h(user_t),
    )
    assert r.status_code == 200, r.text
    as_id = r.json()["aftersale"]["id"]
    # 未支付订单不可售后
    r = client.post(
        "/orders",
        headers=_h(user_t),
        json={"items": [{"plan_id": "P001", "name": "x", "price": 1, "qty": 1, "shop": "S001"}]},
    )
    oid2 = r.json()["order"]["order_id"]
    r = client.post(f"/orders/{oid2}/aftersale", json={"type": "refund"}, headers=_h(user_t))
    assert r.status_code == 400
    # 我的售后
    r = client.get("/me/aftersales", headers=_h(user_t))
    assert r.status_code == 200
    assert any(a["id"] == as_id for a in r.json()["aftersales"])
    # admin 列表
    r = client.get("/admin/aftersales", params={"status": "pending"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert any(a["id"] == as_id for a in r.json()["aftersales"])
    # 拒绝
    r = client.post(f"/admin/aftersales/{as_id}/reject", json={"note": "证据不足"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert r.json()["aftersale"]["status"] == "rejected"
    assert r.json()["aftersale"]["review_note"] == "证据不足"


def test_aftersale_refund_links_payment(client):
    admin_t = _admin_token(client)
    user_t, _ = _register(client, "adm_f")
    oid = _create_and_pay(client, user_t)
    r = client.post(f"/orders/{oid}/aftersale", json={"type": "return"}, headers=_h(user_t))
    as_id = r.json()["aftersale"]["id"]
    r = client.post(f"/admin/aftersales/{as_id}/refund", headers=_h(admin_t))
    assert r.status_code == 200
    assert r.json()["aftersale"]["status"] == "refunded"
    # payments 联动
    from storage.db import get_conn

    row = get_conn().execute(
        "SELECT status FROM payments WHERE order_id=?", (oid,)
    ).fetchone()
    assert row and row["status"] == "refunded"


# ---------- M5 商家入驻 ----------


def test_merchant_apply_flow(client):
    admin_t = _admin_token(client)
    user_t, uid = _register(client, "adm_g")
    r = client.post(
        "/merchant/apply",
        json={
            "shop_name": "测试花店",
            "contact_name": "张三",
            "contact_phone": "13800001111",
            "license_no": "L-001",
            "intro": "专注测试",
        },
        headers=_h(user_t),
    )
    assert r.status_code == 200, r.text
    app_id = r.json()["application"]["id"]
    # 重复申请被拒
    r = client.post("/merchant/apply", json={"shop_name": "测试花店2"}, headers=_h(user_t))
    assert r.status_code == 400
    # admin 列表
    r = client.get("/admin/merchant-applications", params={"status": "pending"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert any(a["id"] == app_id for a in r.json()["applications"])
    # 通过 → 提权 + 建店 + 绑定
    r = client.post(f"/admin/merchant-applications/{app_id}/approve", headers=_h(admin_t))
    assert r.status_code == 200
    assert r.json()["application"]["status"] == "approved"
    from security import get_user_role

    assert get_user_role(uid) == "merchant"
    assert catalog.merchant_shops(uid)
    # 已入驻列表
    r = client.get("/admin/merchants", headers=_h(admin_t))
    assert r.status_code == 200
    assert any(m["user_id"] == uid for m in r.json()["merchants"])
    # 清理测试创建的店铺，避免污染其他测试（如 test_catalog 的固定店铺数断言）
    for s in catalog.merchant_shops(uid):
        catalog.delete_shop(s["id"])


def test_merchant_apply_reject(client):
    admin_t = _admin_token(client)
    user_t, _ = _register(client, "adm_h")
    r = client.post("/merchant/apply", json={"shop_name": "被拒花店"}, headers=_h(user_t))
    app_id = r.json()["application"]["id"]
    r = client.post(
        f"/admin/merchant-applications/{app_id}/reject",
        json={"note": "执照不清晰"},
        headers=_h(admin_t),
    )
    assert r.status_code == 200
    assert r.json()["application"]["status"] == "rejected"
    assert r.json()["application"]["review_note"] == "执照不清晰"


# ---------- M6 评价审核 ----------


def _create_review(client, token, username):
    """下单→支付→发货→签收→评价，返回 review_id。"""
    token, _ = _register(client, username)
    oid = _create_and_pay(client, token)
    r = client.post(f"/orders/{oid}/action", json={"action": "ship"}, headers=_h(token))
    assert r.status_code == 200, r.text
    r = client.post(f"/orders/{oid}/action", json={"action": "complete"}, headers=_h(token))
    assert r.status_code == 200, r.text
    r = client.post(
        "/reviews",
        json={"order_id": oid, "rating": 4, "content": "测试评价内容"},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["review"]["id"]


def test_review_hide_show_delete(client):
    admin_t = _admin_token(client)
    rev_id = _create_review(client, None, "adm_i")
    # admin 列表可见
    r = client.get("/admin/reviews", params={"keyword": "测试评价"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert any(x["id"] == rev_id for x in r.json()["reviews"])
    # 隐藏 → C 端不再展示
    r = client.post(f"/admin/reviews/{rev_id}/hide", headers=_h(admin_t))
    assert r.status_code == 200
    r = client.get("/reviews")
    assert r.status_code == 200
    assert not any(x["id"] == rev_id for x in r.json()["reviews"])
    # 显示 → 恢复
    r = client.post(f"/admin/reviews/{rev_id}/show", headers=_h(admin_t))
    assert r.status_code == 200
    r = client.get("/reviews")
    assert any(x["id"] == rev_id for x in r.json()["reviews"])
    # 删除
    r = client.delete(f"/admin/reviews/{rev_id}", headers=_h(admin_t))
    assert r.status_code == 200
    r = client.get("/admin/reviews", headers=_h(admin_t))
    assert not any(x["id"] == rev_id for x in r.json()["reviews"])


# ---------- M8 数据看板 ----------


def test_admin_dashboard(client):
    admin_t = _admin_token(client)
    r = client.get("/admin/dashboard", headers=_h(admin_t))
    assert r.status_code == 200
    d = r.json()
    for k in ("gmv", "order_count", "user_count", "new_users_today", "top_plans", "top_shops", "order_trend"):
        assert k in d, k
    assert isinstance(d["top_plans"], list) and isinstance(d["order_trend"], list)
    # 未登录 401
    assert client.get("/admin/dashboard").status_code == 401


# ---------- M7 运营配置 ----------


def test_operations_config_flow(client):
    admin_t = _admin_token(client)
    # 默认（seed 兜底）
    r = client.get("/config")
    assert r.status_code == 200
    assert r.json()["delivery_options"] and r.json()["shipping_fee"] is not None
    # admin 改配送时段 + 运费 → 公开接口同步
    r = client.put(
        "/admin/config",
        json={"delivery_options": ["今天 20:00–22:00", "明天 08:00–10:00"], "shipping_fee": 8},
        headers=_h(admin_t),
    )
    assert r.status_code == 200, r.text
    assert r.json()["delivery_options"] == ["今天 20:00–22:00", "明天 08:00–10:00"]
    assert r.json()["shipping_fee"] == 8
    r = client.get("/config")
    assert r.json()["delivery_options"] == ["今天 20:00–22:00", "明天 08:00–10:00"]
    # 非法输入：Pydantic 校验拒绝（422）或业务校验（400）
    r = client.put("/admin/config", json={"shipping_fee": -1}, headers=_h(admin_t))
    assert r.status_code in (400, 422)
    # 未登录 401
    assert client.get("/admin/config").status_code == 401


def test_content_faqs_flow(client):
    admin_t = _admin_token(client)
    r = client.put(
        "/admin/content/faqs",
        json={"faqs": [{"q": "测试问题", "a": "测试答案"}]},
        headers=_h(admin_t),
    )
    assert r.status_code == 200
    r = client.get("/config")
    assert any(f["q"] == "测试问题" for f in r.json()["faqs"])
    # 公告
    r = client.put(
        "/admin/content/announcements",
        json={"announcements": [{"content": "平台公告：春节正常营业"}]},
        headers=_h(admin_t),
    )
    assert r.status_code == 200
    r = client.get("/config")
    assert any(a["content"].startswith("平台公告") for a in r.json()["announcements"])


def test_admin_categories_crud(client):
    admin_t = _admin_token(client)
    r = client.post("/admin/categories", json={"name": "后台测试分类"}, headers=_h(admin_t))
    assert r.status_code == 200, r.text
    cid = r.json()["category"]["id"]
    r = client.put(f"/admin/categories/{cid}", json={"name": "后台测试分类2"}, headers=_h(admin_t))
    assert r.status_code == 200
    assert r.json()["category"]["name"] == "后台测试分类2"
    r = client.delete(f"/admin/categories/{cid}", headers=_h(admin_t))
    assert r.status_code == 200
    assert client.get("/admin/categories", headers=_h(admin_t)).status_code == 200


def test_admin_shops_crud_and_location(client):
    """店铺管理（合作花店）：admin 可增删改，且能改 lat/lng/rating 影响首页排序。"""
    admin_t = _admin_token(client)
    r = client.post(
        "/admin/shops",
        json={
            "name": "后台测试花店",
            "rating": 4.2,
            "lat": 22.60,
            "lng": 114.30,
            "status": "营业中",
        },
        headers=_h(admin_t),
    )
    assert r.status_code == 200, r.text
    shop = r.json()["shop"]
    sid = shop["shop_id"]
    assert shop["name"] == "后台测试花店"
    assert shop["lat"] == 22.60

    # 更新：改 lat/lng/rating/地址（首页按距离+评分排序）
    r = client.put(
        f"/admin/shops/{sid}",
        json={"lat": 22.45, "lng": 114.10, "rating": 4.9, "address": "深圳市福田区测试路 1 号"},
        headers=_h(admin_t),
    )
    assert r.status_code == 200, r.text
    upd = r.json()["shop"]
    assert upd["lat"] == 22.45
    assert upd["lng"] == 114.10
    assert upd["rating"] == 4.9
    assert upd["address"] == "深圳市福田区测试路 1 号"

    # 普通用户访问 /admin/shops → 403；未登录 401
    u_tok, _ = _register(client, "adm_shop_u")
    assert client.get("/admin/shops", headers=_h(u_tok)).status_code == 403
    assert client.get("/admin/shops").status_code == 401

    # 删除
    r = client.delete(f"/admin/shops/{sid}", headers=_h(admin_t))
    assert r.status_code == 200
    assert client.get("/admin/shops", headers=_h(admin_t)).status_code == 200

