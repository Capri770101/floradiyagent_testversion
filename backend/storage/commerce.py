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

from backend.storage import payment as payment_module
from backend.storage.db import get_conn

logger = logging.getLogger("commerce")


def _now() -> str:
    """当前时间字符串（本地时区，便于人工排查）。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _now_ts() -> float:
    """当前时间戳。"""
    return time.time()


def _ts(value: str) -> float:
    """解析 '%Y-%m-%d %H:%M:%S' 时间字符串为时间戳。"""
    return time.mktime(time.strptime(value, "%Y-%m-%d %H:%M:%S"))


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


# --------------------------------------------------------------------------- #
# 领券中心 / 积分商城
# --------------------------------------------------------------------------- #

#: 内置可领取/可兑换券（首次启动播种；兑换成本 points_cost 积分，0=免费领）
COUPON_OFFER_SEEDS = [
    ("OFF_FREE5", "5 元无门槛券", 5.0, 0.0, 0, -1),
    ("OFF_FULL99", "满 99 减 10 券", 10.0, 99.0, 0, -1),
    ("OFF_PTS50", "50 积分兑 15 元券", 15.0, 0.0, 50, 200),
    ("OFF_PTS100", "100 积分兑 30 元券", 30.0, 0.0, 100, 100),
]


def _seed_coupon_offers() -> None:
    """幂等播种领券中心模板（仅补缺失行，不覆盖已修改数据）。"""
    conn = get_conn()
    for oid, title, discount, min_spend, pts, stock in COUPON_OFFER_SEEDS:
        conn.execute(
            """INSERT OR IGNORE INTO coupon_offers
               (id, title, discount, min_spend, points_cost, stock, active, created_at)
               VALUES (?,?,?,?,?,?,1,?)""",
            (oid, title, discount, min_spend, pts, stock, _now()),
        )
    conn.commit()


def list_coupon_offers(user_id: str = "") -> list[dict[str, Any]]:
    """上架中的券模板（含每人限领状态：已领过则 claimed=true）。

    Args:
        user_id: 传入时附带 claimed / claimable 标记；留空则不标记。
    """
    _seed_coupon_offers()
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM coupon_offers WHERE active=1 ORDER BY points_cost ASC, discount ASC"""
    ).fetchall()
    offers: list[dict[str, Any]] = []
    for r in rows:
        o = dict(r)
        o["claimed"] = False
        if user_id:
            got = conn.execute(
                "SELECT 1 FROM coupons WHERE user_id=? AND offer_id=? LIMIT 1",
                (user_id, o["id"]),
            ).fetchone()
            o["claimed"] = bool(got)
        offers.append(o)
    return offers


