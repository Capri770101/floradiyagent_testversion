"""DIY 方案资产库测试：确认级落库、重复去重、成交升级、个人复用检索、学习素材。"""
import asyncio
import uuid

from backend.storage import diy
from backend.storage.db import get_conn, init_db


def _count_diy(user_id):
    """PG 模式走异步计数；sqlite 回退用同步 get_conn()。"""
    from backend.storage import db_async as dba
    if dba.dialect() == 'postgresql':
        from backend.storage.db import _run_async
        async def _q():
            async with dba.transaction() as c:
                rows = await c.execute('SELECT COUNT(*) FROM diy_plans WHERE user_id=?', (user_id,))
                return rows[0][0]
        return _run_async(_q())
    return get_conn().execute('SELECT COUNT(*) FROM diy_plans WHERE user_id=?', (user_id,)).fetchone()[0]


def setup_module(module):
    init_db()

def _make_plan(style='韩式', recipient='母亲', budget=200, flower='康乃馨', plan_id=None):
    return {'plan_id': plan_id or 'DIY_' + uuid.uuid4().hex[:6], 'name': f'{style}·感恩花束', 'diy': True, 'style': style, 'recipient': recipient, 'occasion': '生日', 'budget_num': budget, 'design': {'main_flowers': [{'name': flower, 'ratio': 0.6}], 'fillers': [{'name': '满天星'}], 'foliage': [{'name': '尤加利'}], 'color_scheme': ['粉色'], 'packaging': '雾面纸', 'meaning': '感恩'}, 'diy_steps': ['1. 修剪', '2. 捆扎'], 'care_tips': '斜剪 45°', 'card_message': '妈妈我爱你', 'budget_breakdown': {'total_estimate': budget}}

def test_save_and_dedup():
    uid = 'u_diy_test'
    r1 = asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    assert r1['saved'] is True
    r2 = asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    assert r2['duplicate'] is True
    assert r2['plan_id'] == r1['plan_id']
    r3 = asyncio.run(diy.save_diy_plan(_make_plan(style='北欧', budget=300), uid))
    assert r3['saved'] is True
    n = _count_diy(uid)
    assert n == 2

def test_dup_does_not_reset_order_count():
    uid = 'u_diy_test2'
    r1 = asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    asyncio.run(diy.mark_diy_plan_ordered(r1['plan_id']))
    asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    p = asyncio.run(diy.get_diy_plan(r1['plan_id']))
    assert p['order_count'] == 1
    assert p['status'] == 'ordered'

def test_dup_fills_missing_image():
    uid = 'u_diy_test5'
    r1 = asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    assert asyncio.run(diy.get_diy_plan(r1['plan_id']))['effect_image_url'] is None
    p2 = _make_plan()
    p2['result_url'] = '/generated/abc.jpg'
    asyncio.run(diy.save_diy_plan(p2, uid))
    assert asyncio.run(diy.get_diy_plan(r1['plan_id']))['effect_image_url'] == '/generated/abc.jpg'

def test_search_personal_reuse():
    uid = 'u_diy_test3'
    asyncio.run(diy.save_diy_plan(_make_plan(recipient='母亲', budget=200), uid))
    asyncio.run(diy.save_diy_plan(_make_plan(recipient='恋人', budget=500, style='浪漫'), uid))
    from agent.requirements import FlowerRequirement
    req = FlowerRequirement(recipient='母亲')
    hits = asyncio.run(diy.search_diy_plans(uid, req))
    assert hits and all(p['recipient'] == '母亲' for p in hits)
    hits2 = asyncio.run(diy.search_diy_plans(uid, FlowerRequirement(recipient='同事')))
    assert hits2
    assert asyncio.run(diy.search_diy_plans('u_other', req)) == []

def test_proven_learning_entries():
    uid = 'u_diy_test4'
    r = asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    asyncio.run(diy.mark_diy_plan_ordered(r['plan_id']))
    proven = asyncio.run(diy.list_proven_plans(limit=5))
    assert any(p['id'] == r['plan_id'] and p['order_count'] == 1 for p in proven)
    hit = next(p for p in proven if p['id'] == r['plan_id'])
    assert hit['flowers'] == ['康乃馨']
    assert hit['color_scheme'] == ['粉色']

def test_knowledge_proven_domain():
    from agent.knowledge.store import query_knowledge
    r = asyncio.run(diy.save_diy_plan(_make_plan(flower='玫瑰'), 'u_diy_test6'))
    asyncio.run(diy.mark_diy_plan_ordered(r['plan_id']))
    out = query_knowledge('proven', '玫瑰')
    assert out['domain'] == 'proven'
    assert any(e['id'] == r['plan_id'] for e in out['results'])

def test_new_card_fields_roundtrip():
    """模块二：卡片扩充字段（难度/耗时/保鲜期/适宜人群/禁忌/情绪标签）落库并完整还原。"""
    uid = 'u_diy_card_fields'
    plan = _make_plan()
    plan['design'].update({'difficulty': '进阶', 'est_time': 45, 'shelf_life': '约 5-7 天', 'suitable_for': ['母亲', '长辈', '感恩'], 'caution': '康乃馨花萼易散，请轻拿轻放', 'mood_tags': ['温馨', '感恩']})
    r = asyncio.run(diy.save_diy_plan(plan, uid))
    assert r['saved'] is True
    p = asyncio.run(diy.get_diy_plan(r['plan_id']))
    d = p['design']
    assert d['difficulty'] == '进阶'
    assert d['est_time'] == 45
    assert d['shelf_life'] == '约 5-7 天'
    assert d['suitable_for'] == ['母亲', '长辈', '感恩']
    assert d['caution'] == '康乃馨花萼易散，请轻拿轻放'
    assert d['mood_tags'] == ['温馨', '感恩']

def test_old_plan_roundtrip_empty_new_fields():
    """旧方案（无扩充字段）落库→还原，新字段为空但不报错（前端显示 —）。"""
    uid = 'u_diy_card_fields_old'
    r = asyncio.run(diy.save_diy_plan(_make_plan(), uid))
    p = asyncio.run(diy.get_diy_plan(r['plan_id']))
    d = p['design']
    assert d['difficulty'] in (None, '')
    assert d['est_time'] is None
    assert d['shelf_life'] in (None, '')
    assert d['suitable_for'] == []
    assert d['mood_tags'] == []

def test_design_context_includes_proven():
    """设计链路 RAG 上下文包含历史实战方案（闭环：AI 越用越懂你）。"""
    from agent.tools import _retrieve_for_design
    r = asyncio.run(diy.save_diy_plan(_make_plan(flower='康乃馨', recipient='母亲'), 'u_diy_test7'))
    asyncio.run(diy.mark_diy_plan_ordered(r['plan_id']))
    ctx = _retrieve_for_design('给母亲买花，预算200')
    assert '历史实战方案' in ctx
    assert '康乃馨' in ctx
