"""storage/admin.py —— 平台管理员后台的聚合存储层（M0/M2/M3/M4/M5）。

集中管理后台的查询/写操作：用户管理、全局订单、售后审核、商家入驻审核。
所有写入使用事务；售后退款为 sandbox 模拟（翻 payments.status），
真实网关接入后替换实现，不改变调用方。
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, timedelta
from typing import Any

from backend.storage import db_async as dba

AFTERSALE_STATUS = {'pending', 'approved', 'rejected', 'refunded', 'closed'}
APPLY_STATUS = {'pending', 'approved', 'rejected'}

def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')

async def _new_id(prefix: str) -> str:
    return f'{prefix}{uuid.uuid4().hex[:10].upper()}'

async def list_users(keyword: str='', role: str='', status: str='', limit: int=50, offset: int=0) -> tuple[list[dict[str, Any]], int]:
    async with dba.transaction() as c:
        '分页用户列表（昵称/用户名/手机号关键词 + 角色 + 状态筛选）。'
        where, args = (' WHERE 1=1', [])
        kw = (keyword or '').strip()
        if kw:
            like = f'%{kw}%'
            where += ' AND (username LIKE ? OR nickname LIKE ? OR phone LIKE ?)'
            args += [like, like, like]
        if role:
            where += ' AND role=?'
            args.append(role)
        if status:
            where += ' AND status=?'
            args.append(status)
        total = _scalar(await c.execute(f'SELECT COUNT(*) FROM users{where}', args))
        rows = await c.execute(f'SELECT id, username, nickname, avatar, phone, role, status, created_at\n            FROM users{where} ORDER BY created_at DESC LIMIT ? OFFSET ?', args + [limit, offset])
        return ([dict(r) for r in rows], int(total))

async def get_user(user_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '用户详情（含注册/更新时间）。'
        row = _fetchone(await c.execute('SELECT * FROM users WHERE id=?', (user_id,)))
        return dict(row) if row else None

async def set_user_status(user_id: str, status: str) -> bool:
    """禁用/启用用户（active|banned）。"""
    if status not in ('active', 'banned'):
        raise ValueError(f'非法状态: {status}')
    async with dba.transaction() as c:
        cur = await c.execute('UPDATE users SET status=?, updated_at=? WHERE id=? RETURNING id', (status, _now(), user_id))
    return len(cur) > 0

async def set_user_role(user_id: str, role: str) -> bool:
    """提权/降权（user|merchant|admin）。"""
    from backend.security import set_user_role as _set_role
    if role not in ('user', 'merchant', 'admin'):
        raise ValueError(f'非法角色: {role}')
    return _set_role(user_id, role)

async def list_all_orders(status: str='', user_id: str='', shop_id: str='', keyword: str='', date_from: str='', date_to: str='', limit: int=50, offset: int=0) -> tuple[list[str], int]:
    async with dba.transaction() as c:
        '全局订单列表（返回 order_id 列表，由 commerce.get_order 补全详情）。'
        where, args = (' WHERE 1=1', [])
        if status:
            where += ' AND status=?'
            args.append(status)
        if user_id:
            where += ' AND user_id=?'
            args.append(user_id)
        if shop_id:
            sname = _fetchone(await c.execute('SELECT name FROM shops WHERE id=?', (shop_id,)))
            name = sname['name'] if sname else shop_id
            where += ' AND (shop_id IN (?,?) OR order_id IN (SELECT order_id FROM order_items WHERE shop IN (?,?)))'
            args += [shop_id, name, shop_id, name]
        kw = (keyword or '').strip()
        if kw:
            like = f'%{kw}%'
            where += ' AND (order_id LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ? OR items LIKE ?)'
            args += [like, like, like, like]
        if date_from:
            where += ' AND date(created_at) >= ?'
            args.append(date_from.strip()[:10])
        if date_to:
            where += ' AND date(created_at) <= ?'
            args.append(date_to.strip()[:10])
        total = _scalar(await c.execute(f'SELECT COUNT(*) FROM orders{where}', args))
        rows = await c.execute(f'SELECT order_id FROM orders{where} ORDER BY created_at DESC LIMIT ? OFFSET ?', args + [limit, offset])
        ids = [r['order_id'] for r in rows]
        return (ids, int(total))

async def set_order_status(order_id: str, status: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '管理员干预订单状态（绕过用户/商家流程直接落库）。\n\n    联动：标记 paid 时写 paid_at/paid=1；其余直接改状态。\n    '
        from backend.storage import commerce
        row = _fetchone(await c.execute('SELECT status FROM orders WHERE order_id=?', (order_id,)))
        if not row:
            return None
        now = _now()
        async with dba.transaction() as c:
            if status == 'paid':
                await c.execute('UPDATE orders SET status=?, paid=1, paid_at=COALESCE(paid_at,?) WHERE order_id=?', (status, now, order_id))
            else:
                await c.execute('UPDATE orders SET status=? WHERE order_id=?', (status, order_id))
        return await commerce.get_order(order_id)

async def create_aftersale(order_id: str, user_id: str, aftersale_type: str, reason: str='', description: str='', evidence_imgs: list[str] | None=None) -> dict[str, Any]:
    async with dba.transaction() as c:
        '用户发起售后单（订单须归属本人且已支付）。'
        from backend.storage import commerce
        order = await commerce.get_order(order_id)
        if not order:
            raise ValueError('订单不存在')
        if order['user_id'] != user_id:
            raise ValueError('只能对自己名下的订单发起售后')
        if not order.get('paid'):
            raise ValueError('仅已支付订单可发起售后')
        if aftersale_type not in ('refund', 'return', 'exchange'):
            raise ValueError('非法售后类型')
        existing = _fetchone(await c.execute("SELECT id FROM aftersales WHERE order_id=? AND status IN ('pending','approved')", (order_id,)))
        if existing:
            raise ValueError('该订单已有进行中的售后单')
        as_id = await _new_id('AS')
        now = _now()
        async with dba.transaction() as c:
            await c.execute("INSERT INTO aftersales\n               (id, order_id, user_id, shop_id, type, reason, description, evidence_imgs,\n                status, created_at, updated_at)\n               VALUES (?,?,?,?,?,?,?,?,'pending',?,?)", (as_id, order_id, user_id, order.get('shop_id'), aftersale_type, (reason or '')[:200], (description or '')[:1000], json.dumps(evidence_imgs or [], ensure_ascii=False), now, now))
        return await get_aftersale(as_id)

async def list_aftersales(status: str='', limit: int=50, offset: int=0) -> tuple[list[dict[str, Any]], int]:
    async with dba.transaction() as c:
        '售后单列表（按创建时间倒序，可筛状态）。'
        where, args = (' WHERE 1=1', [])
        if status:
            where += ' AND a.status=?'
            args.append(status)
        total = _scalar(await c.execute(f'SELECT COUNT(*) FROM aftersales a{where}', args))
        rows = await c.execute(f'SELECT a.*, o.total_price AS order_total, u.nickname, u.phone\n            FROM aftersales a\n            LEFT JOIN orders o ON o.order_id = a.order_id\n            LEFT JOIN users u ON u.id = a.user_id\n            {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?', args + [limit, offset])
        out = []
        for r in rows:
            d = dict(r)
            try:
                d['evidence_imgs'] = json.loads(d['evidence_imgs']) if d.get('evidence_imgs') else []
            except (json.JSONDecodeError, TypeError):
                d['evidence_imgs'] = []
            out.append(d)
        return (out, int(total))

async def list_user_aftersales(user_id: str, limit: int=50) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '我的售后单列表（用户侧）。'
        rows = await c.execute('SELECT a.*, o.total_price AS order_total FROM aftersales a\n           LEFT JOIN orders o ON o.order_id = a.order_id\n           WHERE a.user_id=? ORDER BY a.created_at DESC LIMIT ?', (user_id, limit))
        out = []
        for r in rows:
            d = dict(r)
            try:
                d['evidence_imgs'] = json.loads(d['evidence_imgs']) if d.get('evidence_imgs') else []
            except (json.JSONDecodeError, TypeError):
                d['evidence_imgs'] = []
            out.append(d)
        return out

async def list_merchant_aftersales(shop_ids: list[str], status: str='', limit: int=50, offset: int=0) -> tuple[list[dict[str, Any]], int]:
    async with dba.transaction() as c:
        '商家维度售后单列表（按绑定店铺隔离，三端架构阶段3b）。\n\n    匹配口径与订单一致：aftersales.shop_id 直接命中，或订单内商品归属店铺命中。\n    '
        if not shop_ids:
            return ([], 0)
        ph = ','.join('?' * len(shop_ids))
        where, args = (f' WHERE (a.shop_id IN ({ph}) OR a.order_id IN (SELECT order_id FROM order_items WHERE shop IN ({ph})))', list(shop_ids) * 2)
        if status:
            where += ' AND a.status=?'
            args.append(status)
        total = _scalar(await c.execute(f'SELECT COUNT(*) FROM aftersales a{where}', args))
        rows = await c.execute(f'SELECT a.*, o.total_price AS order_total, u.nickname, u.phone\n            FROM aftersales a\n            LEFT JOIN orders o ON o.order_id = a.order_id\n            LEFT JOIN users u ON u.id = a.user_id\n            {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?', args + [limit, offset])
        out = []
        for r in rows:
            d = dict(r)
            try:
                d['evidence_imgs'] = json.loads(d['evidence_imgs']) if d.get('evidence_imgs') else []
            except (json.JSONDecodeError, TypeError):
                d['evidence_imgs'] = []
            out.append(d)
        return (out, int(total))

async def get_aftersale(as_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '售后单详情。'
        row = _fetchone(await c.execute('SELECT a.*, o.total_price AS order_total, o.status AS order_status,\n                  u.nickname, u.phone\n           FROM aftersales a\n           LEFT JOIN orders o ON o.order_id = a.order_id\n           LEFT JOIN users u ON u.id = a.user_id\n           WHERE a.id=?', (as_id,)))
        if not row:
            return None
        d = dict(row)
        try:
            d['evidence_imgs'] = json.loads(d['evidence_imgs']) if d.get('evidence_imgs') else []
        except (json.JSONDecodeError, TypeError):
            d['evidence_imgs'] = []
        return d

async def _update_aftersale(as_id: str, status: str, handled_by: str, note: str='', refund_amount: float | None=None) -> dict[str, Any] | None:
    """售后单状态流转（内部共用）。"""
    async with dba.transaction() as c:
        cur = await c.execute('UPDATE aftersales\n               SET status=?, handled_by=?, handled_at=?, refund_amount=COALESCE(?, refund_amount),\n                   review_note=?, updated_at=?\n               WHERE id=? RETURNING id', (status, handled_by, _now(), refund_amount, (note or '')[:500], _now(), as_id))
        if len(cur) == 0:
            return None
        row = _fetchone(await c.execute('SELECT order_id FROM aftersales WHERE id=?', (as_id,)))
        if status == 'refunded' and row:
            await c.execute("UPDATE payments SET status='refunded' WHERE order_id=? AND status='paid'", (row['order_id'],))
    from backend.storage import notify
    labels = {'approved': '售后已通过', 'rejected': '售后申请被驳回', 'refunded': '退款已到账'}
    a = await get_aftersale(as_id)
    if a and status in labels:
        await notify.try_create(a['user_id'], notify.T_AFTERSALE, labels[status], f"订单 {a['order_id']} 的售后单已更新：{note or labels[status]}", ref_type='aftersale', ref_id=a['id'])
    return await get_aftersale(as_id)

async def approve_aftersale(as_id: str, handled_by: str) -> dict[str, Any] | None:
    return await _update_aftersale(as_id, 'approved', handled_by)

async def reject_aftersale(as_id: str, handled_by: str, note: str='') -> dict[str, Any] | None:
    return await _update_aftersale(as_id, 'rejected', handled_by, note)

async def refund_aftersale(as_id: str, handled_by: str, refund_amount: float | None=None) -> dict[str, Any] | None:
    return await _update_aftersale(as_id, 'refunded', handled_by, refund_amount=refund_amount)

async def create_application(user_id: str, shop_name: str, contact_name: str='', contact_phone: str='', license_no: str='', license_img: str='', address: str='', intro: str='') -> dict[str, Any]:
    async with dba.transaction() as c:
        '用户提交入驻申请。'
        existing = _fetchone(await c.execute("SELECT id FROM merchant_applications WHERE applicant_user_id=? AND status='pending'", (user_id,)))
        if existing:
            raise ValueError('已有待审核的入驻申请')
        app_id = await _new_id('APP')
        now = _now()
        async with dba.transaction() as c:
            await c.execute("INSERT INTO merchant_applications\n               (id, applicant_user_id, shop_name, contact_name, contact_phone, license_no,\n                license_img, address, intro, status, created_at)\n               VALUES (?,?,?,?,?,?,?,?,?,'pending',?)", (app_id, user_id, (shop_name or '')[:40], (contact_name or '')[:30], (contact_phone or '')[:20], (license_no or '')[:40], license_img or '', (address or '')[:120], (intro or '')[:200], now))
        return await get_application(app_id)

async def list_applications(status: str='', limit: int=50, offset: int=0) -> tuple[list[dict[str, Any]], int]:
    async with dba.transaction() as c:
        '入驻申请列表（倒序，可筛状态）。'
        where, args = (' WHERE 1=1', [])
        if status:
            where += ' AND a.status=?'
            args.append(status)
        total = _scalar(await c.execute(f'SELECT COUNT(*) FROM merchant_applications a{where}', args))
        rows = await c.execute(f'SELECT a.*, u.nickname, u.phone AS user_phone\n            FROM merchant_applications a\n            LEFT JOIN users u ON u.id = a.applicant_user_id\n            {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?', args + [limit, offset])
        return ([dict(r) for r in rows], int(total))

async def get_application(app_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '入驻申请详情。'
        row = _fetchone(await c.execute('SELECT a.*, u.nickname, u.phone AS user_phone\n           FROM merchant_applications a\n           LEFT JOIN users u ON u.id = a.applicant_user_id\n           WHERE a.id=?', (app_id,)))
        return dict(row) if row else None

async def approve_application(app_id: str, admin_id: str) -> dict[str, Any] | None:
    async with dba.transaction() as c:
        '审核通过：申请人提权 merchant + 创建/绑定店铺（shop 名取 shop_name）。\n\n    新店自动挂载 3 款种子方案（红线1：杜绝「进店无商品」空壳；\n    种子演示数据，商家后台可上下架/替换，上线前可清空重灌）。\n    '
        from backend.storage import catalog
        row = _fetchone(await c.execute('SELECT * FROM merchant_applications WHERE id=?', (app_id,)))
        if not row:
            return None
        app = dict(row)
        if app['status'] != 'pending':
            raise ValueError('该申请已处理')
        async with dba.transaction() as c:
            await c.execute("UPDATE merchant_applications\n               SET status='approved', reviewed_by=?, reviewed_at=? WHERE id=?", (admin_id, _now(), app_id))
        from backend.security import set_user_role
        set_user_role(app['applicant_user_id'], 'merchant')
        shop = await catalog.create_shop({'name': app['shop_name'], 'intro': app['intro'] or '', 'address': app['address'] or '', 'status': '营业中'})
        await catalog.merchant_bind(app['applicant_user_id'], shop['shop_id'])
        seed_plans = [r[0] for r in await c.execute("SELECT id FROM plans WHERE id IN ('P001','P002','P003')")]
        if seed_plans:
            async with dba.transaction() as c:
                for pid in seed_plans:
                    await c.execute("INSERT INTO shop_plans(shop_id, plan_id, status) VALUES (?,?,'on') ON CONFLICT (shop_id, plan_id) DO NOTHING", (shop['shop_id'], pid))
        return await get_application(app_id)

async def reject_application(app_id: str, admin_id: str, note: str='') -> dict[str, Any] | None:
    """审核拒绝（带备注）。"""
    async with dba.transaction() as c:
        cur = await c.execute("UPDATE merchant_applications\n               SET status='rejected', review_note=?, reviewed_by=?, reviewed_at=? WHERE id=? RETURNING id", ((note or '')[:500], admin_id, _now(), app_id))
        if len(cur) == 0:
            return None
    return await get_application(app_id)

async def list_merchants(limit: int=100) -> list[dict[str, Any]]:
    async with dba.transaction() as c:
        '已入驻商家（merchant 角色 + 绑定店铺）。'
        rows = await c.execute("SELECT u.id AS user_id, u.username, u.nickname, u.phone, u.created_at,\n                  ms.shop_id, s.name AS shop_name, s.created_at AS shop_created_at\n           FROM users u\n           JOIN merchant_shops ms ON ms.user_id = u.id\n           LEFT JOIN shops s ON s.id = ms.shop_id\n           WHERE u.role='merchant'\n           ORDER BY s.created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

async def list_reviews(status: str='', keyword: str='', limit: int=50, offset: int=0) -> tuple[list[dict[str, Any]], int]:
    async with dba.transaction() as c:
        '管理后台评价列表（含 hidden，可按状态/关键词筛选）。'
        where, args = (' WHERE 1=1', [])
        if status:
            where += ' AND r.status=?'
            args.append(status)
        kw = (keyword or '').strip()
        if kw:
            like = f'%{kw}%'
            where += ' AND (r.content LIKE ? OR u.nickname LIKE ? OR r.plan_id LIKE ?)'
            args += [like, like, like]
        total = _scalar(await c.execute(f'SELECT COUNT(*) FROM reviews r LEFT JOIN users u ON u.id = r.user_id{where}', args))
        rows = await c.execute(f'SELECT r.*, u.nickname, u.phone, p.name AS plan_name\n            FROM reviews r\n            LEFT JOIN users u ON u.id = r.user_id\n            LEFT JOIN plans p ON p.id = r.plan_id\n            {where} ORDER BY r.created_at DESC LIMIT ? OFFSET ?', args + [limit, offset])
        return ([dict(r) for r in rows], int(total))

async def set_review_status(review_id: str, status: str) -> bool:
    """隐藏/显示评价（visible|hidden）。"""
    if status not in ('visible', 'hidden'):
        raise ValueError(f'非法状态: {status}')
    async with dba.transaction() as c:
        cur = await c.execute('UPDATE reviews SET status=? WHERE id=? RETURNING id', (status, review_id))
    return len(cur) > 0

async def delete_review(review_id: str) -> bool:
    """删除评价。"""
    async with dba.transaction() as c:
        cur = await c.execute('DELETE FROM reviews WHERE id=? RETURNING id', (review_id,))
    return len(cur) > 0

async def dashboard_stats(days: int=7) -> dict[str, Any]:
    async with dba.transaction() as c:
        '平台数据看板聚合：GMV/订单/用户/新用户/热销方案/热门店铺/订单趋势。'
        gmv = _scalar(await c.execute('SELECT COALESCE(SUM(total_price),0) FROM orders'))
        order_count = _scalar(await c.execute('SELECT COUNT(*) FROM orders'))
        user_count = _scalar(await c.execute('SELECT COUNT(*) FROM users'))
        new_today = _scalar(await c.execute("SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')"))
        top_plans = [dict(r) for r in await c.execute('SELECT p.id AS plan_id, p.name, p.sold FROM plans p\n               ORDER BY p.sold DESC LIMIT 5')]
        top_shops = [dict(r) for r in await c.execute('SELECT s.id AS shop_id, s.name, s.sales FROM shops s\n               ORDER BY s.sales DESC LIMIT 5')]
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        trend = [dict(r) for r in await c.execute("SELECT date(created_at) AS date, COUNT(*) AS count, COALESCE(SUM(total_price),0) AS amount\n               FROM orders WHERE date(created_at) >= ?\n               GROUP BY date(created_at) ORDER BY date(created_at) ASC", (cutoff,))]
        return {'gmv': float(gmv), 'order_count': int(order_count), 'user_count': int(user_count), 'new_users_today': int(new_today), 'top_plans': top_plans, 'top_shops': top_shops, 'order_trend': trend}

def _fetchone(rows):
    return rows[0] if rows else None

def _scalar(rows):
    return next(iter(rows[0].values())) if rows else None