def claim_coupon_offer(user_id: str, offer_id: str) -> dict[str, Any]:
    """领取一张券（points_cost=0 免费领；>0 需积分兑换）。

    Raises:
        ValueError: 模板不存在 / 未上架 / 已领过 / 积分不足 / 库存不足。
    """
    _seed_coupon_offers()
    conn = get_conn()
    offer = conn.execute(
        "SELECT * FROM coupon_offers WHERE id=? AND active=1", (offer_id,)
    ).fetchone()
    if not offer:
        raise ValueError("该券已下架或不存在")
    already = conn.execute(
        "SELECT 1 FROM coupons WHERE user_id=? AND offer_id=? LIMIT 1", (user_id, offer_id)
    ).fetchone()
    if already:
        raise ValueError("每人限领一张，你已经领过了")
    stock = int(offer["stock"])
    if stock == 0:
        raise ValueError("库存不足，已抢光")
    cost = int(offer["points_cost"])
    if cost > 0:
        balance = conn.execute(
            "SELECT balance FROM user_points WHERE user_id=?", (user_id,)
        ).fetchone()
        if not balance or int(balance["balance"]) < cost:
            raise ValueError(f"积分不足，需要 {cost} 积分")
    # 扣库存（-1 不限）
    if stock > 0:
        conn.execute(
            "UPDATE coupon_offers SET stock=stock-1 WHERE id=?", (offer_id,)
        )
    # 发券
    cid = "C_" + uuid.uuid4().hex[:10]
    conn.execute(
        """INSERT INTO coupons (id, user_id, title, discount, min_spend, status, offer_id, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            cid,
            user_id,
            offer["title"],
            float(offer["discount"]),
            float(offer["min_spend"]),
            "unused",
            offer_id,
            _now(),
        ),
    )
    # 积分兑换：扣减积分并记流水
    if cost > 0:
        add_points(user_id, -cost, f"积分兑换「{offer['title']}」")
    conn.commit()
    return dict(conn.execute("SELECT * FROM coupons WHERE id=?", (cid,)).fetchone())


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
    """把优惠券落订单（discount/coupon_id），标记为已用，返回实际抵扣金额。"""
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
    return discount


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


def _shop_scope_sql(conn, shop_ids: list[str] | None, alias: str = "") -> tuple[str, list[Any]]:
    """按店铺 scope 生成订单过滤条件。

    orders.shop_id 存的是下单时的商家名快照（与 shops.id 不一致），故同时按
    shop_id 与订单明细里的店名匹配；shop_ids=None 表示不限（admin），
    shop_ids=[] 表示未绑定店铺（无任何可见订单）。
    alias 用于联表查询（如 reviews JOIN orders o → alias='o.'）。
    """
    if shop_ids is None:
        return "", []
    if not shop_ids:
        return " AND 0", []
    names = [
        r["name"]
        for r in conn.execute(
            f"SELECT name FROM shops WHERE id IN ({','.join('?' * len(shop_ids))})", shop_ids
        )
    ]
    keys = [s for s in shop_ids if s] + [n for n in names if n]
    if not keys:
        return f" AND {alias}0", []
    ph = ",".join("?" * len(keys))
    return (
        f" AND ({alias}shop_id IN ({ph}) OR {alias}order_id IN (SELECT order_id FROM order_items WHERE shop IN ({ph})))",
        keys + keys,
    )


def merchant_stats(
    shop_ids: list[str] | None = None, shop_id: str = ""
) -> dict[str, Any]:
    """店铺维度经营统计：订单数 / GMV / 待发货 / 已完成 / 评价数。

    Args:
        shop_ids: 商家绑定店铺 id 列表（None=全部店铺，admin）；
        shop_id: 店铺 id 或店铺名（orders.shop_id 存的是商家名快照），空则按 shop_ids 汇总。
    """
    conn = get_conn()
    where, args = _shop_scope_sql(conn, shop_ids)
    if shop_id:
        sname = conn.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
        name = sname["name"] if sname else shop_id
        if args:
            where += " AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))"
            args += [shop_id, name, shop_id, name]
        else:
            where += " AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))"
            args = [shop_id, name, shop_id, name]
    and_sql = " AND status='paid'"
    pending = conn.execute(
        f"SELECT COUNT(*) FROM orders WHERE 1=1{where}{and_sql}", args
    ).fetchone()[0]
    and_sql = " AND status='done'"
    done = conn.execute(
        f"SELECT COUNT(*) FROM orders WHERE 1=1{where}{and_sql}", args
    ).fetchone()[0]
    and_sql = " AND status='canceled'"
    canceled = conn.execute(
        f"SELECT COUNT(*) FROM orders WHERE 1=1{where}{and_sql}", args
    ).fetchone()[0]
    # 汇总（含全部状态）
    total = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders WHERE 1=1{where}", args
    ).fetchone()
    ph = ",".join("?" * (len(args) // 2)) if args else ""
    rev_where, rev_args = "", []
    if shop_ids == []:
        # 无绑定商家：评价同样为空（与订单口径一致，避免泄漏全部评价）
        rev_where = " AND 1=0"
    elif args:
        rev_where = (
            f" AND (o.shop_id IN ({ph}) OR o.order_id IN (SELECT order_id FROM order_items WHERE shop IN ({ph})))"
        )
        rev_args = list(args)
    rev = conn.execute(
        f"""SELECT COUNT(*), COALESCE(AVG(r.rating),0) FROM reviews r
           JOIN orders o ON o.order_id = r.order_id WHERE 1=1{rev_where}""",
        rev_args,
    ).fetchone()
    # 今日经营（created_at 按 UTC 当日）与待付款（工作台首页大数字卡）
    today = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders WHERE 1=1{where} AND date(created_at)=date('now')",
        args,
    ).fetchone()
    pending_payment = conn.execute(
        f"SELECT COUNT(*) FROM orders WHERE 1=1{where} AND status IN ('created','pending_payment')",
        args,
    ).fetchone()[0]
    if shop_ids is not None:
        shops = conn.execute(
            f"SELECT * FROM shops WHERE id IN ({','.join('?' * len(shop_ids))}) ORDER BY created_at",
            shop_ids,
        ).fetchall()
    else:
        shops = conn.execute("SELECT * FROM shops ORDER BY created_at").fetchall()
    return {
        "order_count": int(total[0]),
        "gmv": float(total[1] or 0),
        "pending_ship": int(pending),
        "done_count": int(done),
        "canceled_count": int(canceled),
        "review_count": int(rev[0]),
        "avg_rating": float(rev[1] or 0),
        # 工作台首页：今日订单 / 今日 GMV / 待付款
        "today_order_count": int(today[0]),
        "today_gmv": float(today[1] or 0),
        "pending_payment": int(pending_payment),
        "shops": [dict(s) for s in shops],
    }


def merchant_orders(
    shop_ids: list[str] | None = None,
    shop_id: str = "",
    status: str = "",
    limit: int = 50,
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict[str, Any]]:
    """商家视角订单列表（按绑定店铺隔离，可按店铺/状态/关键词/日期范围过滤）。

    keyword 匹配：订单号 / 收货人姓名 / 收货人手机 / 商品名（order_items）；
    date_from/date_to：YYYY-MM-DD，按 created_at 当日 00:00:00 ~ 23:59:59 过滤。
    """
    conn = get_conn()
    where, args = _shop_scope_sql(conn, shop_ids)
    if shop_id:
        sname = conn.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
        name = sname["name"] if sname else shop_id
        where += " AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))"
        args += [shop_id, name, shop_id, name]
    if status:
        where += " AND status=?"
        args.append(status)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        # items 为订单快照 JSON（含商品名），order_items 可能为空（兼容旧数据）
        where += (
            " AND (order_id LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ?"
            " OR items LIKE ?"
            " OR order_id IN (SELECT order_id FROM order_items WHERE name LIKE ?))"
        )
        args += [like, like, like, like, like]
    if date_from:
        where += " AND date(created_at) >= ?"
        args.append(date_from.strip()[:10])
    if date_to:
        where += " AND date(created_at) <= ?"
        args.append(date_to.strip()[:10])
    sql = f"SELECT order_id FROM orders WHERE 1=1{where} ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    return [get_order(r["order_id"]) for r in rows]


def merchant_ship(order_id: str) -> dict[str, Any] | None:
    """商家代发货（不受订单归属限制）：paid -> shipped。"""
    return ship_order(order_id)


def merchant_reviews(
    shop_ids: list[str] | None = None, shop_id: str = ""
) -> list[dict[str, Any]]:
    """店铺维度评价列表（按绑定店铺隔离；空 scope 返回全部）。"""
    conn = get_conn()
    where, args = _shop_scope_sql(conn, shop_ids, alias="o.")
    if shop_id:
        sname = conn.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
        name = sname["name"] if sname else shop_id
        where += " AND (o.shop_id IN (?,?) OR o.order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))"
        args += [shop_id, name, shop_id, name]
    rows = conn.execute(
        f"""SELECT r.* FROM reviews r
            JOIN orders o ON o.order_id = r.order_id
            WHERE 1=1{where} ORDER BY r.created_at DESC LIMIT 100""",
        args,
    ).fetchall()
    return [dict(r) for r in rows]


def merchant_review_get(
    review_id: str, shop_ids: list[str] | None = None
) -> dict[str, Any] | None:
    """按 ID 取单条评价（带商家范围校验；越界/不存在返回 None）。"""
    conn = get_conn()
    where, args = _shop_scope_sql(conn, shop_ids, alias="o.")
    row = conn.execute(
        f"""SELECT r.* FROM reviews r
            JOIN orders o ON o.order_id = r.order_id
            WHERE r.id=? AND 1=1{where}""",
        [review_id, *args],
    ).fetchone()
    return dict(row) if row else None


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
    """列出某方案的可见评价（新→旧，含用户昵称）；plan_id 为空返回全部。

    只返回 status='visible'（管理后台隐藏/删除的评价不向 C 端展示）。
    """
    conn = get_conn()
    if plan_id:
        rows = conn.execute(
            """SELECT r.*, u.nickname FROM reviews r
               LEFT JOIN users u ON u.id = r.user_id
               WHERE r.plan_id=? AND r.status='visible' ORDER BY r.created_at DESC LIMIT ?""",
            (plan_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT r.*, u.nickname FROM reviews r
               LEFT JOIN users u ON u.id = r.user_id
               WHERE r.status='visible' ORDER BY r.created_at DESC LIMIT ?""",
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
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """更新购物车项数量或勾选状态；任一为 None 则不改该字段。

    必须传 user_id 做归属校验（WHERE item_id=? AND user_id=?），防止越权改他人购物车项（IDOR）。
    user_id 缺失时直接拒绝，绝不按 item_id 裸查。
    """
    if not user_id:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM cart_items WHERE item_id=? AND user_id=?", (item_id, user_id)
    ).fetchone()
    if not row:
        return None
    if qty is not None:
        qty = max(1, int(qty))
        conn.execute(
            "UPDATE cart_items SET qty=?, updated_at=? WHERE item_id=? AND user_id=?",
            (qty, _now(), item_id, user_id),
        )
    if selected is not None:
        conn.execute(
            "UPDATE cart_items SET selected=?, updated_at=? WHERE item_id=? AND user_id=?",
            (1 if selected else 0, _now(), item_id, user_id),
        )
    conn.commit()
    return _row_to_dict(
        conn.execute(
            "SELECT * FROM cart_items WHERE item_id=? AND user_id=?", (item_id, user_id)
        ).fetchone()
    )


