"""storage/admin.py —— 平台管理员后台的聚合存储层（M0/M2/M3/M4/M5）。

集中管理后台的查询/写操作：用户管理、全局订单、售后审核、商家入驻审核。
所有写入使用事务；售后退款为 sandbox 模拟（翻 payments.status），
真实网关接入后替换实现，不改变调用方。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from storage.db import get_conn, transaction

# 售后状态机
AFTERSALE_STATUS = {"pending", "approved", "rejected", "refunded", "closed"}
# 入驻状态机
APPLY_STATUS = {"pending", "approved", "rejected"}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10].upper()}"


# --------------------------------------------------------------------------- #
# M0 / M2 用户管理
# --------------------------------------------------------------------------- #


def list_users(
    keyword: str = "",
    role: str = "",
    status: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """分页用户列表（昵称/用户名/手机号关键词 + 角色 + 状态筛选）。"""
    conn = get_conn()
    where, args = " WHERE 1=1", []
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        where += " AND (username LIKE ? OR nickname LIKE ? OR phone LIKE ?)"
        args += [like, like, like]
    if role:
        where += " AND role=?"
        args.append(role)
    if status:
        where += " AND status=?"
        args.append(status)
    total = conn.execute(f"SELECT COUNT(*) FROM users{where}", args).fetchone()[0]
    rows = conn.execute(
        f"""SELECT id, username, nickname, avatar, phone, role, status, created_at
            FROM users{where} ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], int(total)


