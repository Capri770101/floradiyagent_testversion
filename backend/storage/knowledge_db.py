"""knowledge_db.py —— 花卉知识库数据库操作层。

提供花卉知识库的 CRUD 操作，支持：
- 花材管理
- 搭配方案管理
- 场景管理
- 风格管理
- 预算方案管理
- 包装方案管理
- 审计日志
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from backend.storage import db_async as dba

logger = logging.getLogger('knowledge_db')


def _now() -> str:
    """返回当前 UTC 时间字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _json_dumps(obj: Any) -> str | None:
    """将对象转换为 JSON 字符串。"""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: str | None) -> Any:
    """将 JSON 字符串转换为对象。"""
    if s is None:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


def _invalidate_knowledge_cache(domain: str) -> None:
    """清除知识库缓存，确保下次查询获取最新数据。"""
    try:
        from agent.knowledge.store import invalidate_cache
        invalidate_cache(domain)
    except ImportError:
        pass


def _fetchone(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从查询结果列表中提取第一行，如果没有则返回 None。"""
    return rows[0] if rows else None


# ========================================
# 花材操作
# ========================================

async def create_flower(flower: dict[str, Any], created_by: str = '', source: str = 'manual') -> dict[str, Any]:
    """创建花材。"""
    now = _now()
    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO flowers (
                id, name, aliases, flower_language, colors, season,
                price_tier, price_per_stem, freshness_days, category,
                care_tips, pairing_notes, tags, source, status, created_at, updated_at, created_by, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 1)
        ''', (
            flower['id'],
            flower['name'],
            _json_dumps(flower.get('aliases', [])),
            _json_dumps(flower.get('flower_language', [])),
            _json_dumps(flower.get('colors', [])),
            _json_dumps(flower.get('season', [])),
            flower.get('price_tier', '中'),
            flower.get('price_per_stem'),
            flower.get('freshness_days'),
            flower.get('category', '主花'),
            flower.get('care_tips', ''),
            flower.get('pairing_notes', ''),
            _json_dumps(flower.get('tags', [])),
            source,
            now,
            now,
            created_by
        ))

    # 清除知识库缓存
    _invalidate_knowledge_cache('flower')

    return await get_flower(flower['id'])


async def get_flower(flower_id: str) -> dict[str, Any] | None:
    """获取花材详情。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM flowers WHERE id=?', (flower_id,))
        row = _fetchone(rows)
        if not row:
            return None
        return _parse_flower(row)


async def list_flowers(
    category: str = '',
    status: str = 'active',
    page: int = 1,
    page_size: int = 20
) -> tuple[list[dict[str, Any]], int]:
    """分页查询花材。"""
    where_parts = ['status=?']
    params: list[Any] = [status]

    if category:
        where_parts.append('category=?')
        params.append(category)

    where_sql = ' AND '.join(where_parts)

    async with dba.transaction() as c:
        # 获取总数
        count_rows = await c.execute(f'SELECT COUNT(*) FROM flowers WHERE {where_sql}', tuple(params))
        count_row = _fetchone(count_rows)
        total = count_row[0] if count_row else 0

        # 分页查询
        offset = (page - 1) * page_size
        rows = await c.execute(
            f'SELECT * FROM flowers WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?',
            tuple(params + [page_size, offset])
        )

        return [_parse_flower(row) for row in rows], total


async def update_flower(
    flower_id: str,
    updates: dict[str, Any],
    updated_by: str = '',
    reason: str = ''
) -> dict[str, Any] | None:
    """更新花材。"""
    # 获取旧值
    old_flower = await get_flower(flower_id)
    if not old_flower:
        return None

    # 构建更新字段
    update_fields = []
    update_values = []

    for key, value in updates.items():
        if key in ('name', 'aliases', 'flower_language', 'colors', 'season',
                   'price_tier', 'price_per_stem', 'freshness_days', 'category',
                   'care_tips', 'pairing_notes', 'tags', 'status'):
            update_fields.append(f'{key}=?')
            if key in ('aliases', 'flower_language', 'colors', 'season', 'tags'):
                update_values.append(_json_dumps(value))
            else:
                update_values.append(value)

    if not update_fields:
        return old_flower

    update_fields.append('updated_at=?')
    update_values.append(_now())
    update_fields.append('version=version+1')
    update_values.append(flower_id)

    async with dba.transaction() as c:
        await c.execute(
            f'UPDATE flowers SET {", ".join(update_fields)} WHERE id=?',
            tuple(update_values)
        )

    # 记录审计日志
    await _log_audit('flowers', flower_id, 'UPDATE', old_flower, updates, updated_by, reason)

    # 清除知识库缓存
    _invalidate_knowledge_cache('flower')

    return await get_flower(flower_id)


async def delete_flower(flower_id: str, deleted_by: str = '', reason: str = '') -> bool:
    """删除花材（软删除）。"""
    return await update_flower(flower_id, {'status': 'archived'}, deleted_by, reason) is not None


def _parse_flower(row: Any) -> dict[str, Any]:
    """解析花材行数据。"""
    if row is None:
        return {}
    return {
        'id': row['id'],
        'name': row['name'],
        'aliases': _json_loads(row['aliases']),
        'flower_language': _json_loads(row['flower_language']),
        'colors': _json_loads(row['colors']),
        'season': _json_loads(row['season']),
        'price_tier': row['price_tier'],
        'price_per_stem': row['price_per_stem'],
        'freshness_days': row['freshness_days'],
        'category': row['category'],
        'care_tips': row['care_tips'],
        'pairing_notes': row['pairing_notes'],
        'tags': _json_loads(row['tags']),
        'source': row.get('source', 'manual'),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'created_by': row.get('created_by'),
        'version': row['version']
    }


# ========================================
# 搭配方案操作
# ========================================

async def create_pairing(pairing: dict[str, Any], created_by: str = '', source: str = 'manual') -> dict[str, Any]:
    """创建搭配方案。"""
    now = _now()
    flowers = pairing.pop('flowers', [])

    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO pairings (
                id, name, description, occasion_ids, style_ids,
                budget_min, budget_max, season, tags,
                use_count, source, status, created_at, updated_at, created_by, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'active', ?, ?, ?, 1)
        ''', (
            pairing['id'],
            pairing['name'],
            pairing.get('description', ''),
            _json_dumps(pairing.get('occasion_ids', [])),
            _json_dumps(pairing.get('style_ids', [])),
            pairing.get('budget_min'),
            pairing.get('budget_max'),
            _json_dumps(pairing.get('season', [])),
            _json_dumps(pairing.get('tags', [])),
            source,
            now,
            now,
            created_by
        ))

        # 添加花材关系
        for flower in flowers:
            await c.execute('''
                INSERT INTO pairing_flowers (
                    pairing_id, flower_id, flower_type,
                    quantity_min, quantity_max, is_required, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                pairing['id'],
                flower['flower_id'],
                flower['flower_type'],
                flower.get('quantity_min', 1),
                flower.get('quantity_max', 1),
                1 if flower.get('is_required', True) else 0,
                flower.get('sort_order', 0)
            ))

    # 清除知识库缓存
    _invalidate_knowledge_cache('pairing')

    return await get_pairing(pairing['id'])


