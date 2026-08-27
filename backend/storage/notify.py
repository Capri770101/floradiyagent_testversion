"""storage/notify.py —— 站内消息通知中心数据层（NEW_FEATURES 模块一）。

形式 C（任务书 §2.1）：完整实现站内收件箱（A），并在数据层预留推送扩展点——
``push_channel`` 字段本期恒为 ``inbox``，微信订阅消息（B）接入时补推送适配器即可。

设计要点：
- 异步、方言无关（dba.transaction）；调用方直接 ``await``，无需 ``asyncio.to_thread``。
- 通知按接收者隔离（notifications.user_id），读取/标记只允许本人。
- 业务埋点一律走 ``try_create``：通知写入失败只记 logger，绝不影响主业务（验收 2.5）。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from backend.storage import db_async as dba

logger = logging.getLogger('storage.notify')
T_ORDER = 'order_status'
T_LOGISTICS = 'logistics'
T_REVIEW = 'review_reply'
T_AFTERSALE = 'aftersale'
T_ANNOUNCE = 'announcement'
T_SYSTEM = 'system'
CH_INBOX = 'inbox'
CH_WECHAT = 'wechat'

def _now() -> str:
    """当前时间字符串（本地时区，含毫秒，便于人工排查与可靠排序）。"""
    return time.strftime('%Y-%m-%d %H:%M:%S') + f'.{int(time.time() * 1000) % 1000:03d}'

def _new_id() -> str:
    """通知 ID（N_ 前缀）。"""
    return f'N{uuid.uuid4().hex[:12].upper()}'

async def create_notification(user_id: str, ntype: str, title: str, body: str='', ref_type: str='', ref_id: str='', push_channel: str=CH_INBOX) -> dict[str, Any] | None:
    """落一条站内通知（接收者不存在/标题为空则跳过）。

    Args:
        user_id: 接收者 users.id。
        ntype: order_status|logistics|review_reply|aftersale|announcement|system。
        title: 通知标题（必填）。
        body: 正文（可选）。
        ref_type: 关联业务类型（order|plan|shop|aftersale 等，点击跳转用）。
        ref_id: 关联业务 id。
        push_channel: 推送渠道（预留，本期恒 inbox）。

    Returns:
        落库后的通知 dict；跳过时返回 None。
    """
    title = (title or '').strip()[:60]
    if not user_id or not title:
        return None
    nid = _new_id()
    now = _now()
    async with dba.transaction() as c:
        await c.execute('INSERT INTO notifications\n               (id, user_id, type, title, body, ref_type, ref_id, push_channel, is_read, created_at)\n               VALUES (?,?,?,?,?,?,?,?,0,?)', (nid, user_id, ntype, title, (body or '')[:300], ref_type or '', ref_id or '', push_channel or CH_INBOX, now))
    return {'id': nid, 'user_id': user_id, 'type': ntype, 'title': title, 'body': (body or '')[:300], 'ref_type': ref_type or '', 'ref_id': ref_id or '', 'push_channel': push_channel or CH_INBOX, 'is_read': 0, 'created_at': now}

async def try_create(user_id: str, ntype: str, title: str, body: str='', ref_type: str='', ref_id: str='', push_channel: str=CH_INBOX) -> dict[str, Any] | None:
    """业务埋点安全包装：通知失败只记 logger，不影响主业务（验收 2.5）。"""
    try:
        return await create_notification(user_id, ntype, title, body, ref_type, ref_id, push_channel)
    except Exception:
        logger.exception('[notify] 通知写入失败 user=%s type=%s', user_id, ntype)
        return None

async def list_notifications(user_id: str, ntype: str='', is_read: int | None=None, limit: int=50, offset: int=0) -> list[dict[str, Any]]:
    """某用户的通知列表（新→旧，支持类型/已读过滤与分页）。"""
    where = 'user_id=?'
    args: list[Any] = [user_id]
    if ntype:
        where += ' AND type=?'
        args.append(ntype)
    if is_read in (0, 1):
        where += ' AND is_read=?'
        args.append(int(is_read))
    async with dba.transaction() as c:
        rows = await c.execute(f'SELECT * FROM notifications WHERE {where}\n                ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?', args + [limit, offset])
    return [dict(r) for r in rows]

async def get_notification(nid: str, user_id: str) -> dict | None:
    """取单条通知（仅本人可见，返回 None 表示不存在或非本人）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM notifications WHERE id=? AND user_id=?', (nid, user_id))
    return dict(rows[0]) if rows else None

async def count_unread(user_id: str) -> int:
    """某用户未读通知数（TabBar 红点）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT COUNT(*) AS c FROM notifications WHERE user_id=? AND is_read=0', (user_id,))
    return int(rows[0]['c']) if rows else 0

async def mark_read(user_id: str, ids: list[str] | None=None, all_: bool=False) -> int:
    """标记已读：all_=True 全部；否则只标记 ids 中属于本人的通知，返回标记条数。"""
    if all_:
        async with dba.transaction() as c:
            rows = await c.execute('UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0 RETURNING id', (user_id,))
        return len(rows)
    ids = [str(i) for i in ids or [] if str(i).strip()]
    if not ids:
        return 0
    ph = ','.join('?' * len(ids))
    async with dba.transaction() as c:
        rows = await c.execute(f'UPDATE notifications SET is_read=1 WHERE user_id=? AND id IN ({ph}) AND is_read=0 RETURNING id', [user_id, *ids])
    return len(rows)

async def broadcast(title: str, body: str='', ntype: str=T_ANNOUNCE, ref_type: str='', ref_id: str='', user_ids: list[str] | None=None) -> int:
    """平台公告/系统消息：发给全部注册用户（或指定群体），返回投放条数。"""
    if user_ids is None:
        async with dba.transaction() as c:
            user_rows = await c.execute('SELECT id FROM users')
        user_ids = [r['id'] for r in user_rows]
    n = 0
    for uid in user_ids:
        if await try_create(uid, ntype, title, body, ref_type, ref_id):
            n += 1
    return n
