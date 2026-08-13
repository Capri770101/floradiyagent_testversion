"""融合测试：将 111 版的优点（session_flags 生图守卫 / respond_to_user 终结工具 / is_affirmative 生图确认）合入 flora_diy_agent 后的回归保障。

不触发真实生图（monkeypatch create_image_task），仅验证后端强约束逻辑。
"""

import json

import pytest

import tools as tools_mod
from agent import is_affirmative
from storage import memory as mem
from storage.db import init_db
from tools import generate_effect_image, to_openai_tools


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


def test_session_flags_roundtrip():
    """session_flags 读写 / 前缀清除（生图确认标记的生命周期）。"""
    sid = mem.get_or_create_session("u_flag")
    mem.set_session_flag("u_flag", sid, "image_confirmed", "1")
    assert mem.get_session_flag("u_flag", sid, "image_confirmed") == "1"
    mem.clear_session_flags("u_flag", sid, prefix="image_")
    assert mem.get_session_flag("u_flag", sid, "image_confirmed") == ""


def test_is_affirmative():
    """生图确认意图识别：肯定词命中、否定词优先、空串否定。"""
    assert is_affirmative("好的，生成吧")
    assert is_affirmative("确认，要这张")
    assert not is_affirmative("不用了，算了")
    assert not is_affirmative("暂时跳过")
    assert not is_affirmative("")


def test_respond_to_user_registered():
    """终结工具已注册进 OpenAI 工具列表（to_openai_tools 自动包含）。"""
    names = [t["function"]["name"] for t in to_openai_tools()]
    assert "respond_to_user" in names


def test_image_guard_requires_confirmation():
    """生图安全闸门：IMAGE_GEN 阶段但未获用户同意时，工具必须拦截。"""
    sid = mem.get_or_create_session("u_img_block")
    mem.update_stage(sid, "image_gen")
    ctx = {"user_id": "u_img_block", "session_id": sid, "location": None}
    out = json.loads(generate_effect_image("latest_diy", ctx))
    assert "error" in out  # 未确认 → 拦截，不应产生 task_id


def test_image_guard_ok_when_confirmed(monkeypatch):
    """生图安全闸门：获得 image_confirmed 标记后放行，并提交一次（防重复）。"""
    sid = mem.get_or_create_session("u_img_ok")
    mem.update_stage(sid, "image_gen")
    mem.set_session_flag("u_img_ok", sid, "image_confirmed", "1")
    # 必须先有结构化方案（generate_diy_plan 才会写入），否则生图兜底会报错
    mem.set_session_json(
        "u_img_ok", sid, "latest_diy_plan",
        {"effect_prompt": "fake prompt", "desc": "fake desc"},
    )
    monkeypatch.setattr(tools_mod.tasks, "create_image_task", lambda p: "fake_task")
    ctx = {"user_id": "u_img_ok", "session_id": sid, "location": None}
    out = json.loads(generate_effect_image("latest_diy", ctx))
    assert out.get("task_id") == "fake_task"  # 确认后放行
    # 同一轮重复提交应被 image_submitted 拦截
    out2 = json.loads(generate_effect_image("latest_diy", ctx))
    assert "error" in out2


def test_effect_image_requires_session_plan(monkeypatch):
    """生图兜底：已确认但会话无结构化方案时，必须报错而非拿字面量生垃圾图。"""
    sid = mem.get_or_create_session("u_img_no_plan")
    mem.update_stage(sid, "image_gen")
    mem.set_session_flag("u_img_no_plan", sid, "image_confirmed", "1")
    captured = {}
    monkeypatch.setattr(tools_mod.tasks, "create_image_task", lambda p: captured.setdefault("called", True))
    ctx = {"user_id": "u_img_no_plan", "session_id": sid, "location": None}
    out = json.loads(generate_effect_image("latest_diy", ctx))
    assert "error" in out  # 缺少方案 → 明确报错
    assert "called" not in captured  # 绝不应提交生图任务


def test_agent_respond_to_user_e2e(monkeypatch):
    """集成：agent.run 能识别 respond_to_user 终结工具，提取并经状态机校验返回。"""
    from types import SimpleNamespace

    import agent as agent_mod
    from agent import ReActAgent

    # 构造一次 LLM 响应：模型调用 respond_to_user 结束本轮
    tc = SimpleNamespace(
        name="respond_to_user",
        arguments={"reply": "好的，已为您设计", "ui": "text", "data": {"ok": 1}, "stage": "analyze"},
        id="c1",
    )
    msg = SimpleNamespace(tool_calls=[tc], content="")
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    # agent.py 用 `from engine.llm import call_llm`，需 patch 其模块命名空间里的绑定
    monkeypatch.setattr(agent_mod, "call_llm", lambda *a, **k: resp)

    agent = ReActAgent()
    r = agent.run("u_e2e", "帮我设计一束花", None, "user", None)
    assert r.reply == "好的，已为您设计"
    assert r.ui.value == "text"  # UIType 校验通过
    assert r.stage == "analyze"  # stage 经状态机校验后保留