def get_user(user_id: str) -> dict[str, Any] | None:
    """用户详情（含注册/更新时间）。"""
    row = get_conn().execute(
        "SELECT * FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return dict(row) if row else None


def set_user_status(user_id: str, status: str) -> bool:
    """禁用/启用用户（active|banned）。"""
    if status not in ("active", "banned"):
        raise ValueError(f"非法状态: {status}")
    with transaction() as c:
        cur = c.execute(
            "UPDATE users SET status=?, updated_at=? WHERE id=?", (status, _now(), user_id)
        )
    return cur.rowcount > 0


def set_user_role(user_id: str, role: str) -> bool:
    """提权/降权（user|merchant|admin）。"""
    from security import set_user_role as _set_role

    if role not in ("user", "merchant", "admin"):
        raise ValueError(f"非法角色: {role}")
    return _set_role(user_id, role)


# --------------------------------------------------------------------------- #
# M3 全局订单
# --------------------------------------------------------------------------- #


def list_all_orders(
    status: str = "",
    user_id: str = "",
    shop_id: str = "",
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[str], int]:
    """全局订单列表（返回 order_id 列表，由 commerce.get_order 补全详情）。"""

    conn = get_conn()
    where, args = " WHERE 1=1", []
    if status:
        where += " AND status=?"
        args.append(status)
    if user_id:
        where += " AND user_id=?"
        args.append(user_id)
    if shop_id:
        sname = conn.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
        name = sname["name"] if sname else shop_id
        where += " AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))"
        args += [shop_id, name, shop_id, name]
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        where += " AND (order_id LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ? OR items LIKE ?)"
        args += [like, like, like, like]
    if date_from:
        where += " AND date(created_at) >= ?"
        args.append(date_from.strip()[:10])
    if date_to:
        where += " AND date(created_at) <= ?"
        args.append(date_to.strip()[:10])
    total = conn.execute(f"SELECT COUNT(*) FROM orders{where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT order_id FROM orders{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        args + [limit, offset],
    ).fetchall()
    ids = [r["order_id"] for r in rows]
    return ids, int(total)


def set_order_status(order_id: str, status: str) -> dict[str, Any] | None:
    """管理员干预订单状态（绕过用户/商家流程直接落库）。

    联动：标记 paid 时写 paid_at/paid=1；其余直接改状态。
    """
    from storage import commerce

    conn = get_conn()
    row = conn.execute(
        "SELECT status FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()
    if not row:
        return None
    now = _now()
    with transaction() as c:
        if status == "paid":
            c.execute(
                "UPDATE orders SET status=?, paid=1, paid_at=COALESCE(paid_at,?) WHERE order_id=?",
                (status, now, order_id),
            )
        else:
            c.execute(
                "UPDATE orders SET status=? WHERE order_id=?", (status, order_id)
            )
    return commerce.get_order(order_id)


# --------------------------------------------------------------------------- #
# M4 售后
# --------------------------------------------------------------------------- #


def create_aftersale(
    order_id: str,
    user_id: str,
    aftersale_type: str,
    reason: str = "",
    description: str = "",
    evidence_imgs: list[str] | None = None,
) -> dict[str, Any]:
    """用户发起售后单（订单须归属本人且已支付）。"""
    from storage import commerce

    order = commerce.get_order(order_id)
    if not order:
        raise ValueError("订单不存在")
    if order["user_id"] != user_id:
        raise ValueError("只能对自己名下的订单发起售后")
    if not order.get("paid"):
        raise ValueError("仅已支付订单可发起售后")
    if aftersale_type not in ("refund", "return", "exchange"):
        raise ValueError("非法售后类型")
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM aftersales WHERE order_id=? AND status IN ('pending','approved')",
        (order_id,),
    ).fetchone()
    if existing:
        raise ValueError("该订单已有进行中的售后单")
    as_id = _new_id("AS")
    now = _now()
    with transaction() as c:
        c.execute(
            """INSERT INTO aftersales
               (id, order_id, user_id, shop_id, type, reason, description, evidence_imgs,
                status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,'pending',?,?)""",
            (
                as_id, order_id, user_id, order.get("shop_id"), aftersale_type,
                (reason or "")[:200], (description or "")[:1000],
                json.dumps(evidence_imgs or [], ensure_ascii=False),
                now, now,
            ),
        )
    return get_aftersale(as_id)


def list_aftersales(status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """售后单列表（按创建时间倒序，可筛状态）。"""
    conn = get_conn()
    where, args = " WHERE 1=1", []
    if status:
        where += " AND a.status=?"
        args.append(status)
    total = conn.execute(
        f"""SELECT COUNT(*) FROM aftersales a{where}""", args
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT a.*, o.total_price AS order_total, u.nickname, u.phone
            FROM aftersales a
            LEFT JOIN orders o ON o.order_id = a.order_id
            LEFT JOIN users u ON u.id = a.user_id
            {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["evidence_imgs"] = json.loads(d["evidence_imgs"]) if d.get("evidence_imgs") else []
        except (json.JSONDecodeError, TypeError):
            d["evidence_imgs"] = []
        out.append(d)
    return out, int(total)


def list_user_aftersales(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """我的售后单列表（用户侧）。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT a.*, o.total_price AS order_total FROM aftersales a
           LEFT JOIN orders o ON o.order_id = a.order_id
           WHERE a.user_id=? ORDER BY a.created_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["evidence_imgs"] = json.loads(d["evidence_imgs"]) if d.get("evidence_imgs") else []
        except (json.JSONDecodeError, TypeError):
            d["evidence_imgs"] = []
        out.append(d)
    return out


def get_aftersale(as_id: str) -> dict[str, Any] | None:
    """售后单详情。"""
    row = get_conn().execute(
        """SELECT a.*, o.total_price AS order_total, o.status AS order_status,
                  u.nickname, u.phone
           FROM aftersales a
           LEFT JOIN orders o ON o.order_id = a.order_id
           LEFT JOIN users u ON u.id = a.user_id
           WHERE a.id=?""",
        (as_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["evidence_imgs"] = json.loads(d["evidence_imgs"]) if d.get("evidence_imgs") else []
    except (json.JSONDecodeError, TypeError):
        d["evidence_imgs"] = []
    return d


def _update_aftersale(
    as_id: str, status: str, handled_by: str, note: str = "", refund_amount: float | None = None
) -> dict[str, Any] | None:
    """售后单状态流转（内部共用）。"""
    with transaction() as c:
        cur = c.execute(
            """UPDATE aftersales
               SET status=?, handled_by=?, handled_at=?, refund_amount=COALESCE(?, refund_amount),
                   review_note=?, updated_at=?
               WHERE id=?""",
            (status, handled_by, _now(), refund_amount, (note or "")[:500], _now(), as_id),
        )
        if cur.rowcount == 0:
            return None
        # sandbox 退款联动：翻 payments.status 为 refunded
        row = c.execute("SELECT order_id FROM aftersales WHERE id=?", (as_id,)).fetchone()
        if status == "refunded" and row:
            c.execute(
                "UPDATE payments SET status='refunded' WHERE order_id=? AND status='paid'",
                (row["order_id"],),
            )
    return get_aftersale(as_id)


def approve_aftersale(as_id: str, handled_by: str) -> dict[str, Any] | None:
    return _update_aftersale(as_id, "approved", handled_by)


def reject_aftersale(as_id: str, handled_by: str, note: str = "") -> dict[str, Any] | None:
    return _update_aftersale(as_id, "rejected", handled_by, note)


def refund_aftersale(as_id: str, handled_by: str, refund_amount: float | None = None) -> dict[str, Any] | None:
    return _update_aftersale(as_id, "refunded", handled_by, refund_amount=refund_amount)


# --------------------------------------------------------------------------- #
# M5 商家入驻
# --------------------------------------------------------------------------- #


def create_application(
    user_id: str,
    shop_name: str,
    contact_name: str = "",
    contact_phone: str = "",
    license_no: str = "",
    license_img: str = "",
    address: str = "",
    intro: str = "",
) -> dict[str, Any]:
    """用户提交入驻申请。"""
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM merchant_applications WHERE applicant_user_id=? AND status='pending'",
        (user_id,),
    ).fetchone()
    if existing:
        raise ValueError("已有待审核的入驻申请")
    app_id = _new_id("APP")
    now = _now()
    with transaction() as c:
        c.execute(
            """INSERT INTO merchant_applications
               (id, applicant_user_id, shop_name, contact_name, contact_phone, license_no,
                license_img, address, intro, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,'pending',?)""",
            (
                app_id, user_id, (shop_name or "")[:40], (contact_name or "")[:30],
                (contact_phone or "")[:20], (license_no or "")[:40], license_img or "",
                (address or "")[:120], (intro or "")[:200], now,
            ),
        )
    return get_application(app_id)


def list_applications(status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """入驻申请列表（倒序，可筛状态）。"""
    conn = get_conn()
    where, args = " WHERE 1=1", []
    if status:
        where += " AND a.status=?"
        args.append(status)
    total = conn.execute(f"SELECT COUNT(*) FROM merchant_applications a{where}", args).fetchone()[0]
    rows = conn.execute(
        f"""SELECT a.*, u.nickname, u.phone AS user_phone
            FROM merchant_applications a
            LEFT JOIN users u ON u.id = a.applicant_user_id
            {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], int(total)


def get_application(app_id: str) -> dict[str, Any] | None:
    """入驻申请详情。"""
    row = get_conn().execute(
        """SELECT a.*, u.nickname, u.phone AS user_phone
           FROM merchant_applications a
           LEFT JOIN users u ON u.id = a.applicant_user_id
           WHERE a.id=?""",
        (app_id,),
    ).fetchone()
    return dict(row) if row else None


def approve_application(app_id: str, admin_id: str) -> dict[str, Any] | None:
    """审核通过：申请人提权 merchant + 创建/绑定店铺（shop 名取 shop_name）。"""
    from storage import catalog

    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM merchant_applications WHERE id=?", (app_id,)
    ).fetchone()
    if not row:
        return None
    app = dict(row)
    if app["status"] != "pending":
        raise ValueError("该申请已处理")
    with transaction() as c:
        c.execute(
            """UPDATE merchant_applications
               SET status='approved', reviewed_by=?, reviewed_at=? WHERE id=?""",
            (admin_id, _now(), app_id),
        )
    # 提权 + 建店 + 绑定（事务外各自提交；失败回滚标记）
    from security import set_user_role

    set_user_role(app["applicant_user_id"], "merchant")
    shop = catalog.create_shop(
        {
            "name": app["shop_name"],
            "intro": app["intro"] or "",
            "address": app["address"] or "",
            "status": "营业中",
        }
    )
    catalog.merchant_bind(app["applicant_user_id"], shop["shop_id"])
    return get_application(app_id)


def reject_application(app_id: str, admin_id: str, note: str = "") -> dict[str, Any] | None:
    """审核拒绝（带备注）。"""
    with transaction() as c:
        cur = c.execute(
            """UPDATE merchant_applications
               SET status='rejected', review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?""",
            ((note or "")[:500], admin_id, _now(), app_id),
        )
        if cur.rowcount == 0:
            return None
    return get_application(app_id)


def list_merchants(limit: int = 100) -> list[dict[str, Any]]:
    """已入驻商家（merchant 角色 + 绑定店铺）。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT u.id AS user_id, u.username, u.nickname, u.phone, u.created_at,
                  ms.shop_id, s.name AS shop_name, s.created_at AS shop_created_at
           FROM users u
           JOIN merchant_shops ms ON ms.user_id = u.id
           LEFT JOIN shops s ON s.id = ms.shop_id
           WHERE u.role='merchant'
           ORDER BY s.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
