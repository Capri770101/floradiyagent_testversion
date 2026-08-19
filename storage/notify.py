"""storage/notify.py —— 站内消息通知中心数据层（NEW_FEATURES 模块一）。

形式 C（任务书 §2.1）：完整实现站内收件箱（A），并在数据层预留推送扩展点——
``push_channel`` 字段本期恒为 ``inbox``，微信订阅消息（B）接入时补推送适配器即可。

设计要点（与 storage/admin.py 同风格）：
- 全部为同步函数，由 routers 通过 ``asyncio.to_thread`` 调用。
- 通知按接收者隔离（notifications.user_id），读取/标记只允许本人。
- 业务埋点一律走 ``try_create``：通知写入失败只记 logger，绝不影响主业务（验收 2.5）。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from storage.db import get_conn

logger = logging.getLogger("storage.notify")

#: 通知类型（任务书 §2.2）
T_ORDER = "order_status"      # 下单/支付/发货/签收/取消
T_LOGISTICS = "logistics"     # 物流节点新增
T_REVIEW = "review_reply"     # 商家回复评价
T_AFTERSALE = "aftersale"     # 售后状态变更
T_ANNOUNCE = "announcement"   # 平台公告/系统消息
T_SYSTEM = "system"

#: 推送渠道：本期仅站内收件箱（微信订阅消息等外部渠道接入时补写）
CH_INBOX = "inbox"
CH_WECHAT = "wechat"


def _now() -> str:
    """当前时间字符串（本地时区，便于人工排查）。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    """通知 ID（N_ 前缀）。"""
    return f"N{uuid.uuid4().hex[:12].upper()}"


def create_notification(
    user_id: str,
    ntype: str,
    title: str,
    body: str = "",
    ref_type: str = "",
    ref_id: str = "",
    push_channel: str = CH_INBOX,
) -> dict[str, Any] | None:
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
    title = (title or "").strip()[:60]
    if not user_id or not title:
        return None
    nid = _new_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO notifications
           (id, user_id, type, title, body, ref_type, ref_id, push_channel, is_read, created_at)
           VALUES (?,?,?,?,?,?,?,?,0,?)""",
        (nid, user_id, ntype, title, (body or "")[:300], ref_type or "", ref_id or "",
         push_channel or CH_INBOX, now),
    )
    conn.commit()
    return {
        "id": nid,
        "user_id": user_id,
        "type": ntype,
        "title": title,
        "body": (body or "")[:300],
        "ref_type": ref_type or "",
        "ref_id": ref_id or "",
        "push_channel": push_channel or CH_INBOX,
        "is_read": 0,
        "created_at": now,
    }


def try_create(
    user_id: str,
    ntype: str,
    title: str,
    body: str = "",
    ref_type: str = "",
    ref_id: str = "",
    push_channel: str = CH_INBOX,
) -> dict[str, Any] | None:
    """业务埋点安全包装：通知失败只记 logger，不影响主业务（验收 2.5）。"""
    try:
        return create_notification(user_id, ntype, title, body, ref_type, ref_id, push_channel)
    except Exception:  # noqa: BLE001  # 通知是旁路，任何异常都不得打断主流程
        logger.exception("[notify] 通知写入失败 user=%s type=%s", user_id, ntype)
        return None


def list_notifications(
    user_id: str,
    ntype: str = "",
    is_read: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """某用户的通知列表（新→旧，支持类型/已读过滤与分页）。"""
    conn = get_conn()
    where = "user_id=?"
    args: list[Any] = [user_id]
    if ntype:
        where += " AND type=?"
        args.append(ntype)
    if is_read in (0, 1):
        where += " AND is_read=?"
        args.append(int(is_read))
    rows = conn.execute(
        f"""SELECT * FROM notifications WHERE {where}
            ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows]


def get_notification(nid: str, user_id: str) -> dict | None:
    """取单条通知（仅本人可见，返回 None 表示不存在或非本人）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM notifications WHERE id=? AND user_id=?", (nid, user_id)
        ).fetchone()
    return dict(row) if row else None


def count_unread(user_id: str) -> int:
    """某用户未读通知数（TabBar 红点）。"""
    row = get_conn().execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,)
    ).fetchone()
    return int(row[0])


def mark_read(user_id: str, ids: list[str] | None = None, all_: bool = False) -> int:
    """标记已读：all_=True 全部；否则只标记 ids 中属于本人的通知，返回标记条数。"""
    conn = get_conn()
    if all_:
        cur = conn.execute(
            "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0", (user_id,)
        )
        conn.commit()
        return cur.rowcount
    ids = [str(i) for i in (ids or []) if str(i).strip()]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE notifications SET is_read=1 WHERE user_id=? AND id IN ({ph}) AND is_read=0",
        [user_id, *ids],
    )
    conn.commit()
    return cur.rowcount


def broadcast(
    title: str,
    body: str = "",
    ntype: str = T_ANNOUNCE,
    ref_type: str = "",
    ref_id: str = "",
    user_ids: list[str] | None = None,
) -> int:
    """平台公告/系统消息：发给全部注册用户（或指定群体），返回投放条数。"""
    conn = get_conn()
    if user_ids is None:
        user_ids = [r["id"] for r in conn.execute("SELECT id FROM users").fetchall()]
    n = 0
    for uid in user_ids:
        if try_create(uid, ntype, title, body, ref_type, ref_id):
            n += 1
    return n