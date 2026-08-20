"""storage/report.py —— 内容举报数据层（阶段5 内容审核体系：举报巡查）。

形式与 storage/notify.py 同风格：
- 全部同步函数，由 routers 通过 ``asyncio.to_thread`` 调用。
- 举报按用户隔离写入；查询/处理仅 admin（router 层守护）。
- banned 处理时对目标执行下架动作（商品/店铺置 off、评价置 hidden），联动既有状态字段。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from backend.storage.db import get_conn

logger = logging.getLogger("storage.report")

#: 举报目标类型
T_PLAN = "plan"      # 店铺商品
T_SHOP = "shop"      # 店铺
T_REVIEW = "review"  # 评价

#: 处理状态
S_PENDING = "pending"
S_PASSED = "passed"   # 举报属实（已下架/隐藏）
S_REJECTED = "rejected"  # 举报不属实（驳回）
S_BANNED = "banned"   # 目标已封禁/下架（与 passed 等效动作，语义更重）

#: 可处理状态
HANDLEABLE = {S_PASSED, S_REJECTED, S_BANNED}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return f"R{uuid.uuid4().hex[:12].upper()}"


def create_report(
    user_id: str, target_type: str, target_id: str, reason: str, content: str = ""
) -> dict[str, Any]:
    """新增举报（pending）。"""
    row = {
        "id": _new_id(),
        "user_id": user_id,
        "target_type": target_type,
        "target_id": target_id,
        "reason": reason,
        "content": content,
        "status": S_PENDING,
        "handled_at": None,
        "handled_by": None,
        "created_at": _now(),
    }
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reports (id, user_id, target_type, target_id, reason, content, status, created_at)"
            " VALUES (:id, :user_id, :target_type, :target_id, :reason, :content, :status, :created_at)",
            row,
        )
    return dict(row)


def _target_title(conn: Any, target_type: str, target_id: str) -> str:
    """目标摘要（列表展示用，取不到则回退 id）。"""
    if target_type == T_PLAN:
        row = conn.execute("SELECT name FROM plans WHERE id = ?", (target_id,)).fetchone()
    elif target_type == T_SHOP:
        row = conn.execute("SELECT name FROM shops WHERE id = ?", (target_id,)).fetchone()
    elif target_type == T_REVIEW:
        row = conn.execute("SELECT content FROM reviews WHERE id = ?", (target_id,)).fetchone()
    else:
        row = None
    if row:
        text = row[0] or ""
        return text if len(text) <= 60 else text[:57] + "…"
    return target_id


def list_reports(status: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """admin 举报列表：新→旧，附带举报人昵称与目标摘要。"""
    conn = get_conn()
    where, params = "", []
    if status:
        where, params = "WHERE r.status = ?", [status]
    rows = conn.execute(
        f"SELECT r.*, COALESCE(u.nickname, u.username, '') AS reporter "
        f"FROM reports r LEFT JOIN users u ON u.id = r.user_id {where} "
        "ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
        [*params, max(1, min(limit, 200)), max(0, offset)],
    ).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM reports r {where}", params).fetchone()[0]
    items = []
    for r in rows:
        d = dict(zip(("id", "user_id", "target_type", "target_id", "reason", "content",
                       "status", "handled_at", "handled_by", "created_at", "reporter"), r, strict=True))
        d["target_title"] = _target_title(conn, d["target_type"], d["target_id"])
        items.append(d)
    return {"reports": items, "total": total}


def handle_report(report_id: str, status: str, admin_uid: str) -> dict[str, Any]:
    """admin 处理举报；banned/passed 时联动下架目标（幂等）。"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            raise ValueError("举报不存在")
        r = dict(zip(("id", "user_id", "target_type", "target_id", "reason", "content",
                       "status", "handled_at", "handled_by", "created_at"), row, strict=True))
        if status in (S_BANNED, S_PASSED):
            _take_down(conn, r["target_type"], r["target_id"])
        conn.execute(
            "UPDATE reports SET status = ?, handled_at = ?, handled_by = ? WHERE id = ?",
            (status, _now(), admin_uid, report_id),
        )
        r.update(status=status, handled_at=_now(), handled_by=admin_uid)
    return r


def _take_down(conn: Any, target_type: str, target_id: str) -> None:
    """下架目标：商品 → shop_plans.status=off；店铺 → 该店全部商品 off；评价 → hidden。"""
    if target_type == T_PLAN:
        conn.execute(
            "UPDATE shop_plans SET status = 'off' WHERE plan_id = ?",
            (target_id,),
        )
    elif target_type == T_SHOP:
        conn.execute("UPDATE shop_plans SET status = 'off' WHERE shop_id = ?", (target_id,))
    elif target_type == T_REVIEW:
        conn.execute("UPDATE reviews SET status = 'hidden' WHERE id = ?", (target_id,))
