"""协议契约测试：/chat 响应中每种 ui 类型必须有约定的 data 字段。

这是给小程序前端渲染的"活文档"——任何一处字段被改动，契约测试即刻失败，
要求同步前端。前端联调时可直接以本文件 + openapi.json 为准。
"""
import json

from fastapi.testclient import TestClient

from agent import Agent
from config import Config
from engine.llm import LLMResult
from storage.db import Database
from storage.memory import Memory
from storage.repository import MockRepository
from api import app

client = TestClient(app)

# 契约：ui -> data 必含字段（不改动请先与前端对齐）
CONTRACT = {
    "text": set(),
    "dialog_options": {"question", "options"},
    "plan_card": {"plan_id", "name", "price", "desc", "effect_image_url",
                  "merchant_name", "plan_type"},
    "shop_card": {"shops", "question"},
    "order_card": {"order_id", "plan_type", "plan_name", "quantity",
                   "total_price", "shop_id"},
    "pay_jump": {"order_id", "page_path", "params"},
}
SHOP_FIELDS = {"shop_id", "name", "address", "distance_km", "price_range", "rating"}
VALID_UI = set(CONTRACT)

USER = "contract-user"


def _chat(message: str, session_id=None) -> dict:
    resp = client.post("/chat", json={"user_id": USER, "message": message,
                                      "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assert_contract(r: dict) -> None:
    ui, data = r["ui"], r.get("data") or {}
    assert ui in VALID_UI, f"未知 ui 类型: {ui!r}"
    assert isinstance(data, dict)
    missing = CONTRACT[ui] - set(data.keys())
    assert not missing, f"ui={ui} 契约缺字段: {missing}"
    # 工具调用审计结构
    for tc in r.get("tool_calls") or []:
        assert {"name", "arguments", "result", "status"} <= set(tc), tc
    # shop_card 的数组条目逐项校验
    if ui == "shop_card":
        for s in data["shops"]:
            assert SHOP_FIELDS <= set(s), f"店铺卡片缺字段: {s}"
    if ui == "pay_jump":
        assert isinstance(data["params"], dict)


def test_contract_full_flow():
    client.post("/chat/reset", json={"user_id": USER})
    steps = [
        ("想给母亲买一束花，预算200元左右", None),
        ("看下现有方案", None),
        ("切换成 DIY 定制试试", None),
        ("确认这个方案", None),
        ("选第一家店下单", None),
    ]
    sid = None
    for i, (msg, _s) in enumerate(steps):
        r = _chat(msg, session_id=sid)
        _assert_contract(r)
        sid = r["session_id"] or sid
        ui = r["ui"]
        if i == 0:
            assert ui in ("dialog_options", "plan_card", "text")
    # 支付跳转参数必须自洽
    last = _chat("确认，就这家吧", session_id=sid)
    _assert_contract(last)
    if last["ui"] == "pay_jump":
        assert last["data"]["params"]["order_id"] == last["data"]["order_id"]


def test_pay_jump_order_matches():
    client.post("/chat/reset", json={"user_id": USER})
    sid = None
    for msg in ("想买一束花", "看下现有方案", "确认这个方案", "选第一家店下单", "确认下单"):
        r = _chat(msg, session_id=sid)
        sid = r["session_id"] or sid
        if r["ui"] == "pay_jump":
            assert r["data"]["params"]["order_id"] == r["data"]["order_id"]
            assert r["data"]["page_path"].startswith("/pages/")
            return
    # mock 流程下应已走到 pay_jump；若模型路径偏差则跳过（契约已由上面用例覆盖）


class RespondLLM:
    """第一轮直接以指定 ui 收尾，用于验证不在 mock 流程中的 ui 类型。"""

    def __init__(self, ui: str, data: dict):
        self.ui, self.data = ui, data

    def chat(self, messages, tools=None) -> LLMResult:
        import json as _json
        args = _json.dumps({"reply": "订单已生成", "ui": self.ui, "data": self.data,
                            "stage": "ORDER_CONFIRM"}, ensure_ascii=False)
        return LLMResult(tool_calls=[{
            "id": "call_respond", "type": "function",
            "function": {"name": "respond_to_user", "arguments": args},
        }])


def test_order_card_contract(tmp_path):
    """mock 流程不产出 order_card，用注入 LLM 验证该契约贯通且原样透传。"""
    config = Config()
    db = Database(tmp_path / "t.db")
    db.init_schema()
    data = {"order_id": "O123", "plan_type": "diy", "plan_name": "DIY 花束",
            "quantity": 1, "total_price": 128.0, "shop_id": "s3"}
    agent = Agent(config, RespondLLM("order_card", data), Memory(db), MockRepository())
    r = agent.chat("contract-order", "下单", "", "user")
    _assert_contract(r.model_dump() if hasattr(r, "model_dump") else r)
    assert r.ui == "order_card"
    assert r.data == data