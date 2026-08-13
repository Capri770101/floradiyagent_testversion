"""异常注入测试：LLM 输出各类非法内容时，智能体必须优雅降级而非崩溃/死循环。"""
import json

import pytest

from agent import Agent
from config import Config
from engine.llm import LLMError, LLMResult
from storage.db import Database
from storage.memory import Memory
from storage.repository import MockRepository
from tools import TOOL_REGISTRY, register_tool


def _agent(llm, tmp_path, max_iterations: int = 3) -> Agent:
    config = Config()
    config.max_iterations = max_iterations
    db = Database(tmp_path / "t.db")
    db.init_schema()
    return Agent(config, llm, Memory(db), MockRepository())


def _respond(reply="好的", ui="text", stage="ANALYZE", data=None) -> LLMResult:
    args = json.dumps({"reply": reply, "ui": ui, "data": data or {},
                       "stage": stage}, ensure_ascii=False)
    return LLMResult(tool_calls=[{
        "id": "call_respond", "type": "function",
        "function": {"name": "respond_to_user", "arguments": args},
    }])


class ScriptedLLM:
    """按序返回预设结果；记录每次收到的消息。"""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(list(messages))
        return self.results.pop(0)


def test_malformed_tool_arguments(tmp_path):
    """arguments 不是合法 JSON：记录解析错误并正常续跑。"""
    bad = LLMResult(tool_calls=[{
        "id": "c1", "type": "function",
        "function": {"name": "search_plans", "arguments": "{{{ not json"},
    }])
    llm = ScriptedLLM(bad, _respond("继续"))
    resp = _agent(llm, tmp_path).chat("u1", "查一下", "", "user")
    assert resp.reply == "继续"
    assert any(t.name == "search_plans" and t.status == "error" for t in resp.tool_calls)
    # 解析错误被喂回给模型：下一轮收到携带错误说明的 tool 观察消息
    assert len(llm.calls) >= 2
    last_tool = [m for m in llm.calls[-1] if m["role"] == "tool"]
    assert last_tool and "参数解析失败" in last_tool[0]["content"]


def test_unknown_tool_name(tmp_path):
    """未知工具名：返回结构化错误、记录失败、循环继续。"""
    unknown = LLMResult(tool_calls=[{
        "id": "c2", "type": "function",
        "function": {"name": "no_such_tool", "arguments": "{}"},
    }])
    llm = ScriptedLLM(unknown, _respond("我换个说法吧"))
    resp = _agent(llm, tmp_path).chat("u2", "喂", "", "user")
    assert resp.reply == "我换个说法吧"
    rec = [t for t in resp.tool_calls if t.name == "no_such_tool"]
    assert rec and rec[0].status == "ok"
    assert "工具不存在" in rec[0].result


def test_tool_raises_exception(tmp_path):
    """工具抛异常：execute_tool 捕获并转结构化错误，不中断主循环。"""
    def _boom(**kwargs):
        raise RuntimeError("boom!")

    register_tool("boom_tool", "测试用崩溃工具",
                  {"type": "object", "properties": {}}, _boom)
    try:
        extracted = LLMResult(tool_calls=[{
            "id": "c3", "type": "function",
            "function": {"name": "boom_tool", "arguments": "{}"},
        }])
        llm = ScriptedLLM(extracted, _respond("收到"))
        resp = _agent(llm, tmp_path).chat("u3", "触发", "", "user")
        assert resp.reply == "收到"
        assert "boom" in resp.tool_calls[-1].result
    finally:
        TOOL_REGISTRY.pop("boom_tool", None)


def test_empty_responses_hits_max_iterations(tmp_path):
    """LLM 一直给空响应：达到迭代上限后友好收尾，不死循环。"""
    llm = ScriptedLLM(LLMResult(), LLMResult(), LLMResult(), LLMResult())
    resp = _agent(llm, tmp_path, max_iterations=3).chat("u4", "说话", "", "user")
    assert resp.ui == "text"
    assert resp.reply
    assert len(llm.calls) == 3


def test_llm_error_fallback(tmp_path):
    """LLM 调用异常：返回"服务暂时不可用"，不 500。"""
    class BoomLLM:
        def chat(self, messages, tools=None):
            raise LLMError("网络断了")

    resp = _agent(BoomLLM(), tmp_path).chat("u5", "hi", "", "user")
    assert "稍后再试" in resp.reply


def test_invalid_stage_clamped(tmp_path):
    """模型输出未知阶段名：钳制回当前阶段，正常返回。"""
    llm = ScriptedLLM(_respond("好的", ui="text", stage="NOT_A_STAGE"))
    resp = _agent(llm, tmp_path).chat("u6", "hello", "", "user")
    assert resp.reply == "好的"
    assert "保持" in resp.reply or resp.ui in ("text",)


def test_invalid_transition_clamped(tmp_path):
    """模型跳过阶段（DONE 直接回 ANALYZE 前面的非法路径外）会被钳制。"""
    # 从 ANALYZE 一步跳到 ORDER_CONFIRM（非法），应钳制回 ANALYZE
    llm = ScriptedLLM(_respond("下单吧", ui="text", stage="ORDER_CONFIRM"))
    resp = _agent(llm, tmp_path).chat("u7", "直接下单", "", "user")
    assert "保持" in resp.reply


def test_casual_text_without_tools(tmp_path):
    """无工具调用的纯文本回复（闲聊兜底路径）。"""
    llm = ScriptedLLM(LLMResult(content="今天天气不错！"))
    resp = _agent(llm, tmp_path).chat("u8", "嗨", "", "user")
    assert resp.ui == "text"
    assert resp.reply == "今天天气不错！"
    assert resp.tool_calls == []


def test_multiple_respond_among_tools(tmp_path):
    """respond_to_user 与真实工具混在：先执行工具再收尾。"""
    mixed = LLMResult(tool_calls=[
        {"id": "c4", "type": "function",
         "function": {"name": "save_memory", "arguments": '{"key":"k","value":"v"}'}},
        {"id": "c5", "type": "function",
         "function": {"name": "respond_to_user",
                      "arguments": json.dumps({"reply": "记住了",
                                               "ui": "text", "data": {}, "stage": "ANALYZE"},
                                              ensure_ascii=False)}},
    ])
    llm = ScriptedLLM(mixed)
    resp = _agent(llm, tmp_path).chat("u9", "记住预算200", "", "user")
    assert resp.reply == "记住了"
    assert {t.name for t in resp.tool_calls} == {"save_memory"}