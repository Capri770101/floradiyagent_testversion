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
) -> dict[str, Any]:
    """创建订单：计算总额、落库（含收货信息），并从购物车移除带 item_id 的项。"""
    conn = get_conn()
    total = sum(float(it.get("price", 0)) * int(it.get("qty", 1)) for it in items)
    order_id = "O_" + uuid.uuid4().hex[:10]
    first = items[0] if items else {}
    # 兼容 recipient 两种命名风格（前端 name/phone/address 或 recipient_name/...）
    r = recipient or {}
    rname = r.get("name") or r.get("recipient_name")
    rphone = r.get("phone") or r.get("recipient_phone")
    raddr = r.get("address") or r.get("recipient_address")
    conn.execute(
        """INSERT INTO orders
           (order_id, user_id, plan_id, plan_type, shop_id, items, total_price,
            paid, status, recipient_name, recipient_phone, recipient_address, delivery_time, note, created_at)
           VALUES (?,?,?,?,?,?,?,0,'created',?,?,?,?,?,?)""",
        (
            order_id,
            user_id,
            first.get("plan_id"),
            "plan",
            first.get("shop"),
            json.dumps(items, ensure_ascii=False),
            total,
            rname,
            rphone,
            raddr,
            delivery,
            note,
            _now(),
        ),
    )
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