async def get_pairing(pairing_id: str) -> dict[str, Any] | None:
    """获取搭配方案详情。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM pairings WHERE id=?', (pairing_id,))
        row = _fetchone(rows)
        if not row:
            return None

        pairing = _parse_pairing(row)

        # 获取花材关系
        flower_rows = await c.execute(
            'SELECT * FROM pairing_flowers WHERE pairing_id=? ORDER BY sort_order',
            (pairing_id,)
        )
        pairing['flowers'] = [_parse_pairing_flower(fr) for fr in flower_rows]

        return pairing


async def list_pairings(
    occasion: str = '',
    style: str = '',
    status: str = 'active',
    page: int = 1,
    page_size: int = 20
) -> tuple[list[dict[str, Any]], int]:
    """分页查询搭配方案。"""
    where_parts = ['status=?']
    params: list[Any] = [status]

    if occasion:
        where_parts.append('occasion_ids LIKE ?')
        params.append(f'%{occasion}%')

    if style:
        where_parts.append('style_ids LIKE ?')
        params.append(f'%{style}%')

    where_sql = ' AND '.join(where_parts)

    async with dba.transaction() as c:
        count_rows = await c.execute(f'SELECT COUNT(*) FROM pairings WHERE {where_sql}', tuple(params))
        count_row = _fetchone(count_rows)
        total = count_row[0] if count_row else 0

        offset = (page - 1) * page_size
        rows = await c.execute(
            f'SELECT * FROM pairings WHERE {where_sql} ORDER BY use_count DESC, created_at DESC LIMIT ? OFFSET ?',
            tuple(params + [page_size, offset])
        )

        return [_parse_pairing(row) for row in rows], total


async def update_pairing(
    pairing_id: str,
    updates: dict[str, Any],
    updated_by: str = '',
    reason: str = ''
) -> dict[str, Any] | None:
    """更新搭配方案。"""
    old_pairing = await get_pairing(pairing_id)
    if not old_pairing:
        return None

    update_fields = []
    update_values = []

    for key, value in updates.items():
        if key in ('name', 'description', 'occasion_ids', 'style_ids',
                   'budget_min', 'budget_max', 'season', 'tags', 'status'):
            update_fields.append(f'{key}=?')
            if key in ('occasion_ids', 'style_ids', 'season', 'tags'):
                update_values.append(_json_dumps(value))
            else:
                update_values.append(value)

    if not update_fields:
        return old_pairing

    update_fields.append('updated_at=?')
    update_values.append(_now())
    update_fields.append('version=version+1')
    update_values.append(pairing_id)

    async with dba.transaction() as c:
        await c.execute(
            f'UPDATE pairings SET {", ".join(update_fields)} WHERE id=?',
            tuple(update_values)
        )

    await _log_audit('pairings', pairing_id, 'UPDATE', old_pairing, updates, updated_by, reason)

    # 清除知识库缓存
    _invalidate_knowledge_cache('pairing')

    return await get_pairing(pairing_id)


async def delete_pairing(pairing_id: str, deleted_by: str = '', reason: str = '') -> bool:
    """删除搭配方案（软删除）。"""
    return await update_pairing(pairing_id, {'status': 'archived'}, deleted_by, reason) is not None


async def increment_pairing_use(pairing_id: str) -> None:
    """增加搭配方案使用计数。"""
    async with dba.transaction() as c:
        await c.execute(
            'UPDATE pairings SET use_count = use_count + 1, updated_at = ? WHERE id = ?',
            (_now(), pairing_id)
        )


async def get_trending_pairings(limit: int = 10) -> list[dict[str, Any]]:
    """获取热门搭配方案（按使用次数排序）。"""
    async with dba.transaction() as c:
        rows = await c.execute(
            "SELECT * FROM pairings WHERE status='active' AND use_count > 0 ORDER BY use_count DESC LIMIT ?",
            (limit,)
        )
        return [_parse_pairing(row) for row in rows]


async def get_pairing_stats() -> dict[str, Any]:
    """获取搭配方案使用统计。"""
    async with dba.transaction() as c:
        total = await c.execute("SELECT COUNT(*) FROM pairings WHERE status='active'")
        used = await c.execute("SELECT COUNT(*) FROM pairings WHERE status='active' AND use_count > 0")
        top_used = await c.execute(
            "SELECT use_count FROM pairings WHERE status='active' ORDER BY use_count DESC LIMIT 1"
        )

        return {
            'total_pairings': total[0] if total else 0,
            'used_pairings': used[0] if used else 0,
            'max_use_count': top_used[0] if top_used else 0,
        }


def _parse_pairing(row: Any) -> dict[str, Any]:
    """解析搭配方案行数据。"""
    if row is None:
        return {}
    return {
        'id': row['id'],
        'name': row['name'],
        'description': row['description'],
        'occasion_ids': _json_loads(row['occasion_ids']),
        'style_ids': _json_loads(row['style_ids']),
        'budget_min': row['budget_min'],
        'budget_max': row['budget_max'],
        'season': _json_loads(row['season']),
        'tags': _json_loads(row['tags']),
        'use_count': row['use_count'],
        'source': row.get('source', 'manual'),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'created_by': row.get('created_by'),
        'version': row['version']
    }


def _parse_pairing_flower(row: Any) -> dict[str, Any]:
    """解析搭配花材关系行数据。"""
    if row is None:
        return {}
    return {
        'pairing_id': row['pairing_id'],
        'flower_id': row['flower_id'],
        'flower_type': row['flower_type'],
        'quantity_min': row['quantity_min'],
        'quantity_max': row['quantity_max'],
        'is_required': bool(row['is_required']),
        'sort_order': row['sort_order']
    }


# ========================================
# 场景操作
# ========================================

async def create_occasion(occasion: dict[str, Any], created_by: str = '', source: str = 'manual') -> dict[str, Any]:
    """创建场景。"""
    now = _now()
    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO occasions (
                id, name, description, keywords, suggested_flowers, tags,
                source, status, created_at, updated_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, 1)
        ''', (
            occasion['id'],
            occasion['name'],
            occasion.get('description', ''),
            _json_dumps(occasion.get('keywords', [])),
            _json_dumps(occasion.get('suggested_flowers', [])),
            _json_dumps(occasion.get('tags', [])),
            source,
            now,
            now
        ))

    # 清除知识库缓存
    _invalidate_knowledge_cache('scene')

    return await get_occasion(occasion['id'])


async def get_occasion(occasion_id: str) -> dict[str, Any] | None:
    """获取场景详情。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM occasions WHERE id=?', (occasion_id,))
        row = _fetchone(rows)
        if not row:
            return None
        return _parse_occasion(row)


async def list_occasions(status: str = 'active') -> list[dict[str, Any]]:
    """查询场景列表。"""
    async with dba.transaction() as c:
        rows = await c.execute(
            'SELECT * FROM occasions WHERE status=? ORDER BY created_at DESC',
            (status,)
        )
        return [_parse_occasion(row) for row in rows]


async def update_occasion(
    occasion_id: str,
    updates: dict[str, Any],
    updated_by: str = '',
    reason: str = ''
) -> dict[str, Any] | None:
    """更新场景。"""
    old_occasion = await get_occasion(occasion_id)
    if not old_occasion:
        return None

    update_fields = []
    update_values = []

    for key, value in updates.items():
        if key in ('name', 'description', 'keywords', 'suggested_flowers', 'tags', 'status'):
            update_fields.append(f'{key}=?')
            if key in ('keywords', 'suggested_flowers', 'tags'):
                update_values.append(_json_dumps(value))
            else:
                update_values.append(value)

    if not update_fields:
        return old_occasion

    update_fields.append('updated_at=?')
    update_values.append(_now())
    update_fields.append('version=version+1')
    update_values.append(occasion_id)

    async with dba.transaction() as c:
        await c.execute(
            f'UPDATE occasions SET {", ".join(update_fields)} WHERE id=?',
            tuple(update_values)
        )

    await _log_audit('occasions', occasion_id, 'UPDATE', old_occasion, updates, updated_by, reason)

    # 清除知识库缓存
    _invalidate_knowledge_cache('scene')

    return await get_occasion(occasion_id)


