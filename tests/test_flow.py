"""端到端冒烟测试：用 mock 大模型走通 需求->弹窗->方案->切换DIY->确认->店铺->下单->支付跳转。"""
import time

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

TEST_USER = "test-flower-user"


def _reset(uid: str = TEST_USER) -> None:
    resp = client.post("/chat/reset", json={"user_id": uid})
    assert resp.status_code == 200


def _chat(message: str, session_id=None, uid: str = TEST_USER) -> dict:
    resp = client.post("/chat", json={
        "user_id": uid, "message": message, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_full_purchase_flow():
    _reset()

    # 1. 需求分析 -> 弹窗询问（现有方案 / DIY）
    r = _chat("我想给母亲买一束花，预算 200 元左右")
    assert r["ui"] == "dialog_options", r
    assert {o["value"] for o in r["data"]["options"]} == {"existing", "diy"}
    session_id = r["session_id"]
    assert session_id

    # 2. 选择现有方案 -> 商家方案卡片
    r = _chat("看下现有方案", session_id=session_id)
    assert r["ui"] == "plan_card", r
    assert r["data"]["plan_type"] == "existing"
    assert r["data"]["effect_image_url"] or r["data"]["plan_id"]

    # 3. 确认前切换到 DIY -> DIY 方案卡片
    r = _chat("切换成 DIY 定制试试", session_id=session_id)
    assert r["ui"] == "plan_card", r
    assert r["data"]["plan_type"] == "diy"

    # 4. 请求效果图 -> 进入生图确认阶段（不直接提交任务）
    r = _chat("帮我生成效果图", session_id=session_id)
    assert r["ui"] == "dialog_options", r
    assert any(o["value"] in ("yes", "no") for o in r["data"]["options"]), r

    # 4b. 用户明确同意 -> 提交任务 -> 轮询完成
    r = _chat("好的，生成吧", session_id=session_id)
    assert r["ui"] == "text" and "task_id" in r["data"], r
    task_id = r["data"]["task_id"]
    task = {"status": "pending"}
    for _ in range(10):
        t = client.get(f"/tasks/{task_id}")
        assert t.status_code == 200
        task = t.json()
        if task["status"] != "pending":
            break
        time.sleep(0.2)
    assert task["status"] == "done", task
    assert task["result_url"]

    # 5. 确认方案 -> 店铺推荐
    r = _chat("确认这个方案", session_id=session_id)
    assert r["ui"] == "shop_card", r
    assert r["data"]["shops"], r

    # 6. 选择店铺下单 -> 支付跳转
    r = _chat("确认，就这家吧", session_id=session_id)
    assert r["ui"] == "pay_jump", r
    assert r["data"]["order_id"] and r["data"]["page_path"], r
    assert r["data"]["params"]["order_id"] == r["data"]["order_id"]
    # 下单工具调用应被记录到 tool_calls
    assert any(tc["name"] == "create_order" for tc in r["tool_calls"]), r["tool_calls"]


def test_casual_chat_and_reset():
    _reset()
    r = _chat("你好呀")
    assert r["ui"] in ("dialog_options", "text")
    # 重置后历史清空：同一用户从模拟对话重来仍可正常响应
    _reset()
    r = _chat("今天天气怎么样")
    assert r["reply"]


def test_invalid_session():
    resp = client.post("/chat", json={"user_id": TEST_USER, "session_id": "no-such-session",
                                      "message": "hi"})
    assert resp.status_code == 200
    assert "会话不存在" in resp.json()["reply"]