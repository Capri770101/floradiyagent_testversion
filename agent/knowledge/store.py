"""knowledge/store.py —— 花卉 DIY 知识库加载与向量混合检索。

域说明：
- 花材/风格/搭配/预算/包装/场景：优先从 SQLite 数据库加载，JSON 文件作为备用数据源。
- 商家智库（shop）：特殊域，数据来自 DB 的 shop_profiles 档案（含风格/场景名称）。
- 实战方案（proven）：特殊域，数据来自 DB 的 diy_plans 表。

升级说明（2026-08-31）：
- 数据源从纯 JSON 文件升级为 SQLite 数据库，支持结构化查询和事务操作。
- 保留 JSON 文件作为备用数据源和初始数据导入来源。
- 向量检索逻辑保持不变，支持关键词命中 + 语义召回的混合检索。
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from backend.config import settings

logger = logging.getLogger('knowledge')
_DOMAINS: dict[str, str] = {
    'flower': 'flowers.json',
    'style': 'styles.json',
    'pairing': 'pairings.json',
    'budget': 'budget.json',
    'packaging': 'packaging.json',
    'scene': 'scenes.json',
    'shop': '',
    'proven': '',
}
# SQLite 域映射：domain -> (table_name, json_id_field)
_DB_DOMAINS: dict[str, str] = {
    'flower': 'flowers',
    'style': 'styles',
    'pairing': 'pairings',
    'scene': 'occasions',
}
_BASE_DIR = Path(__file__).resolve().parent
_cache: dict[str, list[dict[str, Any]]] = {}
_index_cache: dict[str, _VectorSpace] = {}
_CJK = re.compile('[\\u4e00-\\u9fff]+')
_WORD = re.compile('[a-zA-Z0-9]+')
_SEMANTIC_MIN_LEN = 6


def _tokenize(text: str) -> list[str]:
    """把文本切成检索特征：中文走字符 unigram+bigram，拉丁/数字作为整词小写。"""
    features: list[str] = []
    for m in _CJK.finditer(text or ''):
        run = m.group(0)
        features.extend(run)
        for i in range(len(run) - 1):
            features.append(run[i:i + 2])
    for m in _WORD.finditer(text or ''):
        features.append(m.group(0).lower())
    return features


class _VectorSpace:
    """极简 TF-IDF 向量空间：fit 语料后，similarity(query) 返回每条文档的余弦相似度。"""

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}
        self._idf: list[float] = []
        self._vecs: list[dict[int, float]] = []

    def fit(self, docs: list[str]) -> _VectorSpace:
        df: dict[str, int] = {}
        term_counts: list[dict[str, int]] = []
        for d in docs:
            tc: dict[str, int] = {}
            for f in _tokenize(d):
                tc[f] = tc.get(f, 0) + 1
            term_counts.append(tc)
            for t in tc:
                df[t] = df.get(t, 0) + 1
        self._vocab = {t: i for i, t in enumerate(df.keys())}
        n = len(docs)
        self._idf = [math.log((n + 1) / (df[t] + 1)) + 1.0 for t in self._vocab]
        self._vecs = []
        for tc in term_counts:
            vec: dict[int, float] = {}
            length = 0.0
            total = sum(tc.values()) or 1
            for t, c in tc.items():
                idx = self._vocab[t]
                w = c / total * self._idf[idx]
                vec[idx] = w
                length += w * w
            norm = math.sqrt(length) or 1.0
            self._vecs.append({k: v / norm for k, v in vec.items()})
        return self

    def similarity(self, query: str) -> list[float]:
        """返回 query 与每条文档的余弦相似度（已归一化向量 → 点积即余弦）。"""
        tc: dict[str, int] = {}
        for f in _tokenize(query):
            tc[f] = tc.get(f, 0) + 1
        qvec: dict[int, float] = {}
        qlen = 0.0
        total = sum(tc.values()) or 1
        for t, c in tc.items():
            if t in self._vocab:
                idx = self._vocab[t]
                w = c / total * self._idf[idx]
                qvec[idx] = w
                qlen += w * w
        if not qvec:
            return [0.0] * len(self._vecs)
        qnorm = math.sqrt(qlen)
        scores: list[float] = []
        for vec in self._vecs:
            if len(qvec) <= len(vec):
                dot = sum((w / qnorm * vec[idx] for idx, w in qvec.items() if idx in vec))
            else:
                dot = sum((vec[idx] / qnorm * w for idx, w in qvec.items() if idx in vec))
            scores.append(dot)
        return scores


def _run_async(coro):
    """在同步上下文中运行异步协程。安全处理已有运行循环的情况。"""
    if asyncio.iscoroutine(coro):
        try:
            loop = asyncio.get_running_loop()
            # 已有运行中的事件循环，使用同步 DB 查询替代
            return []
        except RuntimeError:
            return asyncio.run(coro)
    return coro


def _load_from_db(domain: str) -> list[dict[str, Any]]:
    """从 SQLite 加载知识库数据（同步查询避免嵌套事件循环）。"""
    table = _DB_DOMAINS.get(domain)
    if not table:
        return []

    try:
        from backend.storage import db as _db

        # 使用同步查询
        conn = _db.get_conn()
        rows = conn.execute(f'SELECT * FROM {table} WHERE status=?', ('active',)).fetchall()

        if not rows:
            return []

        # 转换字段格式（将 JSON 字符串转换为 Python 对象）
        result = []
        for row in rows:
            entry = dict(row)
            # 解析 JSON 字段
            for key in entry:
                if key in ('aliases', 'flower_language', 'colors', 'season', 'tags',
                           'occasion_ids', 'style_ids', 'keywords', 'suggested_flowers',
                           'color_scheme', 'flower_types'):
                    val = entry[key]
                    if isinstance(val, str):
                        try:
                            entry[key] = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            entry[key] = []
            result.append(entry)
        return result
    except Exception as e:
        logger.warning('[knowledge] SQLite 加载失败 %s: %s', domain, e)
        return []


def _load_shops() -> list[dict[str, Any]]:
    """惰性加载商家智库档案（来自 DB 的 shop_profiles，含风格/场景名称）。"""
    if 'shop' in _cache:
        return _cache['shop']
    data: list[dict[str, Any]] = []
    try:
        from backend.storage import db as _db
        conn = _db.get_conn()
        # 直接同步查询 shop_profiles 表
        rows = conn.execute(
            "SELECT * FROM shop_profiles WHERE status='active'"
        ).fetchall()
        for row in rows:
            entry = dict(row)
            shop_row = conn.execute(
                'SELECT id, name FROM shops WHERE id=?',
                (entry.get('shop_id', ''),)
            ).fetchone()
            entry['id'] = entry.get('shop_id', '')
            entry['name'] = shop_row[1] if shop_row else entry.get('shop_id', '')
            data.append(entry)
    except Exception:
        logger.warning('[knowledge] 商家智库加载失败（DB 未就绪？）', exc_info=True)
    _cache['shop'] = data
    return data


def _load_proven() -> list[dict[str, Any]]:
    """实战方案域：diy_plans 中高确认/高成交的用户方案（平台学习素材）。"""
    data: list[dict[str, Any]] = []
    try:
        from backend.storage import db as _db
        conn = _db.get_conn()
        # 直接同步查询 diy_plans 表，筛选高确认/高成交方案
        rows = conn.execute(
            "SELECT id, name, prompt, plants, style, scene, budget, "
            "confirmed, sold, created_at FROM diy_plans "
            "WHERE confirmed >= 5 OR sold >= 3 "
            "ORDER BY confirmed DESC, sold DESC LIMIT 100"
        ).fetchall()
        for row in rows:
            d = dict(row)
            d['id'] = d.get('id', '')
            d['name'] = d.get('name', '')
            data.append(d)
    except Exception:
        logger.warning('[knowledge] 实战方案库加载失败（DB 未就绪？）', exc_info=True)
    return data


def _load(domain: str) -> list[dict[str, Any]]:
    """加载某域数据（带内存缓存，避免重复读盘）。"""
    if domain == 'proven':
        return _load_proven()
    if domain in _cache:
        return _cache[domain]
    if domain == 'shop':
        return _load_shops()

    # 优先从 SQLite 加载
    if domain in _DB_DOMAINS:
        data = _load_from_db(domain)
        if data:
            _cache[domain] = data
            return data

    # 备用：从 JSON 文件加载
    path = _BASE_DIR / _DOMAINS[domain]
    if not path.exists():
        logger.warning('[knowledge] 数据文件缺失: %s', path)
        _cache[domain] = []
        return _cache[domain]
    with path.open(encoding='utf-8') as f:
        data = json.load(f)
    _cache[domain] = data
    return data


def _collect_strings(value: Any, out: list[str]) -> None:
    """递归收集 dict/list 里的所有字符串（嵌套结构如 styles/scenes 名称也纳入索引文本）。"""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _collect_strings(v, out)


def _entry_text(entry: dict[str, Any]) -> str:
    """把一条知识的可检索字段拼成一段文本，用于构建向量（递归含嵌套名称）。"""
    parts: list[str] = []
    for v in entry.values():
        _collect_strings(v, parts)
    return ' '.join(parts)


def _get_index(domain: str) -> _VectorSpace:
    """懒构建并按域缓存向量空间（首次非关键词查询时构建）。"""
    if domain not in _index_cache:
        _index_cache[domain] = _VectorSpace().fit([_entry_text(e) for e in _load(domain)])
    return _index_cache[domain]


def _match(entry: dict[str, Any], tokens: list[str]) -> bool:
    """entry 是否命中任一 token：匹配 name/aliases/tags/flower_language/colors 等文本字段。"""
    haystack = ' '.join(
        (str(v) for k, v in entry.items() if isinstance(v, (str, list)) for v in ([v] if isinstance(v, str) else v))
    )
    return any(tok in haystack for tok in tokens)


def _allow_vector(query: str, tokens: list[str]) -> bool:
    """是否启用向量语义扩展：仅当 rag 开启，且查询为「多 token 或长自然语句」。"""
    return settings.rag_enabled and (len(tokens) >= 2 or len(query) >= _SEMANTIC_MIN_LEN)


def _retrieve_domain(domain: str, tokens: list[str], allow_vector: bool) -> list[tuple[dict[str, Any], float]]:
    """单域检索：返回 [(entry, score)]，按 score 降序。"""
    entries = _load(domain)
    if not entries:
        return []
    kw_hits = [_match(e, tokens) for e in entries]
    if not allow_vector:
        return [(e, 1.0) for e, hit in zip(entries, kw_hits, strict=True) if hit]
    sims = _get_index(domain).similarity(' '.join(tokens))
    out: list[tuple[dict[str, Any], float]] = []
    for e, hit, sim in zip(entries, kw_hits, sims, strict=True):
        score = float(sim)
        if hit:
            score += settings.rag_keyword_boost
        if hit or score >= settings.rag_min_score:
            out.append((e, score))
    out.sort(key=lambda x: x[1], reverse=True)
    if settings.rag_top_k and len(out) > settings.rag_top_k:
        out = out[:settings.rag_top_k]
    return out


def query_knowledge(domain: str = 'all', query: str = '') -> dict[str, Any]:
    """知识库检索（向量混合检索，接口向后兼容）。

    Args:
        domain: "all" 或 flower/style/pairing/budget/packaging/scene/shop 之一。
        query: 自然语言或关键词。

    Returns:
        { "domain": str, "query": str, "count": int, "results": [ {_domain, _score, ...entry} ] }
    """
    tokens = [t for t in query.replace(',', ' ').split() if t]
    domains = list(_DOMAINS) if domain == 'all' else [domain]
    if not tokens:
        results = []
        for dom in domains:
            if dom not in _DOMAINS:
                continue
            for entry in _load(dom):
                results.append({'_domain': dom, '_score': 1.0, **entry})
        return {'domain': domain, 'query': query, 'count': len(results), 'results': results}
    allow_vector = _allow_vector(query, tokens)
    results = []
    for dom in domains:
        if dom not in _DOMAINS:
            continue
        for entry, score in _retrieve_domain(dom, tokens, allow_vector):
            results.append({'_domain': dom, '_score': round(score, 4), **entry})
    if domain == 'all':
        results.sort(key=lambda r: r['_score'], reverse=True)
    return {'domain': domain, 'query': query, 'count': len(results), 'results': results}


def get_by_id(domain: str, item_id: str) -> dict[str, Any] | None:
    """按 id 精确取一条知识（设计函数内部用）。"""
    for entry in _load(domain):
        if entry.get('id') == item_id:
            return entry
    return None


def invalidate_cache(domain: str | None = None) -> None:
    """清除缓存，用于数据更新后重新加载。

    Args:
        domain: 指定域清除，None 则清除全部缓存。
    """
    if domain:
        _cache.pop(domain, None)
        _index_cache.pop(domain, None)
    else:
        _cache.clear()
        _index_cache.clear()
