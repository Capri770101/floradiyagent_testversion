"""scripts/seed_demo.py —— 灌入可控的演示订单数据。

目的：让前端「我的订单 / 物流追踪」展示页在 dev 阶段有真实可读的数据
（测试阶段不管数据真假，重点是页面能完整呈现各状态）。

做法：
- 注册一个可登录的演示账号 capri_demo / 123456（已存在则跳过注册，但会清空其旧订单重灌）。
- 用 DB 内真实存在的 plan_id / shop_id 下 5 单，覆盖 created / paid / shipped / done / canceled。
- 每单带收货人 + 完整的物流时间线（order_logistics），供物流页回放。

运行：python scripts/seed_demo.py
依赖：项目根目录在 sys.path（脚本自动处理）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 项目根目录加入 path，确保能 import config / storage
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from security import register_user  # noqa: E402
from storage import commerce  # noqa: E402
from storage.db import get_conn, init_db  # noqa: E402

DEMO_USER = "capri_demo"
DEMO_PASS = "123456"
DEMO_NICK = "演示小木"

# 演示订单：plan_id 与 shop_id 必须存在于 DB 的 plans / shops 表
DEMO_ORDERS = [
    {
        "plan_id": "P001", "shop": "S001", "qty": 1,
        "name": "康乃馨感恩花束",
        "status": "created", "delivery_time": "2026-08-20 14:00 前送达",
        "recipient": {"name": "李慕白", "phone": "13800001234", "address": "广东省深圳市盐田区海山路 18 号悦千山小区 3 栋 1502"},
        "logistics": [
            "订单已创建，等待支付",
        ],
    },
    {
        "plan_id": "P004", "shop": "S004", "qty": 2,
        "name": "满天星小清新花束",
        "status": "paid", "delivery_time": "2026-08-19 18:00 前送达",
        "recipient": {"name": "周晓彤", "phone": "13900005678", "address": "广东省深圳市福田区福华路 88 号购物公园 B 座 2201"},
        "logistics": [
            "订单已创建，等待支付",
            "支付成功，商家备货中",
        ],
    },
    {
        "plan_id": "P002", "shop": "S001", "qty": 1,
        "name": "玫瑰轻奢花盒",
        "status": "shipped", "delivery_time": "2026-08-18 12:00 前送达",
        "recipient": {"name": "陈思远", "phone": "13700008899", "address": "广东省深圳市南山区科技园南区科兴科学园 B 栋 9 楼"},
        "logistics": [
            "订单已创建，等待支付",
            "支付成功，商家备货中",
            "商家已发货，包裹正在打包出库",
            "包裹已揽收，正在发往深圳转运中心",
            "包裹到达深圳转运中心，正在分拣",
        ],
    },
    {
        "plan_id": "P003", "shop": "S002", "qty": 1,
        "name": "向日葵花束",
        "status": "done", "delivery_time": "2026-08-15 10:00 前送达",
        "recipient": {"name": "林暖暖", "phone": "13600002345", "address": "广东省深圳市罗湖区人民南路 2028 号金光华广场 1508"},
        "logistics": [
            "订单已创建，等待支付",
            "支付成功，商家备货中",
            "商家已发货，包裹正在打包出库",
            "包裹已揽收，正在发往深圳转运中心",
            "包裹到达深圳转运中心，正在分拣",
            "包裹已签收，感谢您的惠顾，期待再次相见",
        ],
    },
    {
        "plan_id": "P005", "shop": "S005", "qty": 1,
        "name": "郁金香春日花束",
        "status": "canceled", "delivery_time": "",
        "recipient": {"name": "黄子轩", "phone": "13500007654", "address": "广东省深圳市宝安区新安街道前进一路 99 号"},
        "logistics": [
            "订单已创建，等待支付",
            "超过支付时限，订单已自动取消",
        ],
    },
]


def ensure_demo_user() -> str:
    """注册（或复用）演示账号，返回 user_id。"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE username=?", (DEMO_USER,)).fetchone()
    if row:
        return row["id"]
    uid, _token = register_user(DEMO_USER, DEMO_PASS, DEMO_NICK)
    return uid


def clear_old_orders(uid: str) -> None:
    """清掉该演示账号旧订单，保证重灌幂等、演示数据干净。"""
    conn = get_conn()
    old = [r["order_id"] for r in conn.execute(
        "SELECT order_id FROM orders WHERE user_id=?", (uid,)).fetchall()]
    if not old:
        return
    ph = ",".join("?" * len(old))
    conn.execute(f"DELETE FROM order_logistics WHERE order_id IN ({ph})", old)
    conn.execute(f"DELETE FROM orders WHERE order_id IN ({ph})", old)
    print(f"  已清理旧演示订单 {len(old)} 条")


def seed() -> None:
    init_db()  # 确保表结构就绪（幂等）
    uid = ensure_demo_user()
    clear_old_orders(uid)
    print(f"演示账号 {DEMO_USER} / {DEMO_PASS} (uid={uid})")

    conn = get_conn()
    for spec in DEMO_ORDERS:
        # create_order 会按 repo.get_plan 取价、自动落库 + 追加首条物流
        order = commerce.create_order(
            user_id=uid,
            items=[{"plan_id": spec["plan_id"], "qty": spec["qty"], "shop": spec["shop"], "name": spec["name"]}],
            recipient=spec["recipient"],
            delivery=spec["delivery_time"] or None,
        )
        order_id = order["order_id"]
        # 覆盖状态为演示目标状态（create_order 默认 created）
        paid = 1 if spec["status"] in ("paid", "shipped", "done") else 0
        conn.execute(
            "UPDATE orders SET status=?, paid=?, recipient_name=?, recipient_phone=?, recipient_address=?, delivery_time=? WHERE order_id=?",
            (spec["status"], paid, spec["recipient"]["name"], spec["recipient"]["phone"],
             spec["recipient"]["address"], spec["delivery_time"] or None, order_id),
        )
        # 重写物流时间线，使其与演示状态一致、叙述完整
        conn.execute("DELETE FROM order_logistics WHERE order_id=?", (order_id,))
        for seq, text in enumerate(spec["logistics"]):
            conn.execute(
                "INSERT INTO order_logistics(order_id, seq, text, created_at) VALUES (?,?,?,datetime('now','-{} hours'))".format(
                    (len(spec["logistics"]) - seq) * 3),
                (order_id, seq, text),
            )
        conn.commit()
        print(f"  + {order_id} [{spec['status']}] {spec['name']} ×{spec['qty']} @ {spec['shop']}")

    print("演示数据灌入完成 ✅")


if __name__ == "__main__":
    seed()
