"""知识库加载与检索测试。"""
from agent.knowledge import get_by_id, query_knowledge


def test_query_flower_by_name() -> None:
    r = query_knowledge('flower', '康乃馨')
    assert r['count'] >= 1
    assert any(x['name'] == '康乃馨' for x in r['results'])

def test_query_style() -> None:
    r = query_knowledge('style', '韩式')
    assert r['count'] == 1
    assert r['results'][0]['name'] == '韩式'

def test_query_all_returns_multiple_domains() -> None:
    r = query_knowledge('all', '')
    domains = {x['_domain'] for x in r['results']}
    assert len(domains) > 1

def test_get_by_id() -> None:
    s = get_by_id('style', 'S_KOREAN')
    assert s is not None and s['name'] == '韩式'

def test_no_match_returns_empty() -> None:
    r = query_knowledge('flower', '量子计算机')
    assert r['count'] == 0
