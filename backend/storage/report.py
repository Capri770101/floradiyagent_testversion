"""storage/report.py —— 内容举报数据层（阶段5 内容审核体系：举报巡查）。

P1 异步迁移（详见 EXTENSION_ENGINEERING_PLAN.md 第 3 节）：
- 函数已转为 ``async``，全部经由 ``db_async.transaction()`` + ``await c.execute`` 访问数据库，
  不再依赖 ``db.get_conn()`` 的同步连接；调用方（routers）直接 ``await``，无需 ``asyncio.to_thread``。
- SQL 仍用 ``?`` 占位符；``db_async`` 会在执行前按方言改写为 ``:p0,:p1``，PG 下同一段 SQL 也能跑
  （本模块不涉及 ``date('now')`` / ``INSERT OR`` / ``JSON``，故无需方言特例）。
- 仍由 router 层守护权限（举报按用户隔离写入；查询/处理仅 admin）。

注：sqlite 回退路径下，本模块与仍走同步 ``get_conn()`` 的其它存储模块共享同一个 db 文件，
通过 WAL 并发读写，行为一致；PG 路径只需在装有 Postgres 的环境验证方言编译结果。
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from backend.storage import db_async as dba

logger = logging.getLogger('storage.report')
T_PLAN = 'plan'
T_SHOP = 'shop'
T_REVIEW = 'review'
S_PENDING = 'pending'
S_PASSED = 'passed'
S_REJECTED = 'rejected'
S_BANNED = 'banned'
HANDLEABLE = {S_PASSED, S_REJECTED, S_BANNED}

def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')

def _new_id() -> str:
    return f'R{uuid.uuid4().hex[:12].upper()}'

async def create_report(user_id: str, target_type: str, target_id: str, reason: str, content: str='') -> dict[str, Any]:
    """新增举报（pending）。"""
    row = {'id': _new_id(), 'user_id': user_id, 'target_type': target_type, 'target_id': target_id, 'reason': reason, 'content': content, 'status': S_PENDING, 'created_at': _now()}
    async with dba.transaction() as c:
        await c.execute('INSERT INTO reports (id, user_id, target_type, target_id, reason, content, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (row['id'], row['user_id'], row['target_type'], row['target_id'], row['reason'], row['content'], row['status'], row['created_at']))
    return dict(row)

async def _target_title(c: Any, target_type: str, target_id: str) -> str:
    """目标摘要（列表展示用，取不到则回退 id）。"""
    if target_type == T_PLAN:
        rows = await c.execute('SELECT name FROM plans WHERE id = ?', (target_id,))
    elif target_type == T_SHOP:
        rows = await c.execute('SELECT name FROM shops WHERE id = ?', (target_id,))
    elif target_type == T_REVIEW:
        rows = await c.execute('SELECT content FROM reviews WHERE id = ?', (target_id,))
    else:
        rows = []
    if rows:
        text = rows[0]['name' if target_type != T_REVIEW else 'content'] or ''
        return text if len(text) <= 60 else text[:57] + '…'
    return target_id

async def list_reports(status: str='', limit: int=50, offset: int=0) -> dict[str, Any]:
    """admin 举报列表：新→旧，附带举报人昵称与目标摘要。"""
    where, params = ('', [])
    if status:
        where, params = ('WHERE r.status = ?', [status])
    async with dba.transaction() as c:
        rows = await c.execute(f"SELECT r.*, COALESCE(u.nickname, u.username, '') AS reporter FROM reports r LEFT JOIN users u ON u.id = r.user_id {where} ORDER BY r.created_at DESC LIMIT ? OFFSET ?", [*params, max(1, min(limit, 200)), max(0, offset)])
        total = (await c.execute(f'SELECT COUNT(*) AS cnt FROM reports r {where}', params))[0]['cnt']
        items = []
        for r in rows:
            d = dict(r)
            d['target_title'] = await _target_title(c, d['target_type'], d['target_id'])
            items.append(d)
    return {'reports': items, 'total': total}

async def handle_report(report_id: str, status: str, admin_uid: str) -> dict[str, Any]:
    """admin 处理举报；banned/passed 时联动下架目标（幂等）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
        if not rows:
            raise ValueError('举报不存在')
        r = dict(rows[0])
        if status in (S_BANNED, S_PASSED):
            await _take_down(c, r['target_type'], r['target_id'])
        await c.execute('UPDATE reports SET status = ?, handled_at = ?, handled_by = ? WHERE id = ?', (status, _now(), admin_uid, report_id))
        r.update(status=status, handled_at=_now(), handled_by=admin_uid)
    return r

async def _take_down(c: Any, target_type: str, target_id: str) -> None:
    """下架目标：商品 → shop_plans.status=off；店铺 → 该店全部商品 off；评价 → hidden。"""
    if target_type == T_PLAN:
        await c.execute("UPDATE shop_plans SET status = 'off' WHERE plan_id = ?", (target_id,))
    elif target_type == T_SHOP:
        await c.execute("UPDATE shop_plans SET status = 'off' WHERE shop_id = ?", (target_id,))
    elif target_type == T_REVIEW:
        await c.execute("UPDATE reviews SET status = 'hidden' WHERE id = ?", (target_id,))
