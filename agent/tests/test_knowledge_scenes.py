"""知识库：场景/节日模板检索测试。

验证 scenes.json 加载、按关键词检索、场景推荐的风格/子风格可被解析。
"""
from agent.knowledge import get_by_id, query_knowledge


def test_scene_retrieval_by_keyword() -> None:
    """按节日关键词能命中对应场景模板。"""
    r = query_knowledge('scene', '母亲节')
    assert r['count'] >= 1
    assert any(s['name'] == '母亲节' for s in r['results'])

def test_scene_all_returns_full_list() -> None:
    """空 query 返回全部场景模板（不少于 12 个）。"""
    r = query_knowledge('scene', '')
    assert r['count'] >= 12

def test_scene_recommended_style_and_substyle() -> None:
    """场景模板必须带 recommended_style 与 recommended_substyle（均为风格 id）。"""
    s = get_by_id('scene', 'SC_VALENTINE')
    assert s['recommended_style'].startswith('S_')
    assert s['recommended_substyle'].startswith('S_')

def test_scene_substyle_resolves_via_tools() -> None:
    """场景推荐的子风格 id 必须真实存在于 styles.json 的 substyles 中。"""
    from agent.tools import _get_style_full
    for s in query_knowledge('scene', '')['results']:
        resolved, _ = _get_style_full(s['recommended_substyle'])
        assert resolved is not None, f"子风格未解析: {s['recommended_substyle']}"
        assert resolved['id'] == s['recommended_substyle']
