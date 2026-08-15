"""storage/commerce.py —— 电商业务数据层（购物车 / 订单 / 支付）。

设计要点：
- 全部为同步函数，由 api.py 通过 ``asyncio.to_thread`` 调用，避免阻塞事件循环
  （与 storage/db.py 的线程局部连接策略一致）。
- 购物车按 ``user_id`` 隔离；同一用户重复加同一 ``plan_id`` 只累加数量。
- 订单落 ``orders`` 表（items 以 JSON 存储）；下单后可清空对应购物车项。
- 支付由 ``storage.payment`` 抽象层驱动：``pay_order`` 只负责发起统一下单、记录
  ``payments`` 行并归一化返回；真实网关的「已支付」状态仅由 ``mark_order_paid``
  （支付回调验签通过后调用）落库，状态机不被前端直接信任。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from storage import payment as payment_module
from storage.db import get_conn

logger = logging.getLogger("commerce")


def _now() -> str:
    """当前时间字符串（本地时区，便于人工排查）。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: Any) -> dict[str, Any]:
    """sqlite3.Row -> dict，并把 selected 转成 bool。"""
    d = dict(row)
    d["selected"] = bool(d.get("selected"))
    return d


# --------------------------------------------------------------------------- #
# 优惠券 / 积分
# --------------------------------------------------------------------------- #


def _ensure_welcome_coupon(user_id: str) -> None:
    """新用户自动发放一张「新人立减 10 元」无门槛券（幂等：已有券则不重复发）。"""
    conn = get_conn()
    has = conn.execute(
        "SELECT 1 FROM coupons WHERE user_id=? LIMIT 1", (user_id,)
    ).fetchone()
    if has:
        return
    conn.execute(
        """INSERT INTO coupons (id, user_id, title, discount, min_spend, status, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            "C_" + uuid.uuid4().hex[:10],
            user_id,
            "新人立减 10 元",
            10.0,
            0.0,
            "unused",
            _now(),
        ),
    )
    conn.commit()


def list_coupons(user_id: str) -> list[dict[str, Any]]:
    """列出用户优惠券（自动发放新人券），未使用的排前面。"""
    _ensure_welcome_coupon(user_id)
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM coupons WHERE user_id=?
           ORDER BY (status='unused') DESC, created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _best_coupon_for(user_id: str, total: float) -> dict[str, Any] | None:
    """选一张最优可用券：未使用 + 金额达标，抵扣额最大的那张。"""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM coupons WHERE user_id=? AND status='unused' AND min_spend<=?
           ORDER BY discount DESC LIMIT 1""",
        (user_id, total),
    ).fetchone()
    return dict(row) if row else None


def apply_best_coupon(order_id: str, user_id: str, total: float) -> float:
    """为已落库订单自动抵扣最优券，返回实际抵扣金额（无券/不达标为 0）。"""
    _ensure_welcome_coupon(user_id)
    coupon = _best_coupon_for(user_id, total)
    if not coupon:
        return 0.0
    return apply_coupon(order_id, coupon, total)


def apply_coupon(order_id: str, coupon: dict[str, Any], total: float) -> float:
    """把优惠券落订单（discount/coupon_id），标记为已用，返回抵扣后的金额。"""
    conn = get_conn()
    discount = min(float(coupon["discount"]), total)
    conn.execute(
        """UPDATE orders SET coupon_id=?, discount=? WHERE order_id=?""",
        (coupon["id"], discount, order_id),
    )
    conn.execute(
        """UPDATE coupons SET status='used', order_id=?, used_at=? WHERE id=?""",
        (order_id, _now(), coupon["id"]),
    )
    conn.commit()
    return total - discount


