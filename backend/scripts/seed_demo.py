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

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from backend.security import register_user
from backend.storage import chats, commerce, notify
from backend.storage.db import get_conn, init_db

DEMO_USER = 'capri_demo'
DEMO_PASS = '123456'
DEMO_NICK = '演示小木'
DEMO_ORDERS = [{'plan_id': 'P001', 'shop': 'S001', 'qty': 1, 'name': '康乃馨感恩花束', 'status': 'created', 'delivery_time': '2026-08-20 14:00 前送达', 'recipient': {'name': '李慕白', 'phone': '13800001234', 'address': '广东省深圳市盐田区海山路 18 号悦千山小区 3 栋 1502'}, 'logistics': ['订单已创建，等待支付']}, {'plan_id': 'P004', 'shop': 'S004', 'qty': 2, 'name': '满天星小清新花束', 'status': 'paid', 'delivery_time': '2026-08-19 18:00 前送达', 'recipient': {'name': '周晓彤', 'phone': '13900005678', 'address': '广东省深圳市福田区福华路 88 号购物公园 B 座 2201'}, 'logistics': ['订单已创建，等待支付', '支付成功，商家备货中']}, {'plan_id': 'P002', 'shop': 'S001', 'qty': 1, 'name': '玫瑰轻奢花盒', 'status': 'shipped', 'delivery_time': '2026-08-18 12:00 前送达', 'recipient': {'name': '陈思远', 'phone': '13700008899', 'address': '广东省深圳市南山区科技园南区科兴科学园 B 栋 9 楼'}, 'logistics': ['订单已创建，等待支付', '支付成功，商家备货中', '商家已发货，包裹正在打包出库', '包裹已揽收，正在发往深圳转运中心', '包裹到达深圳转运中心，正在分拣']}, {'plan_id': 'P003', 'shop': 'S002', 'qty': 1, 'name': '向日葵花束', 'status': 'done', 'delivery_time': '2026-08-15 10:00 前送达', 'recipient': {'name': '林暖暖', 'phone': '13600002345', 'address': '广东省深圳市罗湖区人民南路 2028 号金光华广场 1508'}, 'logistics': ['订单已创建，等待支付', '支付成功，商家备货中', '商家已发货，包裹正在打包出库', '包裹已揽收，正在发往深圳转运中心', '包裹到达深圳转运中心，正在分拣', '包裹已签收，感谢您的惠顾，期待再次相见']}, {'plan_id': 'P005', 'shop': 'S005', 'qty': 1, 'name': '郁金香春日花束', 'status': 'canceled', 'delivery_time': '', 'recipient': {'name': '黄子轩', 'phone': '13500007654', 'address': '广东省深圳市宝安区新安街道前进一路 99 号'}, 'logistics': ['订单已创建，等待支付', '超过支付时限，订单已自动取消']}]

def ensure_demo_user() -> str:
    """注册（或复用）演示账号，返回 user_id。"""
    conn = get_conn()
    row = conn.execute('SELECT id FROM users WHERE username=?', (DEMO_USER,)).fetchone()
    if row:
        return row['id']
    uid, _token = register_user(DEMO_USER, DEMO_PASS, DEMO_NICK)
    return uid

def clear_old_orders(uid: str) -> None:
    """清掉该演示账号旧订单，保证重灌幂等、演示数据干净。"""
    conn = get_conn()
    old = [r['order_id'] for r in conn.execute('SELECT order_id FROM orders WHERE user_id=?', (uid,)).fetchall()]
    if not old:
        return
    ph = ','.join('?' * len(old))
    conn.execute(f'DELETE FROM order_logistics WHERE order_id IN ({ph})', old)
    conn.execute(f'DELETE FROM orders WHERE order_id IN ({ph})', old)
    print(f'  已清理旧演示订单 {len(old)} 条')

