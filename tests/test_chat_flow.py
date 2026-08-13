"""/chat 端到端冒烟测试：走通「需求→选择→方案→确认→店铺→下单→pay_jump」。"""

import pytest
from fastapi.testclient import TestClient

from api import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:  # 触发 lifespan：init_db
        yield c


def _chat(c: TestClient, uid: str, msg: str) -> dict:
    r = c.post("/chat", json={"user_id": uid, "message": msg})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_order_flow(client: TestClient) -> None:
    """完整导购下单链路（Mock 引擎，零配置）。"""
    uid = "flow_001"
    # 1) 需求 → 现有/DIY 选择弹窗
    b1 = _chat(client, uid, "想给母亲买一束花，预算200元左右")
    assert b1["ui"] == "dialog_options"
    assert b1["stage"] == "select_mode"

    # 2) 选现有方案 → 方案卡片
    b2 = _chat(client, uid, "选现有方案")
    assert b2["ui"] == "plan_card"
    assert b2["stage"] == "view_plan"

    # 3) 确认 → 店铺卡片
    b3 = _chat(client, uid, "确认")
    assert b3["ui"] == "shop_card"
    assert b3["stage"] == "shop_recommend"

    # 4) 选店铺 → 支付跳转参数
    b4 = _chat(client, uid, "第一家")
    assert b4["ui"] == "pay_jump"
    assert b4["stage"] == "done"
    assert "order_id" in b4["data"]


def test_mode_switch_before_confirm(client: TestClient) -> None:
    """确认前可在现有方案与 DIY 间往返切换。"""
    uid = "switch_002"
    _chat(client, uid, "我想买花")            # → select_mode
    _chat(client, uid, "选现有方案")           # → view_plan
    b = _chat(client, uid, "还是想自己DIY吧")  # → diy_design
    assert b["stage"] == "diy_design"


def test_chitchat_does_not_trigger_tools(client: TestClient) -> None:
    """闲聊不触发工具、不推进流程。"""
    uid = "chat_003"
    b = _chat(client, uid, "你好呀")
    assert b["ui"] == "text"
    assert all(tc["name"] not in ("search_plans", "search_shops", "create_order") for tc in b["tool_calls"])


def test_reset_clears_session(client: TestClient) -> None:
    """重置接口生效。"""
    uid = "reset_004"
    _chat(client, uid, "想买花")
    r = client.post("/chat/reset", json={"user_id": uid})
    assert r.status_code == 200
    assert r.json()["reset"] is True


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["llm_mode"] == "mock"