def get_points(user_id: str) -> dict[str, Any]:
    """查询用户积分余额与流水。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM user_points WHERE user_id=?", (user_id,)).fetchone()
    balance = int(row["balance"]) if row else 0
    records = conn.execute(
        """SELECT * FROM point_records WHERE user_id=? ORDER BY created_at DESC LIMIT 50""",
        (user_id,),
    ).fetchall()
    return {
        "balance": balance,
        "records": [dict(r) for r in records],
    }


def add_points(user_id: str, delta: int, reason: str, order_id: str = "") -> int:
    """发放/扣减积分并记流水，返回最新余额。"""
    conn = get_conn()
    row = conn.execute("SELECT balance FROM user_points WHERE user_id=?", (user_id,)).fetchone()
    balance = int(row["balance"]) if row else 0
    new_balance = max(0, balance + delta)
    conn.execute(
        """INSERT INTO user_points (user_id, balance, total_earned)
           VALUES (?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
             balance=excluded.balance,
             total_earned=user_points.total_earned + CASE WHEN ? > 0 THEN ? ELSE 0 END""",
        (user_id, new_balance, max(0, delta), delta, delta),
    )
    conn.execute(
        """INSERT INTO point_records (id, user_id, delta, reason, order_id, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            "P_" + uuid.uuid4().hex[:10],
            user_id,
            delta,
            reason,
            order_id or None,
            _now(),
        ),
    )
    conn.commit()
    return new_balance


# --------------------------------------------------------------------------- #
# 收货地址
# --------------------------------------------------------------------------- #


def list_addresses(user_id: str) -> list[dict[str, Any]]:
    """列出用户收货地址（默认地址排最前）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_address(
    user_id: str, name: str, phone: str, address: str, is_default: bool = False
) -> dict[str, Any]:
    """新增地址：首个地址自动设为默认；is_default=True 时清除其他默认。"""
    conn = get_conn()
    addr_id = "A_" + uuid.uuid4().hex[:10]
    now = _now()
    first = not conn.execute("SELECT 1 FROM addresses WHERE user_id=?", (user_id,)).fetchone()
    if is_default or first:
        conn.execute("UPDATE addresses SET is_default=0 WHERE user_id=?", (user_id,))
    conn.execute(
        """INSERT INTO addresses (id, user_id, name, phone, address, is_default, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (addr_id, user_id, name, phone, address, 1 if (is_default or first) else 0, now, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM addresses WHERE id=?", (addr_id,)).fetchone())


def update_address(
    addr_id: str, user_id: str,
    name: str | None = None, phone: str | None = None,
    address: str | None = None, is_default: bool | None = None,
) -> dict[str, Any] | None:
    """更新地址（仅本人）；is_default=True 时清除该用户其他默认。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM addresses WHERE id=? AND user_id=?", (addr_id, user_id)
    ).fetchone()
    if not row:
        return None
    sets: list[str] = []
    vals: list[Any] = []
    for col, val in (("name", name), ("phone", phone), ("address", address)):
        if val is not None:
            sets.append(f"{col}=?")
            vals.append(val)
    if is_default is True:
        conn.execute("UPDATE addresses SET is_default=0 WHERE user_id=?", (row["user_id"],))
        sets.append("is_default=1")
    elif is_default is False:
        sets.append("is_default=0")
    sets.append("updated_at=?")
    vals.append(_now())
    if sets:
        conn.execute(
            f"UPDATE addresses SET {', '.join(sets)} WHERE id=? AND user_id=?",
            vals + [addr_id, user_id],
        )
        conn.commit()
    return dict(conn.execute("SELECT * FROM addresses WHERE id=?", (addr_id,)).fetchone())


def delete_address(addr_id: str, user_id: str) -> bool:
    """删除地址（仅本人）；被删的是默认地址时，自动把最新一条设为默认。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM addresses WHERE id=? AND user_id=?", (addr_id, user_id)
    ).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM addresses WHERE id=?", (addr_id,))
    if row["is_default"]:
        nxt = conn.execute(
            "SELECT id FROM addresses WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (row["user_id"],),
        ).fetchone()
        if nxt:
            conn.execute("UPDATE addresses SET is_default=1 WHERE id=?", (nxt["id"],))
    conn.commit()
    return True


def get_default_address(user_id: str) -> dict[str, Any] | None:
    """读取默认地址（无默认则取最新一条，用于下单预填）。"""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM addresses WHERE user_id=?
           ORDER BY is_default DESC, created_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------- #
# 收藏
# --------------------------------------------------------------------------- #


def add_favorite(user_id: str, plan_id: str) -> bool:
    """收藏方案（幂等：已收藏不报错），返回是否新增。"""
    conn = get_conn()
    cur = conn.execute(
        """INSERT OR IGNORE INTO favorites (user_id, plan_id, created_at) VALUES (?,?,?)""",
        (user_id, plan_id, _now()),
    )
    conn.commit()
    return cur.rowcount > 0


def remove_favorite(user_id: str, plan_id: str) -> bool:
    """取消收藏，返回是否删到了。"""
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM favorites WHERE user_id=? AND plan_id=?", (user_id, plan_id)
    )
    conn.commit()
    return cur.rowcount > 0


