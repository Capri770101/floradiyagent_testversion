"""storage/chats.py —— 商家-顾客会话数据层（商家中心新增能力）。

设计要点（与 storage/commerce.py 同风格）：
- 全部为同步函数，由 api.py 通过 ``asyncio.to_thread`` 调用。
- 会话挂在 ``shop_chats``（店铺+顾客唯一），消息落 ``chat_messages``。
- 未读数分侧维护：顾客发言 → 商家未读 +1；商家回复 → 顾客未读 +1；
  任一侧读取消息列表即清零该侧未读。
- 会话列表展示 ``last_msg``（消息摘要）与 ``last_at``，按最后消息时间倒序。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from backend.storage.db import get_conn

#: 消息发送方（与 chat_messages.sender 对应）
SENDER_USER = "user"
SENDER_MERCHANT = "merchant"


def _now() -> str:
    """当前时间字符串（本地时区，便于人工排查）。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    """会话/消息 ID。"""
    return f"CH{uuid.uuid4().hex[:12].upper()}"


def get_or_create_chat(shop_id: str, user_id: str) -> dict[str, Any]:
    """取（或建）店铺+顾客唯一会话，返回会话字典。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM shop_chats WHERE shop_id=? AND user_id=?", (shop_id, user_id)
    ).fetchone()
    if row:
        return dict(row)
    chat_id = _new_id()
    now = _now()
    conn.execute(
        "INSERT INTO shop_chats(id, shop_id, user_id, last_msg, last_at, unread_user, unread_merchant, created_at)"
        " VALUES (?,?,?,NULL,?,0,0,?)",
        (chat_id, shop_id, user_id, now, now),
    )
    conn.commit()
    return {
        "id": chat_id,
        "shop_id": shop_id,
        "user_id": user_id,
        "last_msg": None,
        "last_at": now,
        "unread_user": 0,
        "unread_merchant": 0,
        "created_at": now,
    }


def list_merchant_chats(shop_ids: list[str] | None) -> list[dict[str, Any]]:
    """商家会话列表（按绑定店铺隔离；admin 传 None 返回全部）。

    附带顾客昵称（users.nickname）与店铺名（shops.name），供会话列表展示。
    """
    conn = get_conn()
    if shop_ids is None:
        rows = conn.execute(
            """SELECT c.*, u.nickname, u.avatar, s.name AS shop_name
               FROM shop_chats c
               LEFT JOIN users u ON u.id = c.user_id
               LEFT JOIN shops s ON s.id = c.shop_id
               ORDER BY c.last_at DESC LIMIT 200"""
        ).fetchall()
    elif not shop_ids:
        return []
    else:
        ph = ",".join("?" * len(shop_ids))
        rows = conn.execute(
            f"""SELECT c.*, u.nickname, u.avatar, s.name AS shop_name
                FROM shop_chats c
                LEFT JOIN users u ON u.id = c.user_id
                LEFT JOIN shops s ON s.id = c.shop_id
                WHERE c.shop_id IN ({ph})
                ORDER BY c.last_at DESC LIMIT 200""",
            shop_ids,
        ).fetchall()
    return [dict(r) for r in rows]


def list_user_chats(user_id: str) -> list[dict[str, Any]]:
    """顾客侧会话列表（个人中心展示用，附带店铺名）。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.*, s.name AS shop_name
           FROM shop_chats c
           LEFT JOIN shops s ON s.id = c.shop_id
           WHERE c.user_id=?
           ORDER BY c.last_at DESC LIMIT 200""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_chat(chat_id: str) -> dict[str, Any] | None:
    """按 ID 取会话（None 表示不存在）。"""
    row = get_conn().execute("SELECT * FROM shop_chats WHERE id=?", (chat_id,)).fetchone()
    return dict(row) if row else None


def get_shop_name(shop_id: str) -> str:
    """取店铺名（会话创建时给前端展示用；店铺不存在返回原 ID）。"""
    row = get_conn().execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
    return row["name"] if row else shop_id


def list_messages(chat_id: str, reader: str) -> list[dict[str, Any]]:
    """取会话消息（时间正序），并清零 reader 侧未读数。

    Args:
        reader: SENDER_USER（顾客读取）或 SENDER_MERCHANT（商家读取）。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE chat_id=? ORDER BY rowid ASC LIMIT 500",
        (chat_id,),
    ).fetchall()
    if reader == SENDER_USER:
        conn.execute("UPDATE shop_chats SET unread_user=0 WHERE id=?", (chat_id,))
    else:
        conn.execute("UPDATE shop_chats SET unread_merchant=0 WHERE id=?", (chat_id,))
    conn.commit()
    return [dict(r) for r in rows]


def send_message(chat_id: str, sender: str, content: str) -> dict[str, Any]:
    """写入一条消息，并更新会话的 last_msg/last_at 与对方未读数。

    Returns:
        写入后的消息字典。
    """
    conn = get_conn()
    msg_id = _new_id()
    now = _now()
    conn.execute(
        "INSERT INTO chat_messages(id, chat_id, sender, content, created_at) VALUES (?,?,?,?,?)",
        (msg_id, chat_id, sender, content, now),
    )
    if sender == SENDER_USER:
        conn.execute(
            "UPDATE shop_chats SET last_msg=?, last_at=?, unread_merchant=unread_merchant+1 WHERE id=?",
            (content[:120], now, chat_id),
        )
    else:
        conn.execute(
            "UPDATE shop_chats SET last_msg=?, last_at=?, unread_user=unread_user+1 WHERE id=?",
            (content[:120], now, chat_id),
        )
    conn.commit()
    return {
        "id": msg_id,
        "chat_id": chat_id,
        "sender": sender,
        "content": content,
        "created_at": now,
    }


def reply_review(review_id: str, reply: str) -> dict[str, Any] | None:
    """商家回复评价：写入 reply/reply_at，返回更新后的评价（None=评价不存在）。

    联动通知中心（模块一）：回复后给评价者落一条站内通知。
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    if not row:
        return None
    now = _now()
    conn.execute(
        "UPDATE reviews SET reply=?, reply_at=? WHERE id=?",
        (reply.strip()[:500], now, review_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    if updated["user_id"]:
        from backend.storage import notify

        notify.try_create(
            updated["user_id"], notify.T_REVIEW, "商家回复了你的评价",
            reply.strip()[:120],
            ref_type="order", ref_id=updated["order_id"] or "",
        )
    return dict(updated)
