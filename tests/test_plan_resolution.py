"""会话级方案解析测试：search_shops / create_order / generate_effect_image 的
「latest」占位符绑定到当前会话，替代旧的进程级全局状态（并发安全、不下错单）。
"""

import json

import pytest

import skills  # noqa: F401 —— 触发 create_order 技能注册
import tools as tools_mod
from storage import memory as mem
from storage.db import init_db
from tools import generate_diy_plan, generate_effect_image, search_shops


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


def _ctx(uid: str) -> dict:
    sid = mem.get_or_create_session(uid)
    return {"user_id": uid, "session_id": sid, "location": None}


def test_order_uses_session_diy_plan_not_first_default() -> None:
    """DIY 流程：create_order(latest) 应下到会话里的 DIY 方案，而不是首条预设方案 P001。"""
    from skills import skill_order

    ctx = _ctx("u_plan_diy")
    diy = json.loads(generate_diy_plan("送母亲生日花 预算200", ctx))
    shops = json.loads(search_shops("latest_diy", ctx))
    assert isinstance(shops, list) and shops
    out = json.loads(skill_order.create_order("first", "latest", "diy", ctx))
    assert out["plan_type"] == "diy"
    assert out["items"][0]["plan_id"] == diy["plan_id"]  # 与推荐阶段同一份方案


def test_order_uses_explicit_plan_id() -> None:
    """现有方案流程：模型显式传 plan_id 时按 id 下单（不受会话占位影响）。"""
    from skills import skill_order

    ctx = _ctx("u_plan_explicit")
    out = json.loads(skill_order.create_order("first", "P002", "existing", ctx))
    assert out["items"][0]["plan_id"] == "P002"
    assert out["plan_type"] == "existing"


def test_two_sessions_do_not_cross_plans() -> None:
    """并发隔离：A 的 DIY 方案不影响 B 的 latest 解析（替代全局变量后的关键回归）。"""
    from skills import skill_order

    ctx_a = _ctx("u_iso_a")
    ctx_b = _ctx("u_iso_b")
    diy_a = json.loads(generate_diy_plan("母亲节康乃馨 预算200", ctx_a))
    json.loads(generate_diy_plan("送恋人生日玫瑰 预算500", ctx_b))
    out_a = json.loads(skill_order.create_order("first", "latest", "diy", ctx_a))
    assert out_a["items"][0]["plan_id"] == diy_a["plan_id"]


def test_effect_image_prompt_from_session_plan(monkeypatch) -> None:
    """生图 prompt 取会话内最新 DIY 方案的 effect_prompt，而非进程级全局。"""
    ctx = _ctx("u_img_prompt")
    mem.update_stage(ctx["session_id"], "image_gen")
    mem.set_session_flag(ctx["user_id"], ctx["session_id"], "image_confirmed", "1")
    diy = json.loads(generate_diy_plan("母亲节 康乃馨 预算200", ctx))

    captured: dict = {}

    def fake_create(prompt: str) -> str:
        captured["prompt"] = prompt
        return "fake_task"

    monkeypatch.setattr(tools_mod.tasks, "create_image_task", fake_create)
    out = json.loads(generate_effect_image("latest_diy", ctx))
    assert out["task_id"] == "fake_task"
    assert captured["prompt"] == diy["effect_prompt"]