def list_favorites(user_id: str) -> list[dict[str, Any]]:
    """列出收藏（新→旧，附方案详情供前端直接渲染）。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT f.plan_id, f.created_at, p.name, p.price, p.effect_image_url,
                  p.merchant_name, p.desc
           FROM favorites f LEFT JOIN plans p ON p.id = f.plan_id
           WHERE f.user_id=? ORDER BY f.created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def is_favorite(user_id: str, plan_id: str) -> bool:
    conn = get_conn()
    return bool(
        conn.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND plan_id=?", (user_id, plan_id)
        ).fetchone()
    )


def count_favorites(user_id: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
    ).fetchone()
    return int(row[0])


# --------------------------------------------------------------------------- #
# 商家端（店铺维度经营数据）
# --------------------------------------------------------------------------- #


def merchant_stats(shop_id: str = "") -> dict[str, Any]:
    """店铺维度经营统计：订单数 / GMV / 待发货 / 已完成 / 评价数。

    Args:
        shop_id: 店铺名或店铺 id（orders.shop_id 存的是商家名快照），空则汇总全部店铺。
    """
    conn = get_conn()
    where = "WHERE shop_id=?" if shop_id else ""
    args: tuple[Any, ...] = (shop_id,) if shop_id else ()
    total = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders {where}", args).fetchone()
    and_sql = " AND status='paid'" if shop_id else " WHERE status='paid'"
    pending = conn.execute(
        f"SELECT COUNT(*) FROM orders {where}{and_sql}", args
    ).fetchone()[0]
    and_sql = " AND status='done'" if shop_id else " WHERE status='done'"
    done = conn.execute(
        f"SELECT COUNT(*) FROM orders {where}{and_sql}", args
    ).fetchone()[0]
    and_sql = " AND status='canceled'" if shop_id else " WHERE status='canceled'"
    canceled = conn.execute(
        f"SELECT COUNT(*) FROM orders {where}{and_sql}", args
    ).fetchone()[0]
    rev = conn.execute(
        """SELECT COUNT(*), COALESCE(AVG(r.rating),0) FROM reviews r
           LEFT JOIN orders o ON o.order_id = r.order_id
           WHERE o.shop_id = COALESCE(?, o.shop_id)""",
        (shop_id or None,),
    ).fetchone()
    shops = conn.execute("SELECT id, name FROM shops ORDER BY created_at").fetchall()
    return {
        "order_count": int(total[0]),
        "gmv": float(total[1] or 0),
        "pending_ship": int(pending),
        "done_count": int(done),
        "canceled_count": int(canceled),
        "review_count": int(rev[0]),
        "avg_rating": float(rev[1] or 0),
        "shops": [dict(s) for s in shops],
    }


def merchant_orders(shop_id: str = "", status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """商家视角订单列表（任意用户，可按店铺/状态过滤）。"""
    conn = get_conn()
    sql = "SELECT order_id FROM orders WHERE 1=1"
    args: list[Any] = []
    if shop_id:
        sql += " AND shop_id=?"
        args.append(shop_id)
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    return [get_order(r["order_id"]) for r in rows]


def merchant_ship(order_id: str) -> dict[str, Any] | None:
    """商家代发货（不受订单归属限制）：paid -> shipped。"""
    return ship_order(order_id)


def merchant_reviews(shop_id: str = "") -> list[dict[str, Any]]:
    """店铺维度评价列表（关联订单取收货信息；空 shop_id 返回全部）。"""
    conn = get_conn()
    if shop_id:
        rows = conn.execute(
            """SELECT r.* FROM reviews r
               JOIN orders o ON o.order_id = r.order_id
               WHERE o.shop_id=? ORDER BY r.created_at DESC LIMIT 100""",
            (shop_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 评价
# --------------------------------------------------------------------------- #


def create_review(
    user_id: str, order_id: str, rating: int, content: str = ""
) -> dict[str, Any]:
    """订单完成后写评价：仅订单主人 + 订单已 done；同一订单只能评一次（重复则更新）。

    Returns:
        评价 dict。

    Raises:
        ValueError: 订单不存在 / 非本人 / 未完成 / 评分越界。
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()
    if not row:
        raise ValueError("订单不存在")
    if row["user_id"] != user_id:
        raise ValueError("无权评价该订单")
    if row["status"] != "done":
        raise ValueError("订单完成后才能评价")
    if rating < 1 or rating > 5:
        raise ValueError("评分需在 1-5 星之间")
    now = _now()
    items = json.loads(row["items"]) if row["items"] else []
    plan_id = items[0].get("plan_id") if items else None
    exist = conn.execute(
        "SELECT id FROM reviews WHERE user_id=? AND order_id=?", (user_id, order_id)
    ).fetchone()
    if exist:
        conn.execute(
            "UPDATE reviews SET rating=?, content=?, created_at=? WHERE id=?",
            (rating, content, now, exist["id"]),
        )
        conn.commit()
        rev = dict(conn.execute("SELECT * FROM reviews WHERE id=?", (exist["id"],)).fetchone())
    else:
        rev_id = "R_" + uuid.uuid4().hex[:10]
        conn.execute(
            """INSERT INTO reviews (id, user_id, plan_id, order_id, rating, content, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (rev_id, user_id, plan_id, order_id, rating, content, now),
        )
        conn.commit()
        rev = dict(conn.execute("SELECT * FROM reviews WHERE id=?", (rev_id,)).fetchone())
    rev["plan_id"] = plan_id
    return rev


def list_reviews(plan_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """列出某方案的评价（新→旧，含用户昵称）；plan_id 为空返回全部。"""
    conn = get_conn()
    if plan_id:
        rows = conn.execute(
            """SELECT r.*, u.nickname FROM reviews r
               LEFT JOIN users u ON u.id = r.user_id
               WHERE r.plan_id=? ORDER BY r.created_at DESC LIMIT ?""",
            (plan_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT r.*, u.nickname FROM reviews r
               LEFT JOIN users u ON u.id = r.user_id
               ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# 购物车
# --------------------------------------------------------------------------- #


def add_to_cart(
    user_id: str,
    plan_id: str,
    name: str,
    price: float,
    shop: str | None = None,
) -> dict[str, Any]:
    """加入购物车：同用户同方案已存在则数量 +1，否则新建。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM cart_items WHERE user_id=? AND plan_id=?", (user_id, plan_id)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE cart_items SET qty=qty+1, updated_at=? WHERE item_id=?",
            (_now(), row["item_id"]),
        )
        conn.commit()
        return _row_to_dict(
            conn.execute(
                "SELECT * FROM cart_items WHERE item_id=?", (row["item_id"],)
            ).fetchone()
        )
    item_id = "C_" + uuid.uuid4().hex[:10]
    now = _now()
    conn.execute(
        """INSERT INTO cart_items
           (item_id, user_id, plan_id, name, price, shop, qty, selected, created_at, updated_at)
           VALUES (?,?,?,?,?,?,1,1,?,?)""",
        (item_id, user_id, plan_id, name, price, shop, now, now),
    )
    conn.commit()
    return _row_to_dict(
        conn.execute("SELECT * FROM cart_items WHERE item_id=?", (item_id,)).fetchone()
    )


