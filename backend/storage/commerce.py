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

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from backend.storage import db_async as dba
from backend.storage import payment as payment_module

logger = logging.getLogger('commerce')

def _now() -> str:
    """当前时间字符串（本地时区，便于人工排查）。"""
    return time.strftime('%Y-%m-%d %H:%M:%S')

def _now_ts() -> float:
    """当前时间戳。"""
    return time.time()

def _ts(value: str) -> float:
    """解析 '%Y-%m-%d %H:%M:%S' 时间字符串为时间戳。"""
    return time.mktime(time.strptime(value, '%Y-%m-%d %H:%M:%S'))

def _row_to_dict(row: Any) -> dict[str, Any]:
    """sqlite3.Row -> dict，并把 selected 转成 bool。"""
    d = dict(row)
    d['selected'] = bool(d.get('selected'))
    return d

async def _ensure_welcome_coupon(user_id: str) -> None:
    async with dba.transaction() as c:
        '新用户自动发放一张「新人立减 10 元」无门槛券（幂等：已有券则不重复发）。'
        has = _fetchone(await c.execute('SELECT 1 FROM coupons WHERE user_id=? LIMIT 1', (user_id,)))
        if has:
            return
        await c.execute('INSERT INTO coupons (id, user_id, title, discount, min_spend, status, created_at)\n           VALUES (?,?,?,?,?,?,?)', ('C_' + uuid.uuid4().hex[:10], user_id, '新人立减 10 元', 10.0, 0.0, 'unused', _now()))

async def list_coupons(user_id: str) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '列出用户优惠券（自动发放新人券），未使用的排前面。'
        await _ensure_welcome_coupon(user_id)
        rows = await c.execute("SELECT * FROM coupons WHERE user_id=?\n           ORDER BY (status='unused') DESC, created_at DESC", (user_id,))
        return [dict(r) for r in rows]
COUPON_OFFER_SEEDS = [('OFF_FREE5', '5 元无门槛券', 5.0, 0.0, 0, -1), ('OFF_FULL99', '满 99 减 10 券', 10.0, 99.0, 0, -1), ('OFF_PTS50', '50 积分兑 15 元券', 15.0, 0.0, 50, 200), ('OFF_PTS100', '100 积分兑 30 元券', 30.0, 0.0, 100, 100)]

async def _seed_coupon_offers() -> None:
    async with dba.transaction() as c:
        '幂等播种领券中心模板（仅补缺失行，不覆盖已修改数据）。'
        for oid, title, discount, min_spend, pts, stock in COUPON_OFFER_SEEDS:
            await c.execute('INSERT INTO coupon_offers\n               (id, title, discount, min_spend, points_cost, stock, active, created_at)\n               VALUES (?,?,?,?,?,?,1,?)\n               ON CONFLICT (id) DO NOTHING', (oid, title, discount, min_spend, pts, stock, _now()))

async def list_coupon_offers(user_id: str='') -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '上架中的券模板（含每人限领状态：已领过则 claimed=true）。\n\n    Args:\n        user_id: 传入时附带 claimed / claimable 标记；留空则不标记。\n    '
        await _seed_coupon_offers()
        rows = await c.execute('SELECT * FROM coupon_offers WHERE active=1 ORDER BY points_cost ASC, discount ASC')
        offers: list[dict[str, Any]] = []
        for r in rows:
            o = dict(r)
            o['claimed'] = False
            if user_id:
                got = _fetchone(await c.execute('SELECT 1 FROM coupons WHERE user_id=? AND offer_id=? LIMIT 1', (user_id, o['id'])))
                o['claimed'] = bool(got)
            offers.append(o)
        return offers

async def claim_coupon_offer(user_id: str, offer_id: str) -> dict[str, Any]:
    async with dba.transaction() as c:
        '领取一张券（points_cost=0 免费领；>0 需积分兑换）。\n\n    Raises:\n        ValueError: 模板不存在 / 未上架 / 已领过 / 积分不足 / 库存不足。\n    '
        await _seed_coupon_offers()
        offer = _fetchone(await c.execute('SELECT * FROM coupon_offers WHERE id=? AND active=1', (offer_id,)))
        if not offer:
            raise ValueError('该券已下架或不存在')
        already = _fetchone(await c.execute('SELECT 1 FROM coupons WHERE user_id=? AND offer_id=? LIMIT 1', (user_id, offer_id)))
        if already:
            raise ValueError('每人限领一张，你已经领过了')
        cost = int(offer['points_cost'])
        if cost > 0:
            balance = _fetchone(await c.execute('SELECT balance FROM user_points WHERE user_id=?', (user_id,)))
            if not balance or int(balance['balance']) < cost:
                raise ValueError(f'积分不足，需要 {cost} 积分')
        # 原子库存递减：先检查再递减，避免并发超领
        offer_rows = await c.execute('SELECT stock FROM coupon_offers WHERE id=?', (offer_id,))
        offer_row = _fetchone(offer_rows)
        stock = int(offer_row['stock']) if offer_row else 0
        # stock = -1 表示无限库存，无需递减
        if stock == 0:
            raise ValueError('库存不足，已抢光')
        if stock > 0:
            await c.execute('UPDATE coupon_offers SET stock=stock-1 WHERE id=?', (offer_id,))
        cid = 'C_' + uuid.uuid4().hex[:10]
        await c.execute('INSERT INTO coupons (id, user_id, title, discount, min_spend, status, offer_id, created_at)\n           VALUES (?,?,?,?,?,?,?,?)', (cid, user_id, offer['title'], float(offer['discount']), float(offer['min_spend']), 'unused', offer_id, _now()))
        if cost > 0:
            await add_points(user_id, -cost, f"积分兑换「{offer['title']}」")
        return dict(_fetchone(await c.execute('SELECT * FROM coupons WHERE id=?', (cid,))))

async def _best_coupon_for(user_id: str, total: float) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '选一张最优可用券：未使用 + 金额达标，抵扣额最大的那张。'
        row = _fetchone(await c.execute("SELECT * FROM coupons WHERE user_id=? AND status='unused' AND min_spend<=?\n           ORDER BY discount DESC LIMIT 1", (user_id, total)))
        return dict(row) if row else None

async def apply_best_coupon(order_id: str, user_id: str, total: float) -> float:
    """为已落库订单自动抵扣最优券，返回实际抵扣金额（无券/不达标为 0）。"""
    await _ensure_welcome_coupon(user_id)
    coupon = await _best_coupon_for(user_id, total)
    if not coupon:
        return 0.0
    return await apply_coupon(order_id, coupon, total)

async def apply_coupon(order_id: str, coupon: dict[str, Any], total: float) -> float:
    async with dba.transaction() as c:
        '把优惠券落订单（discount/coupon_id），标记为已用，返回实际抵扣金额。'
        discount = min(float(coupon['discount']), total)
        await c.execute('UPDATE orders SET coupon_id=?, discount=? WHERE order_id=?', (coupon['id'], discount, order_id))
        await c.execute("UPDATE coupons SET status='used', order_id=?, used_at=? WHERE id=?", (order_id, _now(), coupon['id']))
        return discount

async def get_points(user_id: str) -> dict[str, Any]:
    async with dba.transaction() as c:
        '查询用户积分余额与流水。'
        row = _fetchone(await c.execute('SELECT * FROM user_points WHERE user_id=?', (user_id,)))
        balance = int(row['balance']) if row else 0
        records = await c.execute('SELECT * FROM point_records WHERE user_id=? ORDER BY created_at DESC LIMIT 50', (user_id,))
        return {'balance': balance, 'records': [dict(r) for r in records]}

async def add_points(user_id: str, delta: int, reason: str, order_id: str='') -> int:
    async with dba.transaction() as c:
        '发放/扣减积分并记流水，返回最新余额。'
        row = _fetchone(await c.execute('SELECT balance FROM user_points WHERE user_id=?', (user_id,)))
        balance = int(row['balance']) if row else 0
        new_balance = max(0, balance + delta)
        await c.execute('INSERT INTO user_points (user_id, balance, total_earned)\n           VALUES (?,?,?)\n           ON CONFLICT(user_id) DO UPDATE SET\n             balance=excluded.balance,\n             total_earned=user_points.total_earned + CASE WHEN ? > 0 THEN ? ELSE 0 END', (user_id, new_balance, max(0, delta), delta, delta))
        await c.execute('INSERT INTO point_records (id, user_id, delta, reason, order_id, created_at)\n           VALUES (?,?,?,?,?,?)', ('P_' + uuid.uuid4().hex[:10], user_id, delta, reason, order_id or None, _now()))
        return new_balance

async def list_addresses(user_id: str) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '列出用户收货地址（默认地址排最前）。'
        rows = await c.execute('SELECT * FROM addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC', (user_id,))
        return [dict(r) for r in rows]

async def add_address(user_id: str, name: str, phone: str, address: str, is_default: bool=False) -> dict[str, Any]:
    async with dba.transaction() as c:
        '新增地址：首个地址自动设为默认；is_default=True 时清除其他默认。'
        addr_id = 'A_' + uuid.uuid4().hex[:10]
        now = _now()
        first = not _fetchone(await c.execute('SELECT 1 FROM addresses WHERE user_id=?', (user_id,)))
        if is_default or first:
            await c.execute('UPDATE addresses SET is_default=0 WHERE user_id=?', (user_id,))
        await c.execute('INSERT INTO addresses (id, user_id, name, phone, address, is_default, created_at, updated_at)\n           VALUES (?,?,?,?,?,?,?,?)', (addr_id, user_id, name, phone, address, 1 if is_default or first else 0, now, now))
        return dict(_fetchone(await c.execute('SELECT * FROM addresses WHERE id=?', (addr_id,))))

async def update_address(addr_id: str, user_id: str, name: str | None=None, phone: str | None=None, address: str | None=None, is_default: bool | None=None) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '更新地址（仅本人）；is_default=True 时清除该用户其他默认。'
        row = _fetchone(await c.execute('SELECT * FROM addresses WHERE id=? AND user_id=?', (addr_id, user_id)))
        if not row:
            return None
        sets: list[str] = []
        vals: list[Any] = []
        for col, val in (('name', name), ('phone', phone), ('address', address)):
            if val is not None:
                sets.append(f'{col}=?')
                vals.append(val)
        if is_default is True:
            await c.execute('UPDATE addresses SET is_default=0 WHERE user_id=?', (row['user_id'],))
            sets.append('is_default=1')
        elif is_default is False:
            sets.append('is_default=0')
        sets.append('updated_at=?')
        vals.append(_now())
        if sets:
            await c.execute(f"UPDATE addresses SET {', '.join(sets)} WHERE id=? AND user_id=?", vals + [addr_id, user_id])
        return dict(_fetchone(await c.execute('SELECT * FROM addresses WHERE id=?', (addr_id,))))

async def delete_address(addr_id: str, user_id: str) -> bool:
    async with dba.transaction() as c:
        '删除地址（仅本人）；被删的是默认地址时，自动把最新一条设为默认。'
        row = _fetchone(await c.execute('SELECT * FROM addresses WHERE id=? AND user_id=?', (addr_id, user_id)))
        if not row:
            return False
        await c.execute('DELETE FROM addresses WHERE id=?', (addr_id,))
        if row['is_default']:
            nxt = _fetchone(await c.execute('SELECT id FROM addresses WHERE user_id=? ORDER BY created_at DESC LIMIT 1', (row['user_id'],)))
            if nxt:
                await c.execute('UPDATE addresses SET is_default=1 WHERE id=?', (nxt['id'],))
        return True

async def get_default_address(user_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '读取默认地址（无默认则取最新一条，用于下单预填）。'
        row = _fetchone(await c.execute('SELECT * FROM addresses WHERE user_id=?\n           ORDER BY is_default DESC, created_at DESC LIMIT 1', (user_id,)))
        return dict(row) if row else None

async def add_favorite(user_id: str, plan_id: str) -> bool:
    async with dba.transaction() as c:
        '收藏方案（幂等：已收藏不报错），返回是否新增。'
        cur = await c.execute('INSERT INTO favorites (user_id, plan_id, created_at) VALUES (?,?,?)\n           ON CONFLICT (user_id, plan_id) DO NOTHING RETURNING user_id', (user_id, plan_id, _now()))
        return len(cur) > 0

async def remove_favorite(user_id: str, plan_id: str) -> bool:
    async with dba.transaction() as c:
        '取消收藏，返回是否删到了。'
        cur = await c.execute('DELETE FROM favorites WHERE user_id=? AND plan_id=? RETURNING user_id', (user_id, plan_id))
        return len(cur) > 0

async def list_favorites(user_id: str) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '列出收藏（新→旧，附方案详情供前端直接渲染）。'
        rows = await c.execute('SELECT f.plan_id, f.created_at, p.name, p.price, p.effect_image_url,\n                  p.merchant_name, p.desc\n           FROM favorites f LEFT JOIN plans p ON p.id = f.plan_id\n           WHERE f.user_id=? ORDER BY f.created_at DESC', (user_id,))
        return [dict(r) for r in rows]

async def is_favorite(user_id: str, plan_id: str) -> bool:
    async with dba.transaction() as c:
        return bool(_fetchone(await c.execute('SELECT 1 FROM favorites WHERE user_id=? AND plan_id=?', (user_id, plan_id))))

async def count_favorites(user_id: str) -> int:
    async with dba.transaction() as c:
        row = _fetchone(await c.execute('SELECT COUNT(*) FROM favorites WHERE user_id=?', (user_id,)))
        return int(row[0])

async def _shop_scope_sql(conn, shop_ids: list[str] | None, alias: str='') -> tuple[str, list[Any]]:
    """按店铺 scope 生成订单过滤条件。

    orders.shop_id 存的是下单时的商家名快照（与 shops.id 不一致），故同时按
    shop_id 与订单明细里的店名匹配；shop_ids=None 表示不限（admin），
    shop_ids=[] 表示未绑定店铺（无任何可见订单）。
    alias 用于联表查询（如 reviews JOIN orders o → alias='o.'）。
    """
    if shop_ids is None:
        return ('', [])
    if not shop_ids:
        return (' AND 0', [])
    names = [r['name'] for r in await conn.execute(f"SELECT name FROM shops WHERE id IN ({','.join('?' * len(shop_ids))})", shop_ids)]
    keys = [s for s in shop_ids if s] + [n for n in names if n]
    if not keys:
        return (f' AND {alias}0', [])
    ph = ','.join('?' * len(keys))
    return (f' AND ({alias}shop_id IN ({ph}) OR {alias}order_id IN (SELECT order_id FROM order_items WHERE shop IN ({ph})))', keys + keys)

async def merchant_stats(shop_ids: list[str] | None=None, shop_id: str='') -> dict[str, Any]:
    async with dba.transaction() as c:
        '店铺维度经营统计：订单数 / GMV / 待发货 / 已完成 / 评价数。\n\n    Args:\n        shop_ids: 商家绑定店铺 id 列表（None=全部店铺，admin）；\n        shop_id: 店铺 id 或店铺名（orders.shop_id 存的是商家名快照），空则按 shop_ids 汇总。\n    '
        where, args = await _shop_scope_sql(c, shop_ids)
        if shop_id:
            sname = _fetchone(await c.execute('SELECT name FROM shops WHERE id=?', (shop_id,)))
            name = sname['name'] if sname else shop_id
            if args:
                where += ' AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))'
                args += [shop_id, name, shop_id, name]
            else:
                where += ' AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))'
                args = [shop_id, name, shop_id, name]
        and_sql = " AND status='paid'"
        pending = _scalar(await c.execute(f'SELECT COUNT(*) FROM orders WHERE 1=1{where}{and_sql}', args))
        and_sql = " AND status='done'"
        done = _scalar(await c.execute(f'SELECT COUNT(*) FROM orders WHERE 1=1{where}{and_sql}', args))
        and_sql = " AND status='canceled'"
        canceled = _scalar(await c.execute(f'SELECT COUNT(*) FROM orders WHERE 1=1{where}{and_sql}', args))
        total = _fetchone(await c.execute(f'SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders WHERE 1=1{where}', args))
        ph = ','.join('?' * (len(args) // 2)) if args else ''
        rev_where, rev_args = ('', [])
        if shop_ids == []:
            rev_where = ' AND 1=0'
        elif args:
            rev_where = f' AND (o.shop_id IN ({ph}) OR o.order_id IN (SELECT order_id FROM order_items WHERE shop IN ({ph})))'
            rev_args = list(args)
        rev = _fetchone(await c.execute(f'SELECT COUNT(*), COALESCE(AVG(r.rating),0) FROM reviews r\n           JOIN orders o ON o.order_id = r.order_id WHERE 1=1{rev_where}', rev_args))
        today = _fetchone(await c.execute(f"SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders WHERE 1=1{where} AND created_at >= date('now', 'start of day')", args))
        pending_payment = _scalar(await c.execute(f"SELECT COUNT(*) FROM orders WHERE 1=1{where} AND status IN ('created','pending_payment')", args))
        if shop_ids:
            shops = await c.execute(f"SELECT * FROM shops WHERE id IN ({','.join('?' * len(shop_ids))}) ORDER BY created_at", shop_ids)
        elif shop_ids is not None:
            shops = []
        else:
            shops = await c.execute('SELECT * FROM shops ORDER BY created_at')
        return {'order_count': int(total[0]), 'gmv': float(total[1] or 0), 'pending_ship': int(pending), 'done_count': int(done), 'canceled_count': int(canceled), 'review_count': int(rev[0]), 'avg_rating': float(rev[1] or 0), 'today_order_count': int(today[0]), 'today_gmv': float(today[1] or 0), 'pending_payment': int(pending_payment), 'shops': [dict(s) for s in shops]}

async def merchant_orders(shop_ids: list[str] | None=None, shop_id: str='', status: str='', limit: int=50, keyword: str='', date_from: str='', date_to: str='') -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '商家视角订单列表（按绑定店铺隔离，可按店铺/状态/关键词/日期范围过滤）。\n\n    keyword 匹配：订单号 / 收货人姓名 / 收货人手机 / 商品名（order_items）；\n    date_from/date_to：YYYY-MM-DD，按 created_at 当日 00:00:00 ~ 23:59:59 过滤。\n    '
        where, args = await _shop_scope_sql(c, shop_ids)
        if shop_id:
            sname = _fetchone(await c.execute('SELECT name FROM shops WHERE id=?', (shop_id,)))
            name = sname['name'] if sname else shop_id
            where += ' AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))'
            args += [shop_id, name, shop_id, name]
        if status:
            where += ' AND status=?'
            args.append(status)
        kw = (keyword or '').strip()
        if kw:
            like = f'%{kw}%'
            where += ' AND (order_id LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ? OR items LIKE ? OR order_id IN (SELECT order_id FROM order_items WHERE name LIKE ?))'
            args += [like, like, like, like, like]
        if date_from:
            where += ' AND created_at >= ?'
            args.append(date_from.strip()[:10])
        if date_to:
            where += ' AND created_at <= ?'
            args.append(date_to.strip()[:10] + ' 23:59:59')
        sql = f'SELECT order_id FROM orders WHERE 1=1{where} ORDER BY created_at DESC LIMIT ?'
        args.append(limit)
        rows = await c.execute(sql, args)
        return [await get_order(r['order_id']) for r in rows]

async def merchant_ship(order_id: str) -> dict[str, Any] | None:
    """商家代发货（不受订单归属限制）：paid -> shipped。"""
    return await ship_order(order_id)

async def merchant_reviews(shop_ids: list[str] | None=None, shop_id: str='') -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '店铺维度评价列表（按绑定店铺隔离；空 scope 返回全部）。'
        where, args = await _shop_scope_sql(c, shop_ids, alias='o.')
        if shop_id:
            sname = _fetchone(await c.execute('SELECT name FROM shops WHERE id=?', (shop_id,)))
            name = sname['name'] if sname else shop_id
            where += ' AND (o.shop_id IN (?,?) OR o.order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))'
            args += [shop_id, name, shop_id, name]
        rows = await c.execute(f'SELECT r.* FROM reviews r\n            JOIN orders o ON o.order_id = r.order_id\n            WHERE 1=1{where} ORDER BY r.created_at DESC LIMIT 100', args)
        return [dict(r) for r in rows]

async def merchant_review_get(review_id: str, shop_ids: list[str] | None=None) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '按 ID 取单条评价（带商家范围校验；越界/不存在返回 None）。'
        where, args = await _shop_scope_sql(c, shop_ids, alias='o.')
        row = _fetchone(await c.execute(f'SELECT r.* FROM reviews r\n            JOIN orders o ON o.order_id = r.order_id\n            WHERE r.id=? AND 1=1{where}', [review_id, *args]))
        return dict(row) if row else None

async def create_review(user_id: str, order_id: str, rating: int, content: str='') -> dict[str, Any]:
    async with dba.transaction() as c:
        '订单完成后写评价：仅订单主人 + 订单已 done；同一订单只能评一次（重复则更新）。\n\n    Returns:\n        评价 dict。\n\n    Raises:\n        ValueError: 订单不存在 / 非本人 / 未完成 / 评分越界。\n    '
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            raise ValueError('订单不存在')
        if row['user_id'] != user_id:
            raise ValueError('无权评价该订单')
        if row['status'] != 'done':
            raise ValueError('订单完成后才能评价')
        if rating < 1 or rating > 5:
            raise ValueError('评分需在 1-5 星之间')
        now = _now()
        items = json.loads(row['items']) if row['items'] else []
        plan_id = items[0].get('plan_id') if items else None
        exist = _fetchone(await c.execute('SELECT id FROM reviews WHERE user_id=? AND order_id=?', (user_id, order_id)))
        if exist:
            await c.execute('UPDATE reviews SET rating=?, content=?, created_at=? WHERE id=?', (rating, content, now, exist['id']))
            rev = dict(_fetchone(await c.execute('SELECT * FROM reviews WHERE id=?', (exist['id'],))))
        else:
            rev_id = 'R_' + uuid.uuid4().hex[:10]
            await c.execute('INSERT INTO reviews (id, user_id, plan_id, order_id, rating, content, created_at)\n               VALUES (?,?,?,?,?,?,?)', (rev_id, user_id, plan_id, order_id, rating, content, now))
            rev = dict(_fetchone(await c.execute('SELECT * FROM reviews WHERE id=?', (rev_id,))))
        rev['plan_id'] = plan_id
        return rev

async def list_reviews(plan_id: str='', limit: int=50) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        "列出某方案的可见评价（新→旧，含用户昵称）；plan_id 为空返回全部。\n\n    只返回 status='visible'（管理后台隐藏/删除的评价不向 C 端展示）。\n    "
        if plan_id:
            rows = await c.execute("SELECT r.*, u.nickname FROM reviews r\n               LEFT JOIN users u ON u.id = r.user_id\n               WHERE r.plan_id=? AND r.status='visible' ORDER BY r.created_at DESC LIMIT ?", (plan_id, limit))
        else:
            rows = await c.execute("SELECT r.*, u.nickname FROM reviews r\n               LEFT JOIN users u ON u.id = r.user_id\n               WHERE r.status='visible' ORDER BY r.created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

async def add_to_cart(user_id: str, plan_id: str, name: str, price: float, shop: str | None=None) -> dict[str, Any]:
    async with dba.transaction() as c:
        '加入购物车：同用户同方案已存在则数量 +1，否则新建。'
        row = _fetchone(await c.execute('SELECT * FROM cart_items WHERE user_id=? AND plan_id=?', (user_id, plan_id)))
        if row:
            await c.execute('UPDATE cart_items SET qty=qty+1, updated_at=? WHERE item_id=?', (_now(), row['item_id']))
            return _row_to_dict(_fetchone(await c.execute('SELECT * FROM cart_items WHERE item_id=?', (row['item_id'],))))
        item_id = 'C_' + uuid.uuid4().hex[:10]
        now = _now()
        await c.execute('INSERT INTO cart_items\n           (item_id, user_id, plan_id, name, price, shop, qty, selected, created_at, updated_at)\n           VALUES (?,?,?,?,?,?,1,1,?,?)', (item_id, user_id, plan_id, name, price, shop, now, now))
        return _row_to_dict(_fetchone(await c.execute('SELECT * FROM cart_items WHERE item_id=?', (item_id,))))

async def list_cart(user_id: str) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '列出某用户购物车项（按加入时间倒序）。'
        rows = await c.execute('SELECT * FROM cart_items WHERE user_id=? ORDER BY created_at DESC', (user_id,))
        return [_row_to_dict(r) for r in rows]

async def update_cart_item(item_id: str, qty: int | None=None, selected: bool | None=None, user_id: str | None=None) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '更新购物车项数量或勾选状态；任一为 None 则不改该字段。\n\n    必须传 user_id 做归属校验（WHERE item_id=? AND user_id=?），防止越权改他人购物车项（IDOR）。\n    user_id 缺失时直接拒绝，绝不按 item_id 裸查。\n    '
        if not user_id:
            return None
        row = _fetchone(await c.execute('SELECT * FROM cart_items WHERE item_id=? AND user_id=?', (item_id, user_id)))
        if not row:
            return None
        if qty is not None:
            qty = max(1, int(qty))
            await c.execute('UPDATE cart_items SET qty=?, updated_at=? WHERE item_id=? AND user_id=?', (qty, _now(), item_id, user_id))
        if selected is not None:
            await c.execute('UPDATE cart_items SET selected=?, updated_at=? WHERE item_id=? AND user_id=?', (1 if selected else 0, _now(), item_id, user_id))
        return _row_to_dict(_fetchone(await c.execute('SELECT * FROM cart_items WHERE item_id=? AND user_id=?', (item_id, user_id))))

async def merge_cart(from_user_id: str, to_user_id: str) -> int:
    async with dba.transaction() as c:
        '把 from 用户的购物车并入 to 用户：同方案数量相加，不同方案转移归属。\n\n    用于「游客匿名 uid 购物车 → 登录账号」合并；返回并入的条数。\n    '
        rows = await c.execute('SELECT * FROM cart_items WHERE user_id=? ORDER BY created_at ASC', (from_user_id,))
        merged = 0
        for r in rows:
            existing = _fetchone(await c.execute('SELECT * FROM cart_items WHERE user_id=? AND plan_id=?', (to_user_id, r['plan_id'])))
            if existing:
                await c.execute('UPDATE cart_items SET qty=qty+?, updated_at=? WHERE item_id=?', (r['qty'], _now(), existing['item_id']))
            else:
                await c.execute('UPDATE cart_items SET user_id=?, updated_at=? WHERE item_id=?', (to_user_id, _now(), r['item_id']))
            merged += 1
        return merged

async def remove_cart_item(item_id: str, user_id: str | None=None) -> bool:
    async with dba.transaction() as c:
        '删除购物车项，返回是否真的删到了。\n\n    必须传 user_id 做归属校验（WHERE item_id=? AND user_id=?），防止越权删他人购物车项（IDOR）。\n    user_id 缺失时直接返回 False，绝不按 item_id 裸删。\n    '
        if not user_id:
            return False
        cur = await c.execute('DELETE FROM cart_items WHERE item_id=? AND user_id=? RETURNING item_id', (item_id, user_id))
        return len(cur) > 0

async def _expire_unpaid_order(conn, row) -> bool:
    """懒过期：created/pending_payment 订单超过支付时限 → 自动取消并返还优惠券。

    Returns:
        True 表示本次发生了过期取消。
    """
    status = row['status']
    if status not in ('created', 'pending_payment'):
        return False
    expires_at = row['expires_at']
    if not expires_at:
        return False
    try:
        expired = _now_ts() > _ts(expires_at)
    except ValueError:
        return False
    if not expired:
        return False
    await conn.execute("UPDATE orders SET status='canceled' WHERE order_id=? AND status=?", (row['order_id'], status))
    await _append_logistics(row['order_id'], '超过支付时限，订单已自动取消')
    cid = row['coupon_id']
    if cid:
        await conn.execute("UPDATE coupons SET status='unused', order_id=NULL, used_at=NULL\n               WHERE id=? AND status='used'", (cid,))
    return True

def _order_remaining_seconds(row) -> int:
    """订单剩余支付秒数（已支付/已过期返回 0）。"""
    if row['status'] in ('created', 'pending_payment') and row['expires_at']:
        try:
            return max(0, int(_ts(row['expires_at']) - _now_ts()))
        except ValueError:
            return 0
    return 0

async def create_order(user_id: str, items: list[dict[str, Any]], recipient: dict[str, Any] | None=None, delivery: str | None=None, note: str | None=None, address_id: str | None=None, delivery_location: dict[str, Any] | None=None) -> dict[str, Any]:
    async with dba.transaction() as c:
        '创建订单：服务端按目录取价计算总额、自动抵扣最优优惠券、落库（含收货信息），\n    并从购物车移除带 item_id 的项。\n\n    安全：**价格一律以目录（repo.get_plan）为准，绝不信客户端传价**（review P0：\n    POST /orders 曾直接按客户端 price×qty 计总额，可被篡改为任意低价）。\n    方案不存在 → ValueError（接口层转 400）。\n\n    Args:\n        address_id: 收货地址 id（用户已存地址时传此即可）；未传或找不到时回退 recipient 手填。\n        delivery_location: 配送位置（地图选点）{lat, lng, address}，与收货地址分开存储。\n    '
        from backend.storage.repository import repo
        priced: list[dict[str, Any]] = []
        for it in items:
            pid = it.get('plan_id')
            plan = await repo.get_plan(pid) if pid else None
            if not plan:
                raise ValueError(f'方案不存在或已下架: {pid}')
            priced.append({**it, 'price': float(plan['price']), 'name': plan.get('name') or it.get('name', '')})
        total = sum(float(i['price']) * max(1, int(i.get('qty', 1))) for i in priced)
        order_id = 'O_' + uuid.uuid4().hex[:10]
        first = priced[0] if priced else {}
        r = recipient or {}
        rname = r.get('name') or r.get('recipient_name')
        rphone = r.get('phone') or r.get('recipient_phone')
        raddr = r.get('address') or r.get('recipient_address')
        dl = delivery_location or {}
        dlat = dl.get('lat') if dl.get('lat') is not None else None
        dlng = dl.get('lng') if dl.get('lng') is not None else None
        daddr = dl.get('address') or ''
        saved_addr = None
        if address_id:
            saved_addr = _fetchone(await c.execute('SELECT * FROM addresses WHERE id=? AND user_id=?', (address_id, user_id)))
        if saved_addr:
            rname, rphone, raddr = (saved_addr['name'], saved_addr['phone'], saved_addr['address'])
        await c.execute("INSERT INTO orders\n           (order_id, user_id, plan_id, plan_type, shop_id, items, total_price,\n            paid, status, expires_at, address_id, recipient_name, recipient_phone, recipient_address,\n            delivery_time, note, delivery_lat, delivery_lng, delivery_address, created_at)\n           VALUES (?,?,?,?,?,?,?,0,'created',?,?,?,?,?,?,?,?,?,?,?)", (order_id, user_id, first.get('plan_id'), 'plan', first.get('shop'), json.dumps(priced, ensure_ascii=False), total, _expires_at_str(), saved_addr['id'] if saved_addr else None, rname, rphone, raddr, delivery, note, dlat, dlng, daddr, _now()))
        if total > 0:
            await apply_best_coupon(order_id, user_id, total)
        for it in priced:
            iid = it.get('item_id')
            if iid:
                await c.execute('DELETE FROM cart_items WHERE item_id=?', (iid,))
        await _append_logistics(order_id, '订单已创建，等待支付')
        from backend.storage import notify
        await notify.try_create(user_id, notify.T_ORDER, '订单已创建', f"{rname or '收花人'}的花束订单已提交，等待支付", ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def update_order(order_id: str, recipient: dict[str, Any] | None=None, delivery: str | None=None, note: str | None=None, delivery_location: dict[str, Any] | None=None, card_message: str | None=None, card_image_url: str | None=None, card_token: str | None=None) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '更新订单的收货人 / 配送时间 / 备注 / 配送位置（仅允许设置传入的字段）。\n\n    Args:\n        order_id: 订单号。\n        recipient: ``{name, phone, address}`` 任意子集；缺省字段不覆盖。\n        delivery: 配送时间描述（如 ``"今天 18:00–20:00"``）。\n        note: 订单备注。\n        delivery_location: 配送位置 {lat, lng, address}（地图选点）。\n\n    Returns:\n        更新后的订单 dict；订单不存在返回 None。\n    '
        if not _fetchone(await c.execute('SELECT 1 FROM orders WHERE order_id=?', (order_id,))):
            return None
        sets: list[str] = []
        vals: list[Any] = []
        if recipient is not None and isinstance(recipient, dict):
            if 'name' in recipient:
                sets.append('recipient_name=?')
                vals.append(recipient.get('name'))
            if 'phone' in recipient:
                sets.append('recipient_phone=?')
                vals.append(recipient.get('phone'))
            if 'address' in recipient:
                sets.append('recipient_address=?')
                vals.append(recipient.get('address'))
        if delivery is not None:
            sets.append('delivery_time=?')
            vals.append(delivery)
        if note is not None:
            sets.append('note=?')
            vals.append(note)
        if card_message is not None:
            sets.append('card_message=?')
            vals.append(card_message)
        if card_image_url is not None:
            sets.append('card_image_url=?')
            vals.append(card_image_url)
        if card_token is not None:
            sets.append('card_token=?')
            vals.append(card_token)
        if delivery_location is not None and isinstance(delivery_location, dict):
            if delivery_location.get('lat') is not None:
                sets.append('delivery_lat=?')
                vals.append(delivery_location.get('lat'))
            if delivery_location.get('lng') is not None:
                sets.append('delivery_lng=?')
                vals.append(delivery_location.get('lng'))
            if 'address' in delivery_location:
                sets.append('delivery_address=?')
                vals.append(delivery_location.get('address'))
        if sets:
            await c.execute(f"UPDATE orders SET {', '.join(sets)} WHERE order_id=?", vals + [order_id])
        return await get_order(order_id)

def _expires_at_str() -> str:
    """订单支付截止时间字符串（now + order_pay_timeout_minutes）。"""
    from backend.config import settings
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(_now_ts() + settings.order_pay_timeout_minutes * 60))

async def _enrich_order_item_images(conn: Any, items: list[dict]) -> None:
    """按商品 plan_id 回填订单明细缺失的商品图（effect_image_url）。

    兼容历史订单：下单时未快照图片的明细，读取时从 plans 表补齐，
    保证订单详情/物流页能展示真实商品图；已带 image 的明细不覆盖。
    """
    need = [it for it in items if not (it.get('image') or it.get('effect_image_url'))]
    if not need:
        return
    ids = list({str(it.get('product_id') or it.get('plan_id') or '') for it in need if it.get('product_id') or it.get('plan_id')})
    if not ids:
        return
    ph = ','.join('?' * len(ids))
    rows = await conn.execute(f'SELECT id, effect_image_url FROM plans WHERE id IN ({ph})', ids)
    img_by_id = {r['id']: r['effect_image_url'] for r in rows if r['effect_image_url']}
    for it in need:
        pid = str(it.get('product_id') or it.get('plan_id') or '')
        if pid in img_by_id:
            it['image'] = img_by_id[pid]

async def get_order(order_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '读取订单详情（items 反序列化、paid 转 bool、补充 recipient 嵌套对象）。\n\n    读取时执行懒过期：超时未支付的订单自动转为 canceled 并返还优惠券。\n    '
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        await _expire_unpaid_order(c, row)
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        d = dict(row)
        d['items'] = json.loads(d['items']) if d.get('items') else []
        await _enrich_order_item_images(c, d['items'])
        d['paid'] = bool(d.get('paid'))
        d['recipient'] = {'name': d.get('recipient_name'), 'phone': d.get('recipient_phone'), 'address': d.get('recipient_address')}
        d['delivery_location'] = {'lat': d.get('delivery_lat'), 'lng': d.get('delivery_lng'), 'address': d.get('delivery_address')}
        d['logistics'] = await list_logistics(order_id)
        d['remaining_seconds'] = _order_remaining_seconds(row)
        # 贺卡分享完整链接：配置了 public_base_url 时用公网地址拼；
        # 未配置时返回 None，前端用 window.location.origin 兜底（本地联调）。
        if d.get('card_token'):
            from backend.config import settings
            base = (settings.public_base_url or '').rstrip('/')
            d['share_url'] = f"{base}/card-share/{d['card_token']}" if base else None
        else:
            d['share_url'] = None
        # 商家拒单退款信息（拒单时订单转 canceled + payments refunded）
        if d.get('merchant_status') == 'rejected':
            pay = _fetchone(await c.execute("SELECT amount, paid_at FROM payments WHERE order_id=? AND status='refunded'", (order_id,)))
            d['refund'] = {'amount': float(pay['amount']) if pay else 0.0, 'at': pay['paid_at'] if pay else None}
        else:
            d['refund'] = None
        return d

async def list_orders(user_id: str, limit: int=50) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '列出某用户全部订单（新→旧）。'
        rows = await c.execute('SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
        return [await get_order(r['order_id']) for r in rows]

async def list_logistics(order_id: str) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '读取订单物流时间线（事件新→旧，与主流物流 App 展示一致）。'
        rows = await c.execute('SELECT seq, text, created_at FROM order_logistics WHERE order_id=? ORDER BY seq DESC', (order_id,))
        return [dict(r) for r in rows]

async def _append_logistics(order_id: str, text: str) -> None:
    async with dba.transaction() as c:
        nxt = _scalar(await c.execute('SELECT COALESCE(MAX(seq), -1) + 1 FROM order_logistics WHERE order_id=?', (order_id,)))
        await c.execute('INSERT INTO order_logistics(order_id, seq, text, created_at) VALUES (?,?,?,?)', (order_id, nxt, text, _now()))

async def add_logistics_event(order_id: str, text: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '商家手动追加物流节点（仅配送中 shipped 状态可追加）。订单不存在返回 None。'
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        await _expire_unpaid_order(c, row)
        if row['status'] != 'shipped':
            raise ValueError(f"当前状态 {row['status']} 不可追加物流节点")
        text = (text or '').strip()
        if not text:
            raise ValueError('物流节点内容不能为空')
        await _append_logistics(order_id, text)
        from backend.storage import notify
        await notify.try_create(row['user_id'], notify.T_LOGISTICS, '物流更新', text[:120], ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def ship_order(order_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '模拟发货：paid -> shipped，并生成物流时间线。订单不存在返回 None。'
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        await _expire_unpaid_order(c, row)
        if row['status'] != 'paid':
            raise ValueError(f"当前状态 {row['status']} 不可发货")
        await c.execute("UPDATE orders SET status='shipped' WHERE order_id=?", (order_id,))
        await _append_logistics(order_id, '商家已发货，包裹正在打包出库')
        await _append_logistics(order_id, '包裹已揽收，正在发往深圳转运中心')
        await _append_logistics(order_id, '包裹到达深圳转运中心，正在分拣')
        from backend.storage import notify
        await notify.try_create(row['user_id'], notify.T_ORDER, '订单已发货', f'订单 {order_id} 已由商家发货，正在配送途中', ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def complete_order(order_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '模拟签收：shipped -> done，追加签收时间线。订单不存在返回 None。'
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        await _expire_unpaid_order(c, row)
        if row['status'] != 'shipped':
            raise ValueError(f"当前状态 {row['status']} 不可签收")
        await c.execute("UPDATE orders SET status='done' WHERE order_id=?", (order_id,))
        await _append_logistics(order_id, '包裹已到达配送网点，快递员正在派送')
        await _append_logistics(order_id, '已签收，感谢惠顾 FloraDIY')
        from backend.storage import notify
        await notify.try_create(row['user_id'], notify.T_ORDER, '订单已签收', f'订单 {order_id} 已签收，期待您对本次花束的反馈', ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def cancel_order(order_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '取消订单：仅 created/pending_payment 可取消。订单不存在返回 None。'
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        await _expire_unpaid_order(c, row)
        if row['status'] not in ('created', 'pending_payment'):
            raise ValueError(f"当前状态 {row['status']} 不可取消")
        await c.execute("UPDATE orders SET status='canceled' WHERE order_id=?", (order_id,))
        await _append_logistics(order_id, '订单已取消')
        cid = row['coupon_id']
        if cid:
            await c.execute("UPDATE coupons SET status='unused', order_id=NULL, used_at=NULL\n               WHERE id=? AND status='used'", (cid,))
        from backend.storage import notify
        await notify.try_create(row['user_id'], notify.T_ORDER, '订单已取消', f'订单 {order_id} 已取消，如已使用优惠券将自动返还', ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def pay_order(order_id: str, method: str='', extra: dict[str, Any] | None=None) -> dict[str, Any] | None:
    method = (method or payment_module.settings.payment_provider or 'sandbox')
    async with dba.transaction() as c:
        '发起支付：按配置的支付渠道（默认 sandbox）调统一下单，记录 payments 行并归一化返回。\n\n    - 沙箱渠道：下单即模拟支付成功，订单直接标记为已支付。\n    - 真实渠道（微信/支付宝）：下单成功后订单保持 pending，仅当 ``mark_order_paid``\n      被支付回调（验签通过）调用后才标记已支付——状态变更必须来自可信回调。\n\n    Args:\n        order_id: 本系统订单号。\n        method: 支付方式（wechat/alipay/union/huabei），透传给渠道。\n        extra: 渠道额外参数，如微信需 ``{"openid": ...}``、``{"description": ...}``。\n\n    Returns:\n        归一化的支付意图 dict（含 pay_params / paid / page_path / payment_id）；\n        订单不存在返回 None。\n\n    Raises:\n        PaymentConfigError: 真实渠道凭据未配置（由 payment 层抛出，API 层转 4xx/5xx）。\n        PaymentGatewayError: 调第三方网关网络/返回异常。\n    '
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        await _expire_unpaid_order(c, row)
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        order = dict(row)
        if order['status'] not in ('created', 'pending_payment'):
            raise ValueError(f"当前状态 {order['status']} 不可支付")
        from backend.storage import config as config_store
        shipping = float(await config_store.get_config(config_store.K_SHIPPING, config_store.DEFAULTS[config_store.K_SHIPPING]) or 0)
        pay_order_ctx = dict(order)
        payable = max(0.0, float(order.get('total_price') or 0) + shipping - float(order.get('discount') or 0))
        pay_order_ctx['total_price'] = payable
        provider = payment_module.get_provider(method)
        try:
            intent = provider.create_payment(pay_order_ctx, method, extra)
        except payment_module.PaymentError:
            logger.exception('支付下单失败 order=%s method=%s', order_id, method)
            raise
        pay_id = 'P_' + uuid.uuid4().hex[:10]
        now = _now()
        pay_status = 'paid' if intent.paid else 'pending'
        paid_at = now if intent.paid else None
        await c.execute('INSERT INTO payments (id, order_id, method, amount, status, transaction_id, created_at, paid_at)\n           VALUES (?,?,?,?,?,?,?,?)', (pay_id, order_id, method, intent.amount, pay_status, intent.transaction_id, now, paid_at))
        if intent.paid:
            cur = await c.execute("UPDATE orders SET paid=1, status='paid', paid_at=? WHERE order_id=? AND paid=0 RETURNING order_id", (now, order_id))
            await _append_logistics(order_id, '支付成功，商家备货中')
            if len(cur) > 0:
                await add_points(order['user_id'], max(1, int(round(payable))), '订单消费返积分', order_id)
        else:
            await c.execute("UPDATE orders SET status='pending_payment' WHERE order_id=?", (order_id,))
        if intent.paid:
            if (order.get('card_message') or order.get('card_image_url')) and (not order.get('card_token')):
                token = uuid.uuid4().hex[:12]
                await c.execute('UPDATE orders SET card_token=? WHERE order_id=?', (token, order_id))
            from backend.storage import notify
            await notify.try_create(order['user_id'], notify.T_ORDER, '支付成功', f'订单 {order_id} 已支付 ¥{intent.amount}，商家备货中', ref_type='order', ref_id=order_id)
            await _notify_merchants(c, order)
        result = intent.to_dict()
        result['payment_id'] = pay_id
        return result

async def mark_order_paid(order_id: str, transaction_id: str='') -> bool:
    async with dba.transaction() as c:
        '支付回调确认后标记订单与 payments 行已支付（状态机唯一可信来源）。\n\n    由 ``api.pay_notify`` 在验签通过后调用；绝不直接被前端请求触发，避免伪造回调篡改。\n\n    Args:\n        order_id: 本系统订单号。\n        transaction_id: 第三方交易号（微信/支付宝回调解包得到）。\n\n    Returns:\n        订单是否存在并已处理。\n    '
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return False
        if row['paid']:
            return True
        now = _now()
        await c.execute("UPDATE orders SET paid=1, status='paid', paid_at=? WHERE order_id=? AND paid=0", (now, order_id))
        await _append_logistics(order_id, '支付成功，商家备货中')
        from backend.storage import config as config_store
        shipping = float(await config_store.get_config(config_store.K_SHIPPING, config_store.DEFAULTS[config_store.K_SHIPPING]) or 0)
        payable = max(0.0, float(row['total_price'] or 0) + shipping - float(row['discount'] or 0))
        await add_points(row['user_id'], max(1, int(round(payable))), '订单消费返积分', order_id)
        await c.execute("UPDATE payments SET status='paid', paid_at=?, transaction_id=? WHERE order_id=? AND status<>'paid'", (now, transaction_id, order_id))
        cnt = _scalar(await c.execute('SELECT COUNT(*) FROM payments WHERE order_id=?', (order_id,)))
        if cnt == 0:
            await c.execute('INSERT INTO payments (id, order_id, method, amount, status, transaction_id, created_at, paid_at)\n               VALUES (?,?,?,?,?,?,?,?)', ('P_' + uuid.uuid4().hex[:10], order_id, 'unknown', payable, 'paid', transaction_id, now, now))
        try:
            has_card = row['card_message'] or row['card_image_url']
        except (IndexError, KeyError):
            has_card = False
        if has_card and (not row['card_token']):
            token = uuid.uuid4().hex[:12]
            await c.execute('UPDATE orders SET card_token=? WHERE order_id=?', (token, order_id))
        from backend.storage import notify
        await notify.try_create(row['user_id'], notify.T_ORDER, '支付成功', f'订单 {order_id} 已支付 ¥{payable:.2f}，商家备货中', ref_type='order', ref_id=order_id)
        await _notify_merchants(c, dict(row))
        return True

async def get_payment_status(order_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '查询订单支付状态（客户端轮询兜底，用于回调不可达场景）。\n\n    Returns:\n        含 ``paid`` / ``status`` 的 dict；订单不存在返回 None。\n    '
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        return {'order_id': order_id, 'paid': bool(row['paid']), 'status': row['status']}

async def _notify_merchants(conn, order: dict[str, Any]) -> None:
    """支付后通知该订单店铺的商家「有新订单待确认」（容错：找不到商家则跳过）。

    orders.shop_id 存的是下单时的店铺 id/名快照；先按 shop_id 查 merchant_shops 绑定，
    查不到再按店铺名反查 shops.id 后绑定，最后按绑定找商家 user_id。
    """
    from backend.storage import notify
    shop_key = (order.get('shop_id') or '').strip()
    if not shop_key:
        return
    merchant_ids: list[str] = []
    try:
        rows = await conn.execute('SELECT user_id FROM merchant_shops WHERE shop_id=?', (shop_key,))
        merchant_ids = [r['user_id'] for r in rows]
        if not merchant_ids:
            shop = _fetchone(await conn.execute('SELECT id FROM shops WHERE name=?', (shop_key,)))
            if shop:
                rows = await conn.execute('SELECT user_id FROM merchant_shops WHERE shop_id=?', (shop['id'],))
                merchant_ids = [r['user_id'] for r in rows]
    except Exception:
        logger.exception('[commerce] 查找订单商家失败，跳过通知 order=%s', order.get('order_id'))
        return
    for mid in dict.fromkeys(merchant_ids):
        try:
            await notify.try_create(mid, notify.T_ORDER, '有新订单待确认',
                                    f'订单 {order["order_id"]} 已支付，请在商家后台确认接单', ref_type='order', ref_id=order['order_id'])
        except Exception:
            logger.warning('[commerce] 通知商家失败 merchant=%s', mid)

async def merchant_accept_order(order_id: str) -> dict[str, Any] | None:
    """商家接单：paid 且未处理的订单标记已接单（merchant_status='accepted'）。

    Returns:
        更新后的订单 dict；订单不存在返回 None。

    Raises:
        ValueError: 状态不满足接单条件（未支付 / 已处理 / 已取消等）。
    """
    async with dba.transaction() as c:
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        if row['status'] != 'paid':
            raise ValueError(f"当前状态 {row['status']} 不可接单（仅已支付订单可接单）")
        if row['merchant_status']:
            raise ValueError(f"订单已处理（{row['merchant_status']}），不可重复接单")
        await c.execute("UPDATE orders SET merchant_status='accepted', confirmed_at=? WHERE order_id=? AND merchant_status=''", (_now(), order_id))
        await _append_logistics(order_id, '商家已接单，正在备货')
        from backend.storage import notify
        await notify.try_create(row['user_id'], notify.T_ORDER, '商家已接单', f'订单 {order_id} 已被商家接单，正在备货', ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def merchant_reject_order(order_id: str, reason: str='') -> dict[str, Any] | None:
    """商家拒单：paid 且未处理的订单转取消，退款并返还优惠券，通知用户。

    Returns:
        更新后的订单 dict；订单不存在返回 None。

    Raises:
        ValueError: 状态不满足拒单条件。
        PaymentGatewayError: 真实渠道退款失败（状态不变）。
    """
    async with dba.transaction() as c:
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        if row['status'] != 'paid':
            raise ValueError(f"当前状态 {row['status']} 不可拒单（仅已支付订单可拒单）")
        if row['merchant_status']:
            raise ValueError(f"订单已处理（{row['merchant_status']}），不可重复拒单")
        # 取支付方式与实付金额，用于真实退款
        pm = _fetchone(await c.execute("SELECT method, amount FROM payments WHERE order_id=? AND status='paid' ORDER BY created_at DESC LIMIT 1", (order_id,)))
        pay_method = pm['method'] if pm and pm['method'] else 'sandbox'
        try:
            pay_amount = float(pm['amount']) if pm else float(row['total_price'] or 0)
        except (TypeError, ValueError):
            pay_amount = float(row['total_price'] or 0)

    # 真实渠道先发起退款，受理成功后才翻转本地状态
    from backend.storage import payment as payment_module
    order_ctx = {'order_id': order_id, 'total_price': pay_amount, 'method': pay_method}
    try:
        await asyncio.to_thread(payment_module.try_refund, order_ctx, pay_amount, reason or '商家拒单退款')
    except payment_module.PaymentGatewayError:
        raise

    async with dba.transaction() as c:
        row = _fetchone(await c.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        if row['status'] != 'paid':
            raise ValueError(f"当前状态 {row['status']} 不可拒单（仅已支付订单可拒单）")
        if row['merchant_status']:
            raise ValueError(f"订单已处理（{row['merchant_status']}），不可重复拒单")
        await c.execute("UPDATE orders SET merchant_status='rejected', status='canceled', confirmed_at=? WHERE order_id=? AND merchant_status=''", (_now(), order_id))
        await c.execute("UPDATE payments SET status='refunded' WHERE order_id=? AND status='paid'", (order_id,))
        cid = row['coupon_id']
        if cid:
            await c.execute("UPDATE coupons SET status='unused', order_id=NULL, used_at=NULL WHERE id=? AND status='used'", (cid,))
        await _append_logistics(order_id, '商家拒单，订单已取消并退款')
        from backend.storage import notify
        note = f'商家拒单（{reason or "无"}），款项已原路退回'
        await notify.try_create(row['user_id'], notify.T_ORDER, '商家拒单，已退款', f'订单 {order_id} 被商家拒单：{note}', ref_type='order', ref_id=order_id)
        return await get_order(order_id)

async def get_share_card(token: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '通过贺卡 token 查询贺卡信息（公开端点，无需登录）。'
        row = _fetchone(await c.execute('SELECT card_message, card_image_url, recipient_name, shop_id, created_at FROM orders WHERE card_token=?', (token,)))
        if not row:
            return None
        d = dict(row)
        if d.get('shop_id'):
            shop = _fetchone(await c.execute('SELECT name FROM shops WHERE id=?', (d['shop_id'],)))
            d['shop_name'] = shop['name'] if shop else ''
        else:
            d['shop_name'] = ''
        return d

def _fetchone(rows):
    return rows[0] if rows else None

def _scalar(rows):
    return next(iter(rows[0].values())) if rows else None