def merge_cart(from_user_id: str, to_user_id: str) -> int:
    """把 from 用户的购物车并入 to 用户：同方案数量相加，不同方案转移归属。

    用于「游客匿名 uid 购物车 → 登录账号」合并；返回并入的条数。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM cart_items WHERE user_id=? ORDER BY created_at ASC", (from_user_id,)
    ).fetchall()
    merged = 0
    for r in rows:
        existing = conn.execute(
            "SELECT * FROM cart_items WHERE user_id=? AND plan_id=?", (to_user_id, r["plan_id"])
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE cart_items SET qty=qty+?, updated_at=? WHERE item_id=?",
                (r["qty"], _now(), existing["item_id"]),
            )
        else:
            conn.execute(
                "UPDATE cart_items SET user_id=?, updated_at=? WHERE item_id=?",
                (to_user_id, _now(), r["item_id"]),
            )
        merged += 1
    conn.commit()
    return merged


def remove_cart_item(item_id: str, user_id: str | None = None) -> bool:
    """删除购物车项，返回是否真的删到了。

    必须传 user_id 做归属校验（WHERE item_id=? AND user_id=?），防止越权删他人购物车项（IDOR）。
    user_id 缺失时直接返回 False，绝不按 item_id 裸删。
    """
    if not user_id:
        return False
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM cart_items WHERE item_id=? AND user_id=?", (item_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# 订单
# --------------------------------------------------------------------------- #


def _expire_unpaid_order(conn, row) -> bool:
    """懒过期：created/pending_payment 订单超过支付时限 → 自动取消并返还优惠券。

    Returns:
        True 表示本次发生了过期取消。
    """
    status = row["status"]
    if status not in ("created", "pending_payment"):
        return False
    expires_at = row["expires_at"]
    if not expires_at:
        return False
    try:
        expired = _now_ts() > _ts(expires_at)
    except ValueError:
        return False
    if not expired:
        return False
    conn.execute(
        "UPDATE orders SET status='canceled' WHERE order_id=? AND status=?",
        (row["order_id"], status),
    )
    _append_logistics(row["order_id"], "超过支付时限，订单已自动取消")
    # 返还该订单占用（已标记 used）的优惠券
    cid = row["coupon_id"]
    if cid:
        conn.execute(
            """UPDATE coupons SET status='unused', order_id=NULL, used_at=NULL
               WHERE id=? AND status='used'""",
            (cid,),
        )
    conn.commit()
    return True


def _order_remaining_seconds(row) -> int:
    """订单剩余支付秒数（已支付/已过期返回 0）。"""
    if row["status"] in ("created", "pending_payment") and row["expires_at"]:
        try:
            return max(0, int(_ts(row["expires_at"]) - _now_ts()))
        except ValueError:
            return 0
    return 0


def create_order(
    user_id: str,
    items: list[dict[str, Any]],
    recipient: dict[str, Any] | None = None,
    delivery: str | None = None,
    note: str | None = None,
    address_id: str | None = None,
) -> dict[str, Any]:
    """创建订单：服务端按目录取价计算总额、自动抵扣最优优惠券、落库（含收货信息），
    并从购物车移除带 item_id 的项。

    安全：**价格一律以目录（repo.get_plan）为准，绝不信客户端传价**（review P0：
    POST /orders 曾直接按客户端 price×qty 计总额，可被篡改为任意低价）。
    方案不存在 → ValueError（接口层转 400）。

    Args:
        address_id: 收货地址 id（用户已存地址时传此即可）；未传或找不到时回退 recipient 手填。
    """
    conn = get_conn()
    from backend.storage.repository import repo  # 延迟导入，避免循环依赖

    priced: list[dict[str, Any]] = []
    for it in items:
        pid = it.get("plan_id")
        plan = repo.get_plan(pid) if pid else None
        if not plan:
            raise ValueError(f"方案不存在或已下架: {pid}")
        priced.append(
            {
                **it,
                "price": float(plan["price"]),  # 服务端价格覆盖客户端传入值
                "name": plan.get("name") or it.get("name", ""),
            }
        )
    total = sum(float(i["price"]) * max(1, int(i.get("qty", 1))) for i in priced)
    order_id = "O_" + uuid.uuid4().hex[:10]
    first = priced[0] if priced else {}
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
            paid, status, expires_at, address_id, recipient_name, recipient_phone, recipient_address,
            delivery_time, note, created_at)
           VALUES (?,?,?,?,?,?,?,0,'created',?,?,?,?,?,?,?,?)""",
        (
            order_id,
            user_id,
            first.get("plan_id"),
            "plan",
            first.get("shop"),
            json.dumps(priced, ensure_ascii=False),
            total,
            _expires_at_str(),
            saved_addr["id"] if saved_addr else None,
            rname,
            rphone,
            raddr,
            delivery,
            note,
            _now(),
        ),
    )
    # 自动抵扣最优可用优惠券（新人立减等）；折扣落订单并标记券已用。
    # 防御：total<=0 时跳过，避免给 0 元单套用门槛为 0 的券。
    if total > 0:
        apply_best_coupon(order_id, user_id, total)
    # 若购物车项带 item_id，下单后移除（避免重复结算）
    for it in priced:
        iid = it.get("item_id")
        if iid:
            conn.execute("DELETE FROM cart_items WHERE item_id=?", (iid,))
    _append_logistics(order_id, "订单已创建，等待支付")
    conn.commit()
    # 通知中心（模块一）：下单成功落站内通知
    from backend.storage import notify

    notify.try_create(
        user_id, notify.T_ORDER, "订单已创建",
        f"{rname or '收花人'}的花束订单已提交，等待支付",
        ref_type="order", ref_id=order_id,
    )
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