async def delete_occasion(occasion_id: str, deleted_by: str = '', reason: str = '') -> bool:
    """删除场景（软删除）。"""
    return await update_occasion(occasion_id, {'status': 'archived'}, deleted_by, reason) is not None


def _parse_occasion(row: Any) -> dict[str, Any]:
    """解析场景行数据。"""
    if row is None:
        return {}
    return {
        'id': row['id'],
        'name': row['name'],
        'description': row['description'],
        'keywords': _json_loads(row['keywords']),
        'suggested_flowers': _json_loads(row['suggested_flowers']),
        'tags': _json_loads(row['tags']),
        'source': row.get('source', 'manual'),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'version': row['version']
    }


# ========================================
# 风格操作
# ========================================

async def create_style(style: dict[str, Any], created_by: str = '', source: str = 'manual') -> dict[str, Any]:
    """创建风格。"""
    now = _now()
    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO styles (
                id, name, description, color_scheme, flower_types, keywords, tags,
                source, status, created_at, updated_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, 1)
        ''', (
            style['id'],
            style['name'],
            style.get('description', ''),
            _json_dumps(style.get('color_scheme', [])),
            _json_dumps(style.get('flower_types', [])),
            _json_dumps(style.get('keywords', [])),
            _json_dumps(style.get('tags', [])),
            source,
            now,
            now
        ))

    # 清除知识库缓存
    _invalidate_knowledge_cache('style')

    return await get_style(style['id'])


async def get_style(style_id: str) -> dict[str, Any] | None:
    """获取风格详情。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM styles WHERE id=?', (style_id,))
        row = _fetchone(rows)
        if not row:
            return None
        return _parse_style(row)


async def list_styles(status: str = 'active') -> list[dict[str, Any]]:
    """查询风格列表。"""
    async with dba.transaction() as c:
        rows = await c.execute(
            'SELECT * FROM styles WHERE status=? ORDER BY created_at DESC',
            (status,)
        )
        return [_parse_style(row) for row in rows]


async def update_style(
    style_id: str,
    updates: dict[str, Any],
    updated_by: str = '',
    reason: str = ''
) -> dict[str, Any] | None:
    """更新风格。"""
    old_style = await get_style(style_id)
    if not old_style:
        return None

    update_fields = []
    update_values = []

    for key, value in updates.items():
        if key in ('name', 'description', 'color_scheme', 'flower_types', 'keywords', 'tags', 'status'):
            update_fields.append(f'{key}=?')
            if key in ('color_scheme', 'flower_types', 'keywords', 'tags'):
                update_values.append(_json_dumps(value))
            else:
                update_values.append(value)

    if not update_fields:
        return old_style

    update_fields.append('updated_at=?')
    update_values.append(_now())
    update_fields.append('version=version+1')
    update_values.append(style_id)

    async with dba.transaction() as c:
        await c.execute(
            f'UPDATE styles SET {", ".join(update_fields)} WHERE id=?',
            tuple(update_values)
        )

    await _log_audit('styles', style_id, 'UPDATE', old_style, updates, updated_by, reason)

    # 清除知识库缓存
    _invalidate_knowledge_cache('style')

    return await get_style(style_id)


async def delete_style(style_id: str, deleted_by: str = '', reason: str = '') -> bool:
    """删除风格（软删除）。"""
    return await update_style(style_id, {'status': 'archived'}, deleted_by, reason) is not None


def _parse_style(row: Any) -> dict[str, Any]:
    """解析风格行数据。"""
    if row is None:
        return {}
    return {
        'id': row['id'],
        'name': row['name'],
        'description': row['description'],
        'color_scheme': _json_loads(row['color_scheme']),
        'flower_types': _json_loads(row['flower_types']),
        'keywords': _json_loads(row['keywords']),
        'tags': _json_loads(row['tags']),
        'source': row.get('source', 'manual'),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'version': row['version']
    }


# ========================================
# 审计日志
# ========================================

async def _log_audit(
    table_name: str,
    record_id: str,
    action: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    changed_by: str = '',
    reason: str = ''
) -> None:
    """记录审计日志。"""
    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO knowledge_audit_log (
                table_name, record_id, action, old_value, new_value,
                changed_by, changed_at, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            table_name,
            record_id,
            action,
            json.dumps(old_value, ensure_ascii=False) if old_value else None,
            json.dumps(new_value, ensure_ascii=False) if new_value else None,
            changed_by,
            _now(),
            reason
        ))


# ========================================
# 统计查询
# ========================================

async def get_knowledge_stats() -> dict[str, Any]:
    """获取知识库统计信息。"""
    async with dba.transaction() as c:
        flowers_rows = await c.execute("SELECT COUNT(*) FROM flowers WHERE status='active'")
        flowers_count = _fetchone(flowers_rows)
        pairings_rows = await c.execute("SELECT COUNT(*) FROM pairings WHERE status='active'")
        pairings_count = _fetchone(pairings_rows)
        occasions_rows = await c.execute("SELECT COUNT(*) FROM occasions WHERE status='active'")
        occasions_count = _fetchone(occasions_rows)
        styles_rows = await c.execute("SELECT COUNT(*) FROM styles WHERE status='active'")
        styles_count = _fetchone(styles_rows)
        budgets_rows = await c.execute("SELECT COUNT(*) FROM budget_plans WHERE status='active'")
        budgets_count = _fetchone(budgets_rows)
        packagings_rows = await c.execute("SELECT COUNT(*) FROM packaging WHERE status='active'")
        packagings_count = _fetchone(packagings_rows)

        return {
            'flowers_count': flowers_count[0] if flowers_count else 0,
            'pairings_count': pairings_count[0] if pairings_count else 0,
            'occasions_count': occasions_count[0] if occasions_count else 0,
            'styles_count': styles_count[0] if styles_count else 0,
            'budgets_count': budgets_count[0] if budgets_count else 0,
            'packagings_count': packagings_count[0] if packagings_count else 0,
        }


# ========================================
# 预算方案操作
# ========================================

async def create_budget_plan(budget: dict[str, Any], created_by: str = '', source: str = 'manual') -> dict[str, Any]:
    """创建预算方案。"""
    now = _now()
    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO budget_plans (
                id, name, min_budget, max_budget, main_count_min, main_count_max,
                support_count, packaging_level, suggested_flowers, description,
                source, status, created_at, updated_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, 1)
        ''', (
            budget['id'],
            budget['name'],
            budget['min_budget'],
            budget.get('max_budget'),
            budget.get('main_count_min'),
            budget.get('main_count_max'),
            budget.get('support_count'),
            budget.get('packaging_level'),
            _json_dumps(budget.get('suggested_flowers', [])),
            budget.get('description', ''),
            source,
            now,
            now
        ))
    return await get_budget_plan(budget['id'])


