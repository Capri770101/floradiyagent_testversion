"""storage/chats.py —— 商家-顾客会话数据层（商家中心新增能力）。

设计要点（与 storage/report.py 同步迁移为异步，详见 db_async.py）：
- 全部为异步函数（P1 异步迁移），由 router 层直接 ``await`` 调用。
- 会话挂在 ``shop_chats``（店铺+顾客唯一），消息落 ``chat_messages``。
- 未读数分侧维护：顾客发言 → 商家未读 +1；商家回复 → 顾客未读 +1；
  任一侧读取消息列表即清零该侧未读。
- 会话列表展示 ``last_msg``（消息摘要）与 ``last_at``，按最后消息时间倒序。
- reply_review 内部联动通知中心（notify.try_create），notify 后续迁移为异步后仍可同链路调用。
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from backend.storage import db_async as dba

SENDER_USER = 'user'
SENDER_MERCHANT = 'merchant'

def _now() -> str:
    """当前时间字符串（本地时区，便于人工排查）。"""
    return time.strftime('%Y-%m-%d %H:%M:%S')

def _new_id() -> str:
    """会话/消息 ID。"""
    return f'CH{uuid.uuid4().hex[:12].upper()}'

async def get_or_create_chat(shop_id: str, user_id: str) -> dict[str, Any]:
    """取（或建）店铺+顾客唯一会话，返回会话字典。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM shop_chats WHERE shop_id=? AND user_id=?', (shop_id, user_id))
        if rows:
            return rows[0]
        chat_id = _new_id()
        now = _now()
        await c.execute('INSERT INTO shop_chats(id, shop_id, user_id, last_msg, last_at, unread_user, unread_merchant, created_at) VALUES (?,?,?,NULL,?,0,0,?)', (chat_id, shop_id, user_id, now, now))
    return {'id': chat_id, 'shop_id': shop_id, 'user_id': user_id, 'last_msg': None, 'last_at': now, 'unread_user': 0, 'unread_merchant': 0, 'created_at': now}

async def list_merchant_chats(shop_ids: list[str] | None) -> list[dict[str, Any]]:
    """商家会话列表（按绑定店铺隔离；admin 传 None 返回全部）。

    附带顾客昵称（users.nickname）与店铺名（shops.name），供会话列表展示。
    """
    async with dba.transaction() as c:
        if shop_ids is None:
            rows = await c.execute('SELECT c.*, u.nickname, u.avatar, s.name AS shop_name\n                   FROM shop_chats c\n                   LEFT JOIN users u ON u.id = c.user_id\n                   LEFT JOIN shops s ON s.id = c.shop_id\n                   ORDER BY c.last_at DESC LIMIT 200')
        elif not shop_ids:
            return []
        else:
            ph = ','.join('?' * len(shop_ids))
            rows = await c.execute(f'SELECT c.*, u.nickname, u.avatar, s.name AS shop_name\n                    FROM shop_chats c\n                    LEFT JOIN users u ON u.id = c.user_id\n                    LEFT JOIN shops s ON s.id = c.shop_id\n                    WHERE c.shop_id IN ({ph})\n                    ORDER BY c.last_at DESC LIMIT 200', shop_ids)
    return rows

async def list_user_chats(user_id: str) -> list[dict[str, Any]]:
    """顾客侧会话列表（个人中心展示用，附带店铺名）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT c.*, s.name AS shop_name\n               FROM shop_chats c\n               LEFT JOIN shops s ON s.id = c.shop_id\n               WHERE c.user_id=?\n               ORDER BY c.last_at DESC LIMIT 200', (user_id,))
    return rows

async def get_chat(chat_id: str) -> dict[str, Any] | None:
    """按 ID 取会话（None 表示不存在）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM shop_chats WHERE id=?', (chat_id,))
    return rows[0] if rows else None

async def get_shop_name(shop_id: str) -> str:
    """取店铺名（会话创建时给前端展示用；店铺不存在返回原 ID）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT name FROM shops WHERE id=?', (shop_id,))
    return rows[0]['name'] if rows else shop_id

async def list_messages(chat_id: str, reader: str) -> list[dict[str, Any]]:
    """取会话消息（时间正序），并清零 reader 侧未读数。

    Args:
        reader: SENDER_USER（顾客读取）或 SENDER_MERCHANT（商家读取）。
    """
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM chat_messages WHERE chat_id=? ORDER BY id ASC LIMIT 500', (chat_id,))
        if reader == SENDER_USER:
            await c.execute('UPDATE shop_chats SET unread_user=0 WHERE id=?', (chat_id,))
        else:
            await c.execute('UPDATE shop_chats SET unread_merchant=0 WHERE id=?', (chat_id,))
    return rows

async def send_message(chat_id: str, sender: str, content: str) -> dict[str, Any]:
    """写入一条消息，并更新会话的 last_msg/last_at 与对方未读数。

    Returns:
        写入后的消息字典。
    """
    async with dba.transaction() as c:
        msg_id = _new_id()
        now = _now()
        await c.execute('INSERT INTO chat_messages(id, chat_id, sender, content, created_at) VALUES (?,?,?,?,?)', (msg_id, chat_id, sender, content, now))
        if sender == SENDER_USER:
            await c.execute('UPDATE shop_chats SET last_msg=?, last_at=?, unread_merchant=unread_merchant+1 WHERE id=?', (content[:120], now, chat_id))
        else:
            await c.execute('UPDATE shop_chats SET last_msg=?, last_at=?, unread_user=unread_user+1 WHERE id=?', (content[:120], now, chat_id))
    return {'id': msg_id, 'chat_id': chat_id, 'sender': sender, 'content': content, 'created_at': now}

async def reply_review(review_id: str, reply: str) -> dict[str, Any] | None:
    """商家回复评价：写入 reply/reply_at，返回更新后的评价（None=评价不存在）。

    联动通知中心（模块一）：回复后给评价者落一条站内通知。
    """
    async with dba.transaction() as c:
        rows = await c.execute('SELECT * FROM reviews WHERE id=?', (review_id,))
        if not rows:
            return None
        now = _now()
        await c.execute('UPDATE reviews SET reply=?, reply_at=? WHERE id=?', (reply.strip()[:500], now, review_id))
        updated = await c.execute('SELECT * FROM reviews WHERE id=?', (review_id,))
    if updated[0]['user_id']:
        from backend.storage import notify
        await notify.try_create(updated[0]['user_id'], notify.T_REVIEW, '商家回复了你的评价', reply.strip()[:120], ref_type='order', ref_id=updated[0]['order_id'] or '')
    return updated[0]
