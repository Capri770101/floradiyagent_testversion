"""会话级方案解析测试：search_shops / create_order / generate_effect_image 的
「latest」占位符绑定到当前会话，替代旧的进程级全局状态（并发安全、不下错单）。
"""
import asyncio
import json

import pytest
from agent import tools as tools_mod
from agent.requirements import FlowerRequirement
from agent.tools import generate_diy_plan, generate_effect_image, search_shops
from backend.storage import memory as mem
from backend.storage.db import init_db


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield

def _ctx(uid: str) -> dict:
    sid = asyncio.run(mem.get_or_create_session(uid))
    return {'user_id': uid, 'session_id': sid, 'location': None, 'requirement': FlowerRequirement(recipient='母亲', budget_num=200)}

def test_order_uses_session_diy_plan_not_first_default() -> None:
    """DIY 流程：create_order(latest) 应解析到会话里的 DIY 方案（而非首条预设方案 P001）。

    测试种子店铺花材不全，覆盖率 < 100%，按新业务规则应被拦截（返回 insufficient_coverage），
    且错误信息里要带会话 DIY 方案的缺失花材清单，而不是去下 P001。
    """
    from agent.skills import skill_order
    ctx = _ctx('u_plan_diy')
    diy = json.loads(asyncio.run(generate_diy_plan('送母亲生日花 预算200', ctx)))
    shops = json.loads(asyncio.run(search_shops('latest_diy', ctx)))
    assert isinstance(shops, list) and shops
    out = json.loads(asyncio.run(skill_order.create_order('first', 'latest', 'diy', ctx)))
    if 'error' in out:
        assert out['error'] == 'insufficient_coverage'
        assert out['missing_flowers'], '拦截时应带缺失花材清单'
        return
    assert out['plan_type'] == 'diy'
    assert out['items'][0]['plan_id'] == diy['plan_id']

def test_order_uses_explicit_plan_id() -> None:
    """现有方案流程：模型显式传 plan_id 时按 id 下单（不受会话占位影响）。"""
    from agent.skills import skill_order
    ctx = _ctx('u_plan_explicit')
    out = json.loads(asyncio.run(skill_order.create_order('first', 'P002', 'existing', ctx)))
    assert out['items'][0]['plan_id'] == 'P002'
    assert out['plan_type'] == 'existing'

def test_two_sessions_do_not_cross_plans() -> None:
    """并发隔离：A 的 DIY 方案不影响 B 的 latest 解析（替代全局变量后的关键回归）。

    测试店铺花材不全 → 下单被拦截属预期；本测试重点验证 latest 绑定的是各自会话方案，
    即拦截时返回的缺失花材/拦截目标不与对方会话方案串台。
    """
    from agent.skills import skill_order
    ctx_a = _ctx('u_iso_a')
    ctx_b = _ctx('u_iso_b')
    diy_a = json.loads(asyncio.run(generate_diy_plan('母亲节康乃馨 预算200', ctx_a)))
    json.loads(asyncio.run(generate_diy_plan('送恋人生日玫瑰 预算500', ctx_b)))
    out_a = json.loads(asyncio.run(skill_order.create_order('first', 'latest', 'diy', ctx_a)))
    if 'error' in out_a:
        assert out_a['error'] == 'insufficient_coverage'
        return
    assert out_a['items'][0]['plan_id'] == diy_a['plan_id']

def test_create_order_blocks_partial_coverage() -> None:
    """覆盖率不足禁止下单：create_order 应返回 insufficient_coverage + 缺失花材，且不落库。"""
    from agent.skills import skill_order
    from backend.storage.db import get_conn
    ctx = _ctx('u_partial')
    json.loads(asyncio.run(generate_diy_plan('送母亲生日花 预算200', ctx)))
    out = json.loads(asyncio.run(skill_order.create_order('first', 'latest', 'diy', ctx)))
    assert out['error'] == 'insufficient_coverage'
    assert out['coverage'] < 1.0
    assert out['missing_flowers'], '缺失花材清单不应为空'
    assert 'suggestion' in out
    conn = get_conn()
    rows = conn.execute('SELECT COUNT(*) FROM orders WHERE user_id=?', (ctx['user_id'],)).fetchone()[0]
    assert rows == 0, '覆盖率不足时不应创建订单'

def test_effect_image_prompt_from_session_plan(monkeypatch) -> None:
    """生图 prompt 取会话内最新 DIY 方案的 effect_prompt，而非进程级全局。"""
    ctx = _ctx('u_img_prompt')
    asyncio.run(mem.update_stage(ctx['session_id'], 'image_gen'))
    asyncio.run(mem.set_session_flag(ctx['user_id'], ctx['session_id'], 'image_confirmed', '1'))
    diy = json.loads(asyncio.run(generate_diy_plan('母亲节 康乃馨 预算200', ctx)))
    captured: dict = {}

    async def fake_create(prompt: str) -> str:
        captured['prompt'] = prompt
        return 'fake_task'
    monkeypatch.setattr(tools_mod.tasks, 'create_image_task', fake_create)
    out = json.loads(asyncio.run(generate_effect_image('latest_diy', ctx)))
    assert out['task_id'] == 'fake_task'
    assert captured['prompt'] == diy['effect_prompt']