def seed() -> None:
    init_db()
    uid = ensure_demo_user()
    clear_old_orders(uid)
    print(f'演示账号 {DEMO_USER} / {DEMO_PASS} (uid={uid})')
    conn = get_conn()
    for spec in DEMO_ORDERS:
        order = asyncio.run(commerce.create_order(user_id=uid, items=[{'plan_id': spec['plan_id'], 'qty': spec['qty'], 'shop': spec['shop'], 'name': spec['name']}], recipient=spec['recipient'], delivery=spec['delivery_time'] or None))
        order_id = order['order_id']
        paid = 1 if spec['status'] in ('paid', 'shipped', 'done') else 0
        conn.execute('UPDATE orders SET status=?, paid=?, recipient_name=?, recipient_phone=?, recipient_address=?, delivery_time=? WHERE order_id=?', (spec['status'], paid, spec['recipient']['name'], spec['recipient']['phone'], spec['recipient']['address'], spec['delivery_time'] or None, order_id))
        conn.execute('DELETE FROM order_logistics WHERE order_id=?', (order_id,))
        for seq, text in enumerate(spec['logistics']):
            conn.execute("INSERT INTO order_logistics(order_id, seq, text, created_at) VALUES (?,?,?,datetime('now','-{} hours'))".format((len(spec['logistics']) - seq) * 3), (order_id, seq, text))
        conn.commit()
        print(f"  + {order_id} [{spec['status']}] {spec['name']} ×{spec['qty']} @ {spec['shop']}")
    chat = asyncio.run(chats.get_or_create_chat('S001', uid))
    has_msgs = conn.execute('SELECT 1 FROM chat_messages WHERE chat_id=? LIMIT 1', (chat['id'],)).fetchone()
    if not has_msgs:
        asyncio.run(chats.send_message(chat['id'], chats.SENDER_USER, '你好，我的订单可以改配送时间吗？'))
        asyncio.run(chats.send_message(chat['id'], chats.SENDER_MERCHANT, '您好，可以的。请问希望改到几点呢？确认后我帮您安排～'))
        print(f"  + 演示会话 {chat['id']}（顾客 1 条 + 商家 1 条回复）")
    done_order = conn.execute("SELECT order_id FROM orders WHERE user_id=? AND status='done' LIMIT 1", (uid,)).fetchone()
    if done_order:
        review = conn.execute('SELECT * FROM reviews WHERE order_id=? LIMIT 1', (done_order['order_id'],)).fetchone()
        if not review:
            review = asyncio.run(commerce.create_review(uid, done_order['order_id'], 5, '花很新鲜，包装精致，配送也准时，下次还来！'))
        asyncio.run(chats.reply_review(review['id'], '感谢您的认可！小店会继续用心做好每一束花，期待再次为您服务～'))
        print(f"  + 评价回复已灌入（{review['id']}）")
    conn.execute('DELETE FROM notifications WHERE user_id=?', (uid,))
    demo_notifications = [('order_status', '订单已支付', '订单已支付，商家备货中，请留意物流更新', 'order'), ('logistics', '物流更新', '包裹已揽收，正在发往深圳转运中心', 'order'), ('review_reply', '商家回复了你的评价', '感谢您的认可！小店会继续用心做好每一束花', 'order'), ('aftersale', '退款已到账', '您的售后申请已通过，退款原路返回', 'aftersale'), ('announcement', '平台公告', '跳舞兰夏季花材上新，欢迎选购', '')]
    for i, (ntype, title, body, ref) in enumerate(demo_notifications):
        n = asyncio.run(notify.create_notification(uid, ntype, title, body, ref_type=ref, ref_id=done_order['order_id'] if done_order and ref else ''))
        if n and i >= 2:
            asyncio.run(notify.mark_read(uid, [n['id']]))
    print(f'  + 演示通知 {len(demo_notifications)} 条（前 2 条未读）')
    from backend.storage.diy import save_diy_plan
    demo_diy = {'name': '北欧 · 生日花束', 'recipient': '朋友', 'occasion': '生日', 'style': '北欧', 'budget_num': 299, 'design': {'main_flowers': [{'name': '洋桔梗', 'role': '主花', 'flower_language': ['美好']}], 'fillers': [{'name': '满天星', 'role': '填充'}], 'foliage': [{'name': '尤加利', 'role': '叶材'}], 'color_scheme': ['雾蓝', '奶白'], 'packaging': '礼盒', 'meaning': '祝生日快乐，愿你如花般从容绽放', 'difficulty': '进阶', 'est_time': 45, 'shelf_life': '约 5-7 天', 'suitable_for': ['朋友', '同事', '生日'], 'caution': '洋桔梗花茎较脆，拆包装时请轻拿轻放；满天星娇嫩，忌暴晒', 'mood_tags': ['温柔', '宁静']}, 'diy_steps': ['斜剪花枝根部并醒花 2 小时', '按雾蓝→奶白间隔插入花泥', '插入洋桔梗作为主花定位', '点缀满天星与尤加利', '系上缎带，放入礼盒'], 'care_tips': '收到后斜剪根部、每日换水，雾蓝洋桔梗可养一周左右', 'card_message': '岁岁常欢愉，年年皆胜意', 'budget_breakdown': {'花材': 168, '包装': 68, '手工费': 63}}
    diy_res = asyncio.run(save_diy_plan(demo_diy, uid))
    if diy_res['saved']:
        print(f"  + 演示 DIY 方案 {diy_res['plan_id']}（卡片扩充字段已灌入）")
    if not asyncio.run(commerce.is_favorite(uid, 'P001')):
        asyncio.run(commerce.add_favorite(uid, 'P001'))
        print('  + 演示收藏 P001（韩式风格偏好信号）')
    print('演示数据灌入完成')
if __name__ == '__main__':
    seed()