def _expires_at_str() -> str:
    """订单支付截止时间字符串（now + order_pay_timeout_minutes）。"""
    from backend.config import settings

    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(_now_ts() + settings.order_pay_timeout_minutes * 60),
    )


def _enrich_order_item_images(conn: Any, items: list[dict]) -> None:
    """按商品 plan_id 回填订单明细缺失的商品图（effect_image_url）。

    兼容历史订单：下单时未快照图片的明细，读取时从 plans 表补齐，
    保证订单详情/物流页能展示真实商品图；已带 image 的明细不覆盖。
    """
    need = [it for it in items if not (it.get("image") or it.get("effect_image_url"))]
    if not need:
        return
    # 商品图：优先 product_id（DIY 匹配到的店铺单品），否则 plan_id（现有方案）
    ids = list({str(it.get("product_id") or it.get("plan_id") or "") for it in need if it.get("product_id") or it.get("plan_id")})
    if not ids:
        return
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, effect_image_url FROM plans WHERE id IN ({ph})",
        ids,
    ).fetchall()
    img_by_id = {r["id"]: r["effect_image_url"] for r in rows if r["effect_image_url"]}
    for it in need:
        pid = str(it.get("product_id") or it.get("plan_id") or "")
        if pid in img_by_id:
            it["image"] = img_by_id[pid]


