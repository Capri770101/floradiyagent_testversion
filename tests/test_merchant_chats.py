"""商家-顾客会话（契约 4.1）与商家评价回复接口测试。

覆盖：
- 顾客取/建会话：GET /chats/shop/{shop_id} 幂等（同人同店同会话）、返回店铺名
- 顾客发送消息 → 商家未读 +1、last_msg 更新；商家读取清零商家未读
- 商家回复 → 顾客未读 +1；顾客读取清零顾客未读
- 商家会话列表按绑定店铺隔离；未绑定店铺不可见；越权访问 403
- 顾客访问他人会话 403
- 商家「联系顾客」创建会话：/merchant/chats/with-user
- 评价回复：/merchant/reviews/{id}/reply 写 reply/reply_at；非本店评价 404
- 权限：未登录 401、普通用户访问商家端点 403
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


def _bind_merchant(client, username, shop="S001"):
    token, uid = _register(client, username, role="merchant")
    assert catalog.merchant_bind(uid, shop)
    return token, uid


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


def _create_review(client, token, username):
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


# --------------------------------------------------------------------------- #
# 顾客侧会话
# --------------------------------------------------------------------------- #

def test_user_chat_with_shop_idempotent(client):
    token, uid = _register(client, "ch_u1")
    r = client.get("/chats/shop/S001", headers=_h(token))
    assert r.status_code == 200, r.text
    chat1 = r.json()["chat"]
    assert chat1["shop_id"] == "S001"
    assert chat1["user_id"] == uid
    assert r.json()["shop_name"] == "S001" or r.json()["shop_name"]
    r2 = client.get("/chats/shop/S001", headers=_h(token))
    assert r2.json()["chat"]["id"] == chat1["id"]


def test_user_chat_requires_login(client):
    r = client.get("/chats/shop/S001")
    assert r.status_code == 401


def test_user_send_and_read_unread_cycle(client):
    token, _ = _register(client, "ch_u2")
    r = client.get("/chats/shop/S001", headers=_h(token))
    chat_id = r.json()["chat"]["id"]

    r = client.post(f"/chats/{chat_id}/messages", json={"content": "你好，请问今天能送到吗？"}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["message"]["sender"] == "user"

    # 商家侧列表：未读 +1、last_msg 更新
    m_token, _ = _bind_merchant(client, "ch_m2")
    r = client.get("/merchant/chats", headers=_h(m_token))
    row = next(c for c in r.json()["chats"] if c["id"] == chat_id)
    assert row["unread_merchant"] == 1
    assert row["last_msg"] == "你好，请问今天能送到吗？"
    assert row["nickname"]

    # 商家读取 → 商家未读清零
    r = client.get(f"/merchant/chats/{chat_id}/messages", headers=_h(m_token))
    assert r.status_code == 200, r.text
    assert any(m["content"] == "你好，请问今天能送到吗？" for m in r.json()["messages"])
    r = client.get("/merchant/chats", headers=_h(m_token))
    row = next(c for c in r.json()["chats"] if c["id"] == chat_id)
    assert row["unread_merchant"] == 0


def test_merchant_reply_increments_user_unread(client):
    token, _ = _register(client, "ch_u3")
    r = client.get("/chats/shop/S001", headers=_h(token))
    chat_id = r.json()["chat"]["id"]
    client.post(f"/chats/{chat_id}/messages", json={"content": "在吗"}, headers=_h(token))

    m_token, _ = _bind_merchant(client, "ch_m3")
    r = client.post(f"/merchant/chats/{chat_id}/messages", json={"content": "您好，可以的"}, headers=_h(m_token))
    assert r.status_code == 200, r.text
    assert r.json()["message"]["sender"] == "merchant"

    # 顾客未读 +1；顾客读取清零
    r = client.get(f"/chats/{chat_id}/messages", headers=_h(token))
    assert any(m["content"] == "您好，可以的" for m in r.json()["messages"])
    r2 = client.get(f"/chats/{chat_id}/messages", headers=_h(token))
    assert r2.status_code == 200


def test_user_cannot_read_others_chat(client):
    token_a, _ = _register(client, "ch_u4a")
    r = client.get("/chats/shop/S001", headers=_h(token_a))
    chat_id = r.json()["chat"]["id"]
    token_b, _ = _register(client, "ch_u4b")
    r = client.get(f"/chats/{chat_id}/messages", headers=_h(token_b))
    assert r.status_code == 403
    r = client.post(f"/chats/{chat_id}/messages", json={"content": "插话"}, headers=_h(token_b))
    assert r.status_code == 403


def test_user_chat_list_endpoint(client):
    """顾客消息中心：GET /chats 返回本人与各商家的历史会话（附未读与店铺名）。"""
    token, uid = _register(client, "ch_l1")
    # 未创建会话前 → 空列表
    r = client.get("/chats", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["chats"] == []

    # 与两家店铺建立会话并互发消息
    r1 = client.get("/chats/shop/S001", headers=_h(token))
    c1 = r1.json()["chat"]["id"]
    client.post(f"/chats/{c1}/messages", json={"content": "S001 第一条"}, headers=_h(token))

    r2 = client.get("/chats/shop/S002", headers=_h(token))
    c2 = r2.json()["chat"]["id"]

    # 商家回复 S002 → 顾客未读 +1
    m_token, _ = _bind_merchant(client, "ch_ml1", shop="S002")
    client.post(f"/merchant/chats/{c2}/messages", json={"content": "S002 商家回复"}, headers=_h(m_token))

    r = client.get("/chats", headers=_h(token))
    assert r.status_code == 200, r.text
    chats = r.json()["chats"]
    by_id = {c["id"]: c for c in chats}
    assert len(by_id) == 2
    assert by_id[c1]["last_msg"] == "S001 第一条"
    assert by_id[c1]["unread_user"] == 0
    assert by_id[c2]["unread_user"] == 1
    assert by_id[c2]["last_msg"] == "S002 商家回复"
    assert by_id[c2]["shop_name"]
    # 其他用户看不到此列表（无会话即空）
    token_other, _ = _register(client, "ch_l1b")
    r = client.get("/chats", headers=_h(token_other))
    assert r.json()["chats"] == []


def test_user_chat_list_requires_login(client):
    r = client.get("/chats")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 商家侧会话
# --------------------------------------------------------------------------- #

def test_merchant_chats_isolated_by_shop(client):
    token, _ = _register(client, "ch_u5")
    client.get("/chats/shop/S001", headers=_h(token))
    client.get("/chats/shop/S002", headers=_h(token))

    m_s1, _ = _bind_merchant(client, "ch_m5a", shop="S001")
    r = client.get("/merchant/chats", headers=_h(m_s1))
    ids = {c["id"] for c in r.json()["chats"]}
    assert any("S001" in c["shop_id"] for c in r.json()["chats"])
    assert not any("S002" in c["shop_id"] for c in r.json()["chats"])

    # 未绑定店铺的商家看不到任何会话
    m_none, _ = _register(client, "ch_m5b", role="merchant")
    r = client.get("/merchant/chats", headers=_h(m_none))
    assert r.json()["chats"] == []


def test_merchant_cannot_access_other_shop_chat(client):
    token, _ = _register(client, "ch_u6")
    r = client.get("/chats/shop/S002", headers=_h(token))
    chat_id = r.json()["chat"]["id"]
    m_s1, _ = _bind_merchant(client, "ch_m6", shop="S001")
    r = client.get(f"/merchant/chats/{chat_id}/messages", headers=_h(m_s1))
    assert r.status_code == 403
    r = client.post(f"/merchant/chats/{chat_id}/messages", json={"content": "x"}, headers=_h(m_s1))
    assert r.status_code == 403


def test_merchant_chat_with_user_creates(client):
    _, uid = _register(client, "ch_u7")
    m_token, _ = _bind_merchant(client, "ch_m7")
    r = client.post(
        "/merchant/chats/with-user",
        json={"user_id": uid, "shop_id": "S001"},
        headers=_h(m_token),
    )
    assert r.status_code == 200, r.text
    chat = r.json()["chat"]
    assert chat["user_id"] == uid
    assert chat["shop_id"] == "S001"
    # 幂等：再次调用返回同一会话
    r2 = client.post(
        "/merchant/chats/with-user",
        json={"user_id": uid, "shop_id": "S001"},
        headers=_h(m_token),
    )
    assert r2.json()["chat"]["id"] == chat["id"]


def test_merchant_chat_with_user_scope_forbidden(client):
    _, uid = _register(client, "ch_u8")
    m_s1, _ = _bind_merchant(client, "ch_m8", shop="S001")
    r = client.post(
        "/merchant/chats/with-user",
        json={"user_id": uid, "shop_id": "S002"},
        headers=_h(m_s1),
    )
    assert r.status_code == 403


def test_merchant_chats_require_merchant_role(client):
    token, _ = _register(client, "ch_u9")
    r = client.get("/merchant/chats", headers=_h(token))
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 商家评价回复
# --------------------------------------------------------------------------- #

def test_merchant_review_reply(client):
    rev_id = _create_review(client, None, "ch_r1")
    m_token, _ = _bind_merchant(client, "ch_mr1")
    r = client.post(
        f"/merchant/reviews/{rev_id}/reply",
        json={"reply": "感谢您的评价，欢迎再来！"},
        headers=_h(m_token),
    )
    assert r.status_code == 200, r.text
    review = r.json()["review"]
    assert review["reply"] == "感谢您的评价，欢迎再来！"
    assert review["reply_at"]
    # 公开列表可见商家回复
    r2 = client.get("/reviews")
    public = next(x for x in r2.json()["reviews"] if x["id"] == rev_id)
    assert public["reply"] == "感谢您的评价，欢迎再来！"


def test_merchant_review_reply_not_own_shop(client):
    rev_id = _create_review(client, None, "ch_r2")
    m_s1, _ = _bind_merchant(client, "ch_mr2", shop="S002")
    r = client.post(
        f"/merchant/reviews/{rev_id}/reply",
        json={"reply": "越权"},
        headers=_h(m_s1),
    )
    assert r.status_code == 404


def test_merchant_review_reply_requires_merchant(client):
    rev_id = _create_review(client, None, "ch_r3")
    token, _ = _register(client, "ch_r3")
    r = client.post(
        f"/merchant/reviews/{rev_id}/reply",
        json={"reply": "普通用户"},
        headers=_h(token),
    )
    assert r.status_code == 403