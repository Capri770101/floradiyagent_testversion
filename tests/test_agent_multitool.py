"""回归测试：DeepSeek 等模型会在同一轮返回多个工具调用，
必须打包进同一条 assistant 消息（否则 OpenAI 协议 400）。"""
import json

from agent import Agent
from config import Config
from engine.llm import LLMResult
from storage.db import Database
from storage.memory import Memory
from storage.repository import MockRepository


class FakeLLM:
    """第一次返回多工具调用，第二次记录收到的消息并正常收尾。"""

    def __init__(self):
        self.calls = 0
        self.captured = None

    def chat(self, messages, tools=None) -> LLMResult:
        self.calls += 1
        if self.calls == 1:
            return LLMResult(tool_calls=[
                {"id": "call_search", "type": "function",
                 "function": {"name": "search_plans", "arguments": json.dumps({"keyword": "母亲"}, ensure_ascii=False)}},
                {"id": "call_mem1", "type": "function",
                 "function": {"name": "save_memory", "arguments": json.dumps({"key": "budget", "value": "200"}, ensure_ascii=False)}},
                {"id": "call_mem2", "type": "function",
                 "function": {"name": "save_memory", "arguments": json.dumps({"key": "recipient", "value": "母亲"}, ensure_ascii=False)}},
            ])
        self.captured = list(messages)
        return LLMResult(tool_calls=[{
            "id": "call_resp", "type": "function",
            "function": {"name": "respond_to_user", "arguments": json.dumps({
                "reply": "为您找到方案，请看卡片。", "ui": "plan_card",
                "data": {"plan_id": "p1"}, "stage": "PLAN_CONFIRM"}, ensure_ascii=False)},
        }])


def test_multiple_tool_calls_batched(tmp_path):
    config = Config()
    config.max_iterations = 6
    db = Database(tmp_path / "t.db")
    db.init_schema()
    agent = Agent(config, FakeLLM(), Memory(db), MockRepository())

    resp = agent.chat("u-multi", "给母亲买花", "", "user")

    fake = agent.llm
    assert fake.calls == 2  # 多工具一轮 + 收尾一轮
    msgs = fake.captured

    assistant = [m for m in msgs if m["role"] == "assistant" and m.get("tool_calls")]
    # 所有工具调用必须在同一条 assistant 消息里（协议要求）
    assert len(assistant) == 1, [m["role"] for m in msgs]
    assert len(assistant[0]["tool_calls"]) == 3

    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert len(tool_msgs) == 3
    # 每个 tool_call_id 恰好有一条 tool 观察消息
    ids = {tc["id"] for tc in assistant[0]["tool_calls"]}
    assert ids == {tm["tool_call_id"] for tm in tool_msgs}
    # 消息顺序：assistant(tool_calls) 必须紧跟其 tool 观察消息
    assert msgs.index(assistant[0]) < msgs.index(tool_msgs[0])

    # 收尾响应正常
    assert resp.ui == "plan_card"
    assert resp.reply.startswith("为您找到方案")
    # 3 个工具调用都在审计记录里
    assert {t.name for t in resp.tool_calls} == {"search_plans", "save_memory"}