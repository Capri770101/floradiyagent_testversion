"""用户系统测试：注册 / 登录 / 资料 / 数据隔离。

验证「每个用户的数据独立」：A 创建的会话/购物车，B 用自己令牌读取不到。
注意：password_hash 用 pbkdf2 存储，断言库中不存在明文密码。
"""

import pytest
from fastapi.testclient import TestClient

import api
import security


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as c:  # 触发 lifespan：init_db + 迁移
        yield c


def _register(client: TestClient, username: str, password: str = "secret123") -> dict:
    r = client.post(
        "/auth/register",
        json={"username": username, "password": password, "nickname": username},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_register_issues_token_and_user_id(client: TestClient) -> None:
    body = _register(client, "alice")
    assert body["token"]
    assert body["user_id"].startswith("u_")
    assert security.verify_token(body["token"]) == body["user_id"]


def test_duplicate_username_rejected(client: TestClient) -> None:
    _register(client, "bob")
    r = client.post(
        "/auth/register", json={"username": "bob", "password": "secret123"}
    )
    assert r.status_code == 409


def test_login_wrong_password_fails(client: TestClient) -> None:
    _register(client, "carol", "secret123")
    r = client.post(
        "/auth/login", json={"username": "carol", "password": "wrong"}
    )
    assert r.status_code == 401


def test_login_success_and_me(client: TestClient) -> None:
    reg = _register(client, "dave", "secret123")
    r = client.post(
        "/auth/login", json={"username": "dave", "password": "secret123"}
    )
    assert r.status_code == 200
    token = r.json()["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["id"] == reg["user_id"]


def test_password_not_stored_plaintext(client: TestClient) -> None:
    _register(client, "erin", "secret123")
    from storage.db import get_conn

    row = get_conn().execute(
        "SELECT password_hash FROM users WHERE username=?", ("erin",)
    ).fetchone()
    assert row["password_hash"]
    assert "secret123" not in row["password_hash"]  # pbkdf2 哈希，非明文


def test_data_isolation_between_users(client: TestClient) -> None:
    a = _register(client, "userA", "secret123")
    b = _register(client, "userB", "secret123")
    a_headers = {"Authorization": f"Bearer {a['token']}"}
    b_headers = {"Authorization": f"Bearer {b['token']}"}

    # A 新建会话
    c = client.post("/conversations", headers=a_headers, json={"title": "A的对话"})
    assert c.status_code == 200
    cid = c.json()["conversation_id"]

    # B 的会话列表应为空，且读不到 A 的会话
    b_list = client.get("/conversations", headers=b_headers)
    assert b_list.status_code == 200
    assert b_list.json()["conversations"] == []
    b_get = client.get(
        f"/conversations/{cid}/messages", headers=b_headers, params={"user_id": b["user_id"]}
    )
    assert b_get.status_code == 404  # 归属校验拦截

    # A 能读到自己的会话
    a_list = client.get("/conversations", headers=a_headers)
    assert any(x["id"] == cid for x in a_list.json()["conversations"])
