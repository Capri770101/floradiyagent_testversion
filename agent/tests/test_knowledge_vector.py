"""知识库向量检索（RAG）升级测试。

验证：
- 纯 Python TF-IDF 向量空间的相似度计算正确（相同文本=1，无关=0）。
- 多 token / 长自然语句触发向量语义召回，能检索到关键词不含的字面改写结果。
- rag_enabled=False 时回退旧关键词行为（语义结果 ⊆ 开启时结果）。
- query_knowledge 返回结构向后兼容（含 _domain / _score）。
"""
from agent.knowledge import query_knowledge
from agent.knowledge.store import _tokenize, _VectorSpace


def test_vector_space_identical_and_disjoint() -> None:
    """相同文本余弦=1，完全无关文本余弦=0。"""
    vs = _VectorSpace().fit(['探病祝福清淡色系', '生日庆祝明亮活泼'])
    sim_same = vs.similarity('探病祝福清淡色系')[0]
    assert abs(sim_same - 1.0) < 1e-06
    sim_disjoint = vs.similarity('量子计算区块链')[0]
    assert sim_disjoint == 0.0

def test_tokenize_cjk_bigrams() -> None:
    """中文应产出字符 unigram+bigram，拉丁整词小写。"""
    feats = _tokenize('玫瑰Rose')
    assert '玫' in feats and '玫瑰' in feats
    assert 'rose' in feats

def test_semantic_nl_query_retrieves_relevant() -> None:
    """长自然语句应触发向量语义召回，命中探病/朋友相关搭配条目。"""
    r = query_knowledge('pairing', '看望生病住院的朋友带什么花合适')
    assert r['count'] >= 1
    ids = {x['id'] for x in r['results']}
    assert ids & {'P_OCC_GETWELL', 'P_RECIP_FRIEND', 'P_OCC_MOTHER'}

def test_semantic_adds_beyond_keyword() -> None:
    """语义模式相比纯关键词，能召回更多相关项（超集关系，验证确实升级了）。"""
    kw = query_knowledge('pairing', '探病')
    nl = query_knowledge('pairing', '住院的朋友适合送什么花')
    kw_ids = {x['id'] for x in kw['results']}
    nl_ids = {x['id'] for x in nl['results']}
    assert kw_ids <= nl_ids

def test_rag_disabled_falls_back() -> None:
    """rag_enabled=False 时回退旧关键词行为：语义结果应为开启结果的子集。"""
    from backend.config import settings
    nl = query_knowledge('pairing', '看望生病住院的朋友带什么花合适')
    nl_ids = {x['id'] for x in nl['results']}
    prev = settings.rag_enabled
    settings.rag_enabled = False
    try:
        disabled = query_knowledge('pairing', '看望生病住院的朋友带什么花合适')
    finally:
        settings.rag_enabled = prev
    disabled_ids = {x['id'] for x in disabled['results']}
    assert disabled_ids <= nl_ids

def test_result_shape_compatible() -> None:
    """返回结构向后兼容：含 _domain / _score，且顶层键不变。"""
    r = query_knowledge('flower', '玫瑰')
    assert set(r.keys()) >= {'domain', 'query', 'count', 'results'}
    assert r['results']
    assert '_domain' in r['results'][0] and '_score' in r['results'][0]