def list_cart(user_id: str) -> list[dict[str, Any]]:
    """列出某用户购物车项（按加入时间倒序）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM cart_items WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_cart_item(
    item_id: str,
    qty: int | None = None,
    selected: bool | None = None,
) -> dict[str, Any] | None:
    """更新购物车项数量或勾选状态；任一为 None 则不改该字段。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM cart_items WHERE item_id=?", (item_id,)).fetchone()
    if not row:
        return None
    if qty is not None:
        qty = max(1, int(qty))
        conn.execute(
            "UPDATE cart_items SET qty=?, updated_at=? WHERE item_id=?",
            (qty, _now(), item_id),
        )
    if selected is not None:
        conn.execute(
            "UPDATE cart_items SET selected=?, updated_at=? WHERE item_id=?",
            (1 if selected else 0, _now(), item_id),
        )
    conn.commit()
    return _row_to_dict(
        conn.execute("SELECT * FROM cart_items WHERE item_id=?", (item_id,)).fetchone()
    )


def remove_cart_item(item_id: str) -> bool:
    """删除购物车项，返回是否真的删到了。"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM cart_items WHERE item_id=?", (item_id,))
    conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# 订单
# --------------------------------------------------------------------------- #


def create_order(
    user_id: str,
    items: list[dict[str, Any]],
    recipient: dict[str, Any] | None = None,
    delivery: str | None = None,
    note: str | None = None,
    address_id: str | None = None,
) -> dict[str, Any]:
    """创建订单：计算总额、自动抵扣最优优惠券、落库（含收货信息），并从购物车移除带 item_id 的项。

    Args:
        address_id: 收货地址 id（用户已存地址时传此即可）；未传或找不到时回退 recipient 手填。
    """
    conn = get_conn()
    total = sum(float(it.get("price", 0)) * int(it.get("qty", 1)) for it in items)
    order_id = "O_" + uuid.uuid4().hex[:10]
    first = items[0] if items else {}
    # 兼容 recipient 两种命名风格（前端 name/phone/address 或 recipient_name/...）
    r = recipient or {}
    rname = r.get("name") or r.get("recipient_name")
    rphone = r.get("phone") or r.get("recipient_phone")
    raddr = r.get("address") or r.get("recipient_address")
    saved_addr = None
    if address_id:
        saved_addr = conn.execute(
            "SELECT * FROM addresses WHERE id=? AND user_id=?", (address_id, user_id)
        ).fetchone()
    if saved_addr:
        rname, rphone, raddr = saved_addr["name"], saved_addr["phone"], saved_addr["address"]
    conn.execute(
        """INSERT INTO orders
           (order_id, user_id, plan_id, plan_type, shop_id, items, total_price,
            paid, status, address_id, recipient_name, recipient_phone, recipient_address,
            delivery_time, note, created_at)
           VALUES (?,?,?,?,?,?,?,0,'created',?,?,?,?,?,?,?)""",
        (
            order_id,
            user_id,
            first.get("plan_id"),
            "plan",
            first.get("shop"),
            json.dumps(items, ensure_ascii=False),
            total,
            saved_addr["id"] if saved_addr else None,
            rname,
            rphone,
            raddr,
            delivery,
            note,
            _now(),
        ),
    )
    # 自动抵扣最优可用优惠券（新人立减等）；折扣落订单并标记券已用
    apply_best_coupon(order_id, user_id, total)
    # 若购物车项带 item_id，下单后移除（避免重复结算）
    for it in items:
        iid = it.get("item_id")
        if iid:
            conn.execute("DELETE FROM cart_items WHERE item_id=?", (iid,))
    _append_logistics(order_id, "订单已创建，等待支付")
    conn.commit()
    return get_order(order_id)


def update_order(
    order_id: str,
    recipient: dict[str, Any] | None = None,
    delivery: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """更新订单的收货人 / 配送时间 / 备注（仅允许设置传入的字段）。

    Args:
        order_id: 订单号。
        recipient: ``{name, phone, address}`` 任意子集；缺省字段不覆盖。
        delivery: 配送时间描述（如 ``"今天 18:00–20:00"``）。
        note: 订单备注。

    Returns:
        更新后的订单 dict；订单不存在返回 None。
    """
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM orders WHERE order_id=?", (order_id,)).fetchone():
        return None
    sets: list[str] = []
    vals: list[Any] = []
    if recipient is not None and isinstance(recipient, dict):
        if "name" in recipient:
            sets.append("recipient_name=?")
            vals.append(recipient.get("name"))
        if "phone" in recipient:
            sets.append("recipient_phone=?")
            vals.append(recipient.get("phone"))
        if "address" in recipient:
            sets.append("recipient_address=?")
            vals.append(recipient.get("address"))
    if delivery is not None:
        sets.append("delivery_time=?")
        vals.append(delivery)
    if note is not None:
        sets.append("note=?")
        vals.append(note)
    if sets:
        conn.execute(
            f"UPDATE orders SET {', '.join(sets)} WHERE order_id=?",
            vals + [order_id],
        )
        conn.commit()
    return get_order(order_id)


def get_order(order_id: str) -> dict[str, Any] | None:
    """读取订单详情（items 反序列化、paid 转 bool、补充 recipient 嵌套对象）。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["items"] = json.loads(d["items"]) if d.get("items") else []
    d["paid"] = bool(d.get("paid"))
    # 归一化出嵌套 recipient，便于前端直接消费
    d["recipient"] = {
        "name": d.get("recipient_name"),
        "phone": d.get("recipient_phone"),
        "address": d.get("recipient_address"),
    }
    d["logistics"] = list_logistics(order_id)
    return d