def get_order(order_id: str) -> dict[str, Any] | None:
    """读取订单详情（items 反序列化、paid 转 bool、补充 recipient 嵌套对象）。

    读取时执行懒过期：超时未支付的订单自动转为 canceled 并返还优惠券。
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    _expire_unpaid_order(conn, row)
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    d = dict(row)
    d["items"] = json.loads(d["items"]) if d.get("items") else []
    _enrich_order_item_images(conn, d["items"])
    d["paid"] = bool(d.get("paid"))
    # 归一化出嵌套 recipient，便于前端直接消费
    d["recipient"] = {
        "name": d.get("recipient_name"),
        "phone": d.get("recipient_phone"),
        "address": d.get("recipient_address"),
    }
    d["logistics"] = list_logistics(order_id)
    d["remaining_seconds"] = _order_remaining_seconds(row)
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


def add_logistics_event(order_id: str, text: str) -> dict[str, Any] | None:
    """商家手动追加物流节点（仅配送中 shipped 状态可追加）。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    _expire_unpaid_order(conn, row)
    if row["status"] != "shipped":
        raise ValueError(f"当前状态 {row['status']} 不可追加物流节点")
    text = (text or "").strip()
    if not text:
        raise ValueError("物流节点内容不能为空")
    _append_logistics(order_id, text)
    conn.commit()
    # 通知中心（模块一）：商家追加物流节点通知顾客
    from backend.storage import notify

    notify.try_create(
        row["user_id"], notify.T_LOGISTICS, "物流更新",
        text[:120],
        ref_type="order", ref_id=order_id,
    )
    return get_order(order_id)