async def get_budget_plan(budget_id: str) -> dict[str, Any] | None:
    """获取预算方案详情。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM budget_plans WHERE id=?', (budget_id,))
        row = _fetchone(rows)
        if not row:
            return None
        return _parse_budget_plan(row)


async def list_budget_plans(status: str = 'active') -> list[dict[str, Any]]:
    """查询预算方案列表。"""
    async with dba.transaction() as c:
        rows = await c.execute(
            'SELECT * FROM budget_plans WHERE status=? ORDER BY min_budget ASC',
            (status,)
        )
        return [_parse_budget_plan(row) for row in rows]


def _parse_budget_plan(row: Any) -> dict[str, Any]:
    """解析预算方案行数据。"""
    if row is None:
        return {}
    return {
        'id': row['id'],
        'name': row['name'],
        'min_budget': row['min_budget'],
        'max_budget': row['max_budget'],
        'main_count_min': row['main_count_min'],
        'main_count_max': row['main_count_max'],
        'support_count': row['support_count'],
        'packaging_level': row['packaging_level'],
        'suggested_flowers': _json_loads(row['suggested_flowers']),
        'description': row['description'],
        'source': row.get('source', 'manual'),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'version': row['version']
    }


# ========================================
# 包装方案操作
# ========================================

async def create_packaging(pkg: dict[str, Any], created_by: str = '', source: str = 'manual') -> dict[str, Any]:
    """创建包装方案。"""
    now = _now()
    async with dba.transaction() as c:
        await c.execute('''
            INSERT INTO packaging (
                id, name, material, color, price, description, tags,
                source, status, created_at, updated_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, 1)
        ''', (
            pkg['id'],
            pkg['name'],
            pkg.get('material'),
            pkg.get('color'),
            pkg['price'],
            pkg.get('description', ''),
            _json_dumps(pkg.get('tags', [])),
            source,
            now,
            now
        ))
    return await get_packaging(pkg['id'])


async def get_packaging(pkg_id: str) -> dict[str, Any] | None:
    """获取包装方案详情。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM packaging WHERE id=?', (pkg_id,))
        row = _fetchone(rows)
        if not row:
            return None
        return _parse_packaging(row)


async def list_packaging(status: str = 'active') -> list[dict[str, Any]]:
    """查询包装方案列表。"""
    async with dba.transaction() as c:
        rows = await c.execute(
            'SELECT * FROM packaging WHERE status=? ORDER BY price ASC',
            (status,)
        )
        return [_parse_packaging(row) for row in rows]


def _parse_packaging(row: Any) -> dict[str, Any]:
    """解析包装方案行数据。"""
    if row is None:
        return {}
    return {
        'id': row['id'],
        'name': row['name'],
        'material': row['material'],
        'color': row['color'],
        'price': row['price'],
        'description': row['description'],
        'tags': _json_loads(row['tags']),
        'source': row.get('source', 'manual'),
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'version': row['version']
    }