def list_orders(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """列出某用户全部订单（新→旧）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [get_order(r["order_id"]) for r in rows]


# --------------------------------------------------------------------------- #
# 订单状态流转 / 物流轨迹（模拟）
# --------------------------------------------------------------------------- #
# 状态机：created --(支付)--> paid --(发货)--> shipped --(签收)--> done
#         created --(取消)--> canceled
# 每步流转都会在 order_logistics 追加一条时间线事件，前端「物流跟踪」按 seq 回放。


def list_logistics(order_id: str) -> list[dict[str, Any]]:
    """读取订单物流时间线（事件新→旧，与主流物流 App 展示一致）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT seq, text, created_at FROM order_logistics WHERE order_id=? ORDER BY seq DESC",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _append_logistics(order_id: str, text: str) -> None:
    conn = get_conn()
    nxt = conn.execute(
        "SELECT COALESCE(MAX(seq), -1) + 1 FROM order_logistics WHERE order_id=?",
        (order_id,),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO order_logistics(order_id, seq, text, created_at) VALUES (?,?,?,?)",
        (order_id, nxt, text, _now()),
    )


def ship_order(order_id: str) -> dict[str, Any] | None:
    """模拟发货：paid -> shipped，并生成物流时间线。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    if row["status"] != "paid":
        raise ValueError(f"当前状态 {row['status']} 不可发货")
    conn.execute(
        "UPDATE orders SET status='shipped' WHERE order_id=?", (order_id,)
    )
    _append_logistics(order_id, "商家已发货，包裹正在打包出库")
    _append_logistics(order_id, "包裹已揽收，正在发往深圳转运中心")
    _append_logistics(order_id, "包裹到达深圳转运中心，正在分拣")
    conn.commit()
    return get_order(order_id)


def complete_order(order_id: str) -> dict[str, Any] | None:
    """模拟签收：shipped -> done，追加签收时间线。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    if row["status"] != "shipped":
        raise ValueError(f"当前状态 {row['status']} 不可签收")
    conn.execute(
        "UPDATE orders SET status='done' WHERE order_id=?", (order_id,)
    )
    _append_logistics(order_id, "包裹已到达配送网点，快递员正在派送")
    _append_logistics(order_id, "已签收，感谢惠顾 FloraDIY")
    conn.commit()
    return get_order(order_id)


def cancel_order(order_id: str) -> dict[str, Any] | None:
    """取消订单：仅 created/pending_payment 可取消。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    if row["status"] not in ("created", "pending_payment"):
        raise ValueError(f"当前状态 {row['status']} 不可取消")
    conn.execute(
        "UPDATE orders SET status='canceled' WHERE order_id=?", (order_id,)
    )
    _append_logistics(order_id, "订单已取消")
    conn.commit()
    return get_order(order_id)


def pay_order(
    order_id: str,
    method: str = "wechat",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """发起支付：按配置的支付渠道（默认 sandbox）调统一下单，记录 payments 行并归一化返回。

    - 沙箱渠道：下单即模拟支付成功，订单直接标记为已支付。
    - 真实渠道（微信/支付宝）：下单成功后订单保持 pending，仅当 ``mark_order_paid``
      被支付回调（验签通过）调用后才标记已支付——状态变更必须来自可信回调。

    Args:
        order_id: 本系统订单号。
        method: 支付方式（wechat/alipay/union/huabei），透传给渠道。
        extra: 渠道额外参数，如微信需 ``{"openid": ...}``、``{"description": ...}``。

    Returns:
        归一化的支付意图 dict（含 pay_params / paid / page_path / payment_id）；
        订单不存在返回 None。

    Raises:
        PaymentConfigError: 真实渠道凭据未配置（由 payment 层抛出，API 层转 4xx/5xx）。
        PaymentGatewayError: 调第三方网关网络/返回异常。
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    order = dict(row)

    provider = payment_module.get_provider()
    try:
        intent = provider.create_payment(order, method, extra)
    except payment_module.PaymentError:
        logger.exception("支付下单失败 order=%s method=%s", order_id, method)
        raise

    # 记录 payments 行：沙箱直接 paid，真实网关 pending 待回调回填
    pay_id = "P_" + uuid.uuid4().hex[:10]
    now = _now()
    pay_status = "paid" if intent.paid else "pending"
    paid_at = now if intent.paid else None
    conn.execute(
        """INSERT INTO payments (id, order_id, method, amount, status, transaction_id, created_at, paid_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (pay_id, order_id, method, intent.amount, pay_status, intent.transaction_id, now, paid_at),
    )
    if intent.paid:
        conn.execute(
            "UPDATE orders SET paid=1, status='paid', paid_at=? WHERE order_id=?",
            (now, order_id),
        )
        _append_logistics(order_id, "支付成功，商家备货中")
        add_points(
            order["user_id"],
            max(1, int(round(float(order.get("total_price") or 0)))),
            "订单消费返积分",
            order_id,
        )
    else:
        conn.execute("UPDATE orders SET status='pending_payment' WHERE order_id=?", (order_id,))
    conn.commit()

    result = intent.to_dict()
    result["payment_id"] = pay_id
    return result


def mark_order_paid(order_id: str, transaction_id: str = "") -> bool:
    """支付回调确认后标记订单与 payments 行已支付（状态机唯一可信来源）。

    由 ``api.pay_notify`` 在验签通过后调用；绝不直接被前端请求触发，避免伪造回调篡改。

    Args:
        order_id: 本系统订单号。
        transaction_id: 第三方交易号（微信/支付宝回调解包得到）。

    Returns:
        订单是否存在并已处理。
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return False
    now = _now()
    conn.execute(
        "UPDATE orders SET paid=1, status='paid', paid_at=? WHERE order_id=?",
        (now, order_id),
    )
    _append_logistics(order_id, "支付成功，商家备货中")
    # 真实网关回调确认：同样按金额发放积分（与沙箱渠道行为一致）
    add_points(
        row["user_id"],
        max(1, int(round(float(row["total_price"] or 0)))),
        "订单消费返积分",
        order_id,
    )
    # 把该订单名下所有未支付 payments 标记为已支付（通常仅一笔）
    conn.execute(
        "UPDATE payments SET status='paid', paid_at=?, transaction_id=? WHERE order_id=? AND status<>'paid'",
        (now, transaction_id, order_id),
    )
    # 兜底：若此前没有任何 payments 记录（极端情况），补一条已付记录便于对账
    cnt = conn.execute("SELECT COUNT(*) FROM payments WHERE order_id=?", (order_id,)).fetchone()[0]
    if cnt == 0:
        conn.execute(
            """INSERT INTO payments (id, order_id, method, amount, status, transaction_id, created_at, paid_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("P_" + uuid.uuid4().hex[:10], order_id, "unknown", float(row["total_price"] or 0),
             "paid", transaction_id, now, now),
        )
    conn.commit()
    return True


def get_payment_status(order_id: str) -> dict[str, Any] | None:
    """查询订单支付状态（客户端轮询兜底，用于回调不可达场景）。

    Returns:
        含 ``paid`` / ``status`` 的 dict；订单不存在返回 None。
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    return {"order_id": order_id, "paid": bool(row["paid"]), "status": row["status"]}