def ship_order(order_id: str) -> dict[str, Any] | None:
    """模拟发货：paid -> shipped，并生成物流时间线。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    _expire_unpaid_order(conn, row)
    if row["status"] != "paid":
        raise ValueError(f"当前状态 {row['status']} 不可发货")
    conn.execute(
        "UPDATE orders SET status='shipped' WHERE order_id=?", (order_id,)
    )
    _append_logistics(order_id, "商家已发货，包裹正在打包出库")
    _append_logistics(order_id, "包裹已揽收，正在发往深圳转运中心")
    _append_logistics(order_id, "包裹到达深圳转运中心，正在分拣")
    conn.commit()
    # 通知中心（模块一）：发货通知顾客
    from backend.storage import notify

    notify.try_create(
        row["user_id"], notify.T_ORDER, "订单已发货",
        f"订单 {order_id} 已由商家发货，正在配送途中",
        ref_type="order", ref_id=order_id,
    )
    return get_order(order_id)


def complete_order(order_id: str) -> dict[str, Any] | None:
    """模拟签收：shipped -> done，追加签收时间线。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    _expire_unpaid_order(conn, row)
    if row["status"] != "shipped":
        raise ValueError(f"当前状态 {row['status']} 不可签收")
    conn.execute(
        "UPDATE orders SET status='done' WHERE order_id=?", (order_id,)
    )
    _append_logistics(order_id, "包裹已到达配送网点，快递员正在派送")
    _append_logistics(order_id, "已签收，感谢惠顾 FloraDIY")
    conn.commit()
    # 通知中心（模块一）：签收通知顾客（可去评价）
    from backend.storage import notify

    notify.try_create(
        row["user_id"], notify.T_ORDER, "订单已签收",
        f"订单 {order_id} 已签收，期待您对本次花束的反馈",
        ref_type="order", ref_id=order_id,
    )
    return get_order(order_id)


