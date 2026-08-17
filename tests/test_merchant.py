"""商家端接口：经营统计、订单列表（按店隔离）、代发货、评价列表、上传图片。

覆盖「商家端」后端链路：/merchant/stats 汇总订单/GMV/待发货/评价、
/merchant/orders 按店铺/状态过滤、/merchant/orders/{id}/ship 代发货（不受归属限制）、
/merchant/reviews 列表、/merchant/upload 图片上传；
权限与隔离：未登录 401、普通用户 403、merchant 角色放行、
未绑定店铺商家数据为空、越权访问未绑定店铺 403、admin 不受绑定限制。
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


def _register(client, username, role="merchant", bind=None):
    r = client.post(
        "/auth/register",
        json={"username": username, "password": "secret123", "nickname": username},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    uid = r.json()["user_id"]
    if role != "user":
        set_user_role(uid, role)
    if bind:
        assert catalog.merchant_bind(uid, bind)
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
    token = _register(client, "mer_a", bind="S001")
    _create_and_pay(client, token, shop="S001", price=99)
    r = client.get("/merchant/stats", headers=_merchant_headers(token))
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["order_count"] >= 1
    assert stats["gmv"] >= 99
    assert stats["pending_ship"] >= 1
    assert "shops" in stats


def test_merchant_orders_filter_by_shop_and_status(client):
    token = _register(client, "mer_b", bind="S001")
    _create_and_pay(client, token, shop="S001", price=199)
    r = client.get(
        "/merchant/orders",
        params={"shop_id": "S001", "status": "paid"},
        headers=_merchant_headers(token),
    )
    assert r.status_code == 200
    orders = r.json()["orders"]
    assert all(o["shop_id"] == "S001" and o["status"] == "paid" for o in orders)
    # 状态过滤：done 为空
    r = client.get("/merchant/orders", params={"status": "done"}, headers=_merchant_headers(token))
    assert all(o["status"] == "done" for o in r.json()["orders"])


def test_merchant_ship_any_user_order(client):
    token = _register(client, "mer_c", bind="S001")
    oid = _create_and_pay(client, token, shop="S001")
    r = client.post(f"/merchant/orders/{oid}/ship", headers=_merchant_headers(token))
    assert r.status_code == 200, r.text
    assert r.json()["order"]["status"] == "shipped"
    # 已发货再代发 → 400 状态机拒绝
    r = client.post(f"/merchant/orders/{oid}/ship", headers=_merchant_headers(token))
    assert r.status_code == 400


def test_merchant_reviews(client):
    token = _register(client, "mer_d", bind="S001")
    _create_and_pay(client, token, shop="S001")
    r = client.get("/merchant/reviews", headers=_merchant_headers(token))
    assert r.status_code == 200
    assert isinstance(r.json()["reviews"], list)


# ---------- 按店隔离 ----------


def test_merchant_without_binding_sees_nothing(client):
    """未绑定店铺的商家看不到任何数据（包括自己下的单，隔离到店）。"""
    token = _register(client, "mer_e")
    before = client.get("/merchant/stats", headers=_merchant_headers(token)).json()
    _create_and_pay(client, token, shop="S001")  # 自己下单也不可见
    after = client.get("/merchant/stats", headers=_merchant_headers(token)).json()
    assert after["order_count"] == before["order_count"] == 0
    assert after["shops"] == []
    r = client.get("/merchant/orders", headers=_merchant_headers(token))
    assert r.json()["orders"] == []
    r = client.get("/merchant/reviews", headers=_merchant_headers(token))
    assert r.json()["reviews"] == []


def test_merchant_scope_isolation(client):
    """绑定 S001 的商家看不到 S002 的订单（S002 是另一家店）。"""
    token = _register(client, "mer_f", bind="S001")
    before = client.get("/merchant/stats", headers=_merchant_headers(token)).json()
    _create_and_pay(client, token, shop="S002", price=199)
    after = client.get("/merchant/stats", headers=_merchant_headers(token)).json()
    assert after["order_count"] == before["order_count"]
    assert after["gmv"] == before["gmv"]
    # 显式按 S002 过滤 → 403（无权）
    r = client.get("/merchant/orders", params={"shop_id": "S002"}, headers=_merchant_headers(token))
    assert r.status_code == 403


def test_merchant_shops_endpoint(client):
    token = _register(client, "mer_g", bind="S001")
    r = client.get("/merchant/shops", headers=_merchant_headers(token))
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["shops"]] == ["S001"]


def test_admin_sees_all_shops(client):
    token = _register(client, "mer_admin", role="admin")
    r = client.get("/merchant/shops", headers=_merchant_headers(token))
    assert r.status_code == 200
    assert len(r.json()["shops"]) >= 1


def test_merchant_plans_forbidden_outside_scope(client):
    token = _register(client, "mer_h", bind="S001")
    r = client.get("/merchant/plans", params={"shop_id": "S002"}, headers=_merchant_headers(token))
    assert r.status_code == 403


# ---------- 上传 ----------


def test_merchant_upload_image(client, tmp_path):
    token = _register(client, "mer_i", bind="S001")
    r = client.post(
        "/merchant/upload",
        headers=_merchant_headers(token),
        files={"file": ("pic.jpg", b"\xff\xd8\xff\xe0fakejpg", "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("/uploads/m")
    assert url.endswith(".jpg")
    # 静态托管可访问
    r = client.get(url)
    assert r.status_code == 200
    assert r.content == b"\xff\xd8\xff\xe0fakejpg"


def test_merchant_upload_rejects_bad_type(client):
    token = _register(client, "mer_j", bind="S001")
    r = client.post(
        "/merchant/upload",
        headers=_merchant_headers(token),
        files={"file": ("evil.exe", b"MZfake", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_merchant_upload_rejects_oversize(client):
    token = _register(client, "mer_k", bind="S001")
    r = client.post(
        "/merchant/upload",
        headers=_merchant_headers(token),
        files={"file": ("big.png", b"0" * (5 * 1024 * 1024 + 1), "image/png")},
    )
    assert r.status_code == 400


def test_merchant_upload_requires_login(client):
    r = client.post("/merchant/upload", files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert r.status_code == 401


# ---------- P1：订单关键词 / 日期筛选 ----------


def test_merchant_orders_keyword_filter(client):
    """按商品名关键词过滤：命中 items 快照 JSON（兼容 order_items 为空）。"""
    token = _register(client, "mer_l", bind="S001")
    _create_and_pay(client, token, shop="S001", price=66)  # P001 = 康乃馨感恩花束
    r = client.get(
        "/merchant/orders",
        params={"keyword": "康乃馨"},
        headers=_merchant_headers(token),
    )
    assert r.status_code == 200
    orders = r.json()["orders"]
    assert orders, "关键词应命中订单"
    assert all("康乃馨" in ",".join(i.get("name", "") for i in o["items"]) for o in orders)


def test_merchant_orders_date_filter(client):
    """按日期范围过滤：created_at 兼容 ISO 与空格两种格式。"""
    token = _register(client, "mer_m", bind="S001")
    _create_and_pay(client, token, shop="S001", price=88)
    today = __import__("datetime").date.today().isoformat()
    r = client.get(
        "/merchant/orders",
        params={"date_from": today, "date_to": today},
        headers=_merchant_headers(token),
    )
    assert r.status_code == 200
    assert r.json()["orders"], "今日订单应被日期范围命中"


# ---------- P1：商品分类管理 ----------


def test_merchant_categories_crud(client):
    token = _register(client, "mer_n", bind="S001")
    h = _merchant_headers(token)
    # 列表（种子分类含 plan_count）
    r = client.get("/merchant/categories", headers=h)
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert cats and "plan_count" in cats[0]
    # 新增
    r = client.post("/merchant/categories", json={"name": "测试分类"}, headers=h)
    assert r.status_code == 200, r.text
    cid = r.json()["category"]["id"]
    # 重名拒绝
    r = client.post("/merchant/categories", json={"name": "测试分类"}, headers=h)
    assert r.status_code == 400
    # 改名
    r = client.put(f"/merchant/categories/{cid}", json={"name": "测试分类2"}, headers=h)
    assert r.status_code == 200
    assert r.json()["category"]["name"] == "测试分类2"
    # 删除
    r = client.delete(f"/merchant/categories/{cid}", headers=h)
    assert r.status_code == 200
    # 未登录 401
    assert client.get("/merchant/categories").status_code == 401


# ---------- P1：店铺装修（封面 / Logo / 营业时间等）----------


def test_merchant_update_shop_decoration(client):
    token = _register(client, "mer_o", bind="S001")
    h = _merchant_headers(token)
    r = client.put(
        "/merchant/shop/S001",
        json={
            "cover": "/uploads/mcover.jpg",
            "logo": "/uploads/mlogo.jpg",
            "hours": "08:00 - 20:00",
            "address": "测试路 1 号",
            "notice": "测试公告",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    # stats.shops 应带完整装修字段（店铺设置表单数据源）
    r = client.get("/merchant/stats", headers=h)
    assert r.status_code == 200
    shop = next(s for s in r.json()["shops"] if s["id"] == "S001")
    assert shop["cover"] == "/uploads/mcover.jpg"
    assert shop["logo"] == "/uploads/mlogo.jpg"
    assert shop["hours"] == "08:00 - 20:00"
    assert shop["address"] == "测试路 1 号"
    assert shop["notice"] == "测试公告"
    # C 端店铺详情也带装修字段
    r = client.get("/shops/S001")
    assert r.status_code == 200
    d = r.json()["shop"]
    assert d["cover"] == "/uploads/mcover.jpg"
    assert d["logo"] == "/uploads/mlogo.jpg"
    assert d["hours"] == "08:00 - 20:00"
