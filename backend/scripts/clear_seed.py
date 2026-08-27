"""scripts/clear_seed.py —— 一键清空种子/演示数据（计划书 T4-3）。

清空范围（全部可重灌）：
- 商品目录种子：categories / plans / shop_plans / shops / merchant_shops /
  shop_profiles / shop_styles / shop_scenes
- 领券中心种子：coupon_offers 及用户领取的关联券（coupons.offer_id 非空）
- 演示账号（capri_demo）的订单：orders / order_items / order_logistics / payments

保留范围（用户真实数据）：
- users / sessions / messages / diy_plans（用户 DIY 资产）/
  cart / addresses / favorites / 用户自有订单

重灌：python scripts/seed_demo.py && python -m storage.catalog 由后端 init 时自动 seed_catalog
（uvicorn 启动即触发 seed_catalog；如已在运行，重启后端即可重灌目录种子）。

运行：python scripts/clear_seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from backend.storage.db import get_conn, init_db

DEMO_USER = 'capri_demo'
TABLES_SEED = ['shop_scenes', 'shop_styles', 'shop_profiles', 'merchant_shops', 'shop_plans', 'shops', 'plans', 'categories']

def clear() -> None:
    init_db()
    conn = get_conn()
    with conn:
        for t in TABLES_SEED:
            n = conn.execute(f'DELETE FROM {t}').rowcount
            print(f'  - {t}: 清空 {n} 行')
        n = conn.execute('DELETE FROM coupons WHERE offer_id IS NOT NULL').rowcount
        print(f'  - coupons(offer 关联): 清空 {n} 行')
        n = conn.execute('DELETE FROM coupon_offers').rowcount
        print(f'  - coupon_offers: 清空 {n} 行')
        uid = conn.execute('SELECT id FROM users WHERE username=?', (DEMO_USER,)).fetchone()
        if uid:
            uid = uid['id']
            rows = conn.execute('SELECT order_id FROM orders WHERE user_id=?', (uid,)).fetchall()
            oids = [r['order_id'] for r in rows]
            if oids:
                ph = ','.join('?' * len(oids))
                conn.execute(f'DELETE FROM order_logistics WHERE order_id IN ({ph})', oids)
                conn.execute(f'DELETE FROM order_items WHERE order_id IN ({ph})', oids)
                conn.execute(f'DELETE FROM payments WHERE order_id IN ({ph})', oids)
                conn.execute(f'DELETE FROM orders WHERE order_id IN ({ph})', oids)
            print(f'  演示账号 {DEMO_USER}: 清空订单 {len(oids)} 条')
        else:
            print(f'  演示账号 {DEMO_USER}: 不存在，跳过')
    print('\n已清空种子/演示数据。重灌：')
    print('  1) python scripts/seed_demo.py   （演示订单）')
    print('  2) 重启后端 uvicorn               （启动时自动 seed_catalog 灌目录种子）')
if __name__ == '__main__':
    clear()