def cancel_order(order_id: str) -> dict[str, Any] | None:
    """取消订单：仅 created/pending_payment 可取消。订单不存在返回 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return None
    _expire_unpaid_order(conn, row)
    if row["status"] not in ("created", "pending_payment"):
        raise ValueError(f"当前状态 {row['status']} 不可取消")
    conn.execute(
        "UPDATE orders SET status='canceled' WHERE order_id=?", (order_id,)
    )
    _append_logistics(order_id, "订单已取消")
    # 返还该订单占用（已标记 used）的优惠券（与过期自动取消一致）
    cid = row["coupon_id"]
    if cid:
        conn.execute(
            """UPDATE coupons SET status='unused', order_id=NULL, used_at=NULL
               WHERE id=? AND status='used'""",
            (cid,),
        )
    conn.commit()
    # 通知中心（模块一）：取消通知顾客
    from backend.storage import notify

    notify.try_create(
        row["user_id"], notify.T_ORDER, "订单已取消",
        f"订单 {order_id} 已取消，如已使用优惠券将自动返还",
        ref_type="order", ref_id=order_id,
    )
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
    _expire_unpaid_order(conn, row)
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    order = dict(row)
    if order["status"] not in ("created", "pending_payment"):
        raise ValueError(f"当前状态 {order['status']} 不可支付")

    # 优惠券抵扣：应付金额 = total_price - discount（各支付渠道按此金额下单收款）。
    # 不改动订单原值，仅向支付渠道传入应付金额，保证「展示的折扣」与「实付」一致。
    pay_order_ctx = dict(order)
    payable = max(0.0, float(order.get("total_price") or 0) - float(order.get("discount") or 0))
    pay_order_ctx["total_price"] = payable

    provider = payment_module.get_provider()
    try:
        intent = provider.create_payment(pay_order_ctx, method, extra)
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
        # 幂等：仅当本次成功把订单从未支付翻转为已支付时才发积分/通知，
        # 避免沙箱重复调用（双击）重复发放积分。
        cur = conn.execute(
            "UPDATE orders SET paid=1, status='paid', paid_at=? WHERE order_id=? AND paid=0",
            (now, order_id),
        )
        _append_logistics(order_id, "支付成功，商家备货中")
        if cur.rowcount > 0:
            add_points(
                order["user_id"],
                max(1, int(round(float(order.get("total_price") or 0)))),
                "订单消费返积分",
                order_id,
            )
    else:
        conn.execute("UPDATE orders SET status='pending_payment' WHERE order_id=?", (order_id,))
    conn.commit()

    if intent.paid:
        # 通知中心（模块一）：沙箱渠道下单即支付成功
        from backend.storage import notify

        notify.try_create(
            order["user_id"], notify.T_ORDER, "支付成功",
            f"订单 {order_id} 已支付 ¥{intent.amount}，商家备货中",
            ref_type="order", ref_id=order_id,
        )

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
    # 幂等：订单已支付则直接返回（重复回调不再重复发积分/插支付行）
    if row["paid"]:
        return True
    now = _now()
    conn.execute(
        "UPDATE orders SET paid=1, status='paid', paid_at=? WHERE order_id=? AND paid=0",
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
    # 通知中心（模块一）：真实网关回调确认支付成功
    from backend.storage import notify

    notify.try_create(
        row["user_id"], notify.T_ORDER, "支付成功",
        f"订单 {order_id} 已支付 ¥{float(row['total_price'] or 0)}，商家备货中",
        ref_type="order", ref_id=order_id,
    )
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
