"""回归测试：ReAct 循环跑满（max_iterations 耗尽）但本轮工具已有有效成果时，
不应武断回「思考太久」，而应保留成果并由 _derive_ui 渲染对应卡片。

复现场景：真实 DeepSeek 在「语义冲突 + 带历史 session」输入下陷入「反复调工具但不
收尾」的空转，跑满 max_iterations 即掉进 agent.py 的兜底分支。修复前会回「思考太久」，
但方案其实已 generate_diy_plan 生成成功——修复后改为中性收尾文案 + 真实卡片。
"""

import json
import types

import pytest

import agent as agent_mod
from storage.db import init_db


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


# ---- 轻量 Mock：模拟 OpenAI chat.completions 响应结构 ----
class _Msg:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message):
        self.message = message


class _Resp:
    def __init__(self, message):
        self.choices = [_Choice(message)]


def _make_tool_call(name: str, args: dict) -> object:
    """构造 OpenAI 风格 tool_call（agent._parse_tool_calls 走 function 分支）。"""
    tc = types.SimpleNamespace()
    tc.id = "call_1"
    fn = types.SimpleNamespace()
    fn.name = name
    fn.arguments = json.dumps(args, ensure_ascii=False)
    tc.function = fn
    return tc


def _fake_llm_always_diy(*_args, **_kwargs) -> _Resp:
    """永远返回 generate_diy_plan 工具调用、且永不调用 respond_to_user → 必然耗尽循环。"""
    return _Resp(
        _Msg(
            content="",
            tool_calls=[_make_tool_call("generate_diy_plan", {"requirements": "送给兄弟的表白花 200预算 粉色系"})],
        )
    )


def test_loop_exhausted_with_ok_diy_plan_renders_card(monkeypatch):
    """循环跑满但 generate_diy_plan 成功 -> ui=plan_card、reply 不含『思考太久』、data 有方案。"""
    # 只跑 2 轮即耗尽，避免真实多轮调用的耗时
    from config import settings

    monkeypatch.setattr(settings, "max_iterations", 2)
    # patch agent 模块的 call_llm（agent.py 用 `from engine.llm import call_llm` 绑定了名字）
    monkeypatch.setattr(agent_mod, "call_llm", _fake_llm_always_diy)

    bot = agent_mod.ReActAgent()
    resp = bot.run(
        user_id="u_fallback",
        message="送给兄弟的表白花 200预算 粉色系",
        session_id=None,
        user_role="user",
        location=None,
    )

    assert resp.ui.value == "plan_card", f"期望 plan_card，实际 {resp.ui.value}"
    assert "思考太久" not in resp.reply, f"不应回『思考太久』，实际 reply={resp.reply!r}"
    plans = resp.data.get("plans")
    assert plans, "data.plans 不应为空，方案应被保留渲染"
    assert resp.tool_calls, "tool_log 应记录已执行的 generate_diy_plan"


def test_loop_exhausted_without_any_ok_tool_still_times_out(monkeypatch):
    """循环跑满且全程无成功工具调用（纯空转）-> 仍回『思考太久』兜底。"""
    from config import settings

    monkeypatch.setattr(settings, "max_iterations", 2)

    # 调用一个必然失败的工具（不存在的工具名），使 tool_log 无 status=='ok' 记录
    def _fake_llm_bad_tool(*_args, **_kwargs) -> _Resp:
        return _Resp(_Msg(content="", tool_calls=[_make_tool_call("no_such_tool", {})]))

    monkeypatch.setattr(agent_mod, "call_llm", _fake_llm_bad_tool)

    bot = agent_mod.ReActAgent()
    resp = bot.run(
        user_id="u_fallback_empty",
        message="随便聊聊",
        session_id=None,
        user_role="user",
        location=None,
    )

    assert "太久" in resp.reply, f"无成果应回退超时提示，实际 reply={resp.reply!r}"
