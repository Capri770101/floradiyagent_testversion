"""商家端接口：经营统计、订单列表（按店隔离）、代发货、评价列表、上传图片。

覆盖「商家端」后端链路：/merchant/stats 汇总订单/GMV/待发货/评价、
/merchant/orders 按店铺/状态过滤、/merchant/orders/{id}/ship 代发货（不受归属限制）、
/merchant/reviews 列表、/merchant/upload 图片上传；
权限与隔离：未登录 401、普通用户 403、merchant 角色放行、
未绑定店铺商家数据为空、越权访问未绑定店铺 403、admin 不受绑定限制。
"""
import asyncio

import backend.api as api
import pytest
from backend.security import set_user_role
from backend.storage import catalog
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c

def _register(client, username, role='merchant', bind=None):
    r = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'nickname': username})
    assert r.status_code == 200, r.text
    token = r.json()['token']
    uid = r.json()['user_id']
    if role != 'user':
        set_user_role(uid, role)
    if bind:
        assert asyncio.run(catalog.merchant_bind(uid, bind))
    return token

def _merchant_headers(token):
    return {'Authorization': f'Bearer {token}'}

def _create_and_pay(client, token, shop='S001', price=99):
    r = client.post('/orders', headers=_merchant_headers(token), json={'items': [{'plan_id': 'P001', 'name': '测试花束', 'price': price, 'qty': 1, 'shop': shop}]})
    assert r.status_code == 200, r.text
    oid = r.json()['order']['order_id']
    r = client.post('/pay', headers=_merchant_headers(token), json={'order_id': oid})
    assert r.status_code == 200, r.text
    return oid

def test_merchant_requires_login(client):
    r = client.get('/merchant/stats')
    assert r.status_code == 401

def test_merchant_forbids_normal_user(client):
    token = _register(client, 'mer_plain', role='user')
    r = client.get('/merchant/stats', headers=_merchant_headers(token))
    assert r.status_code == 403

def test_merchant_stats(client):
    token = _register(client, 'mer_a', bind='S001')
    _create_and_pay(client, token, shop='S001', price=99)
    r = client.get('/merchant/stats', headers=_merchant_headers(token))
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats['order_count'] >= 1
    assert stats['gmv'] >= 99
    assert stats['pending_ship'] >= 1
    assert 'shops' in stats

def test_merchant_orders_filter_by_shop_and_status(client):
    token = _register(client, 'mer_b', bind='S001')
    _create_and_pay(client, token, shop='S001', price=199)
    r = client.get('/merchant/orders', params={'shop_id': 'S001', 'status': 'paid'}, headers=_merchant_headers(token))
    assert r.status_code == 200
    orders = r.json()['orders']
    assert all(o['shop_id'] == 'S001' and o['status'] == 'paid' for o in orders)
    r = client.get('/merchant/orders', params={'status': 'done'}, headers=_merchant_headers(token))
    assert all(o['status'] == 'done' for o in r.json()['orders'])

def test_merchant_ship_any_user_order(client):
    token = _register(client, 'mer_c', bind='S001')
    oid = _create_and_pay(client, token, shop='S001')
    r = client.post(f'/merchant/orders/{oid}/ship', headers=_merchant_headers(token))
    assert r.status_code == 200, r.text
    assert r.json()['order']['status'] == 'shipped'
    r = client.post(f'/merchant/orders/{oid}/ship', headers=_merchant_headers(token))
    assert r.status_code == 400

def test_merchant_reviews(client):
    token = _register(client, 'mer_d', bind='S001')
    _create_and_pay(client, token, shop='S001')
    r = client.get('/merchant/reviews', headers=_merchant_headers(token))
    assert r.status_code == 200
    assert isinstance(r.json()['reviews'], list)

def test_merchant_without_binding_sees_nothing(client):
    """未绑定店铺的商家看不到任何数据（包括自己下的单，隔离到店）。"""
    token = _register(client, 'mer_e')
    before = client.get('/merchant/stats', headers=_merchant_headers(token)).json()
    _create_and_pay(client, token, shop='S001')
    after = client.get('/merchant/stats', headers=_merchant_headers(token)).json()
    assert after['order_count'] == before['order_count'] == 0
    assert after['shops'] == []
    r = client.get('/merchant/orders', headers=_merchant_headers(token))
    assert r.json()['orders'] == []
    r = client.get('/merchant/reviews', headers=_merchant_headers(token))
    assert r.json()['reviews'] == []

def test_merchant_scope_isolation(client):
    """绑定 S001 的商家看不到 S002 的订单（S002 是另一家店）。"""
    token = _register(client, 'mer_f', bind='S001')
    before = client.get('/merchant/stats', headers=_merchant_headers(token)).json()
    _create_and_pay(client, token, shop='S002', price=199)
    after = client.get('/merchant/stats', headers=_merchant_headers(token)).json()
    assert after['order_count'] == before['order_count']
    assert after['gmv'] == before['gmv']
    r = client.get('/merchant/orders', params={'shop_id': 'S002'}, headers=_merchant_headers(token))
    assert r.status_code == 403

def test_merchant_cannot_access_other_shop_order_detail(client):
    """IDOR 防护：绑定 S001 的商家查看/代发货/加物流他人(S002)订单 → 403。"""
    token_a = _register(client, 'mer_scope_a', bind='S001')
    oid_own = _create_and_pay(client, token_a, shop='S001')
    token_b = _register(client, 'mer_scope_b', bind='S002')
    oid_other = _create_and_pay(client, token_b, shop='S002')
    h = _merchant_headers(token_a)
    r = client.get(f'/merchant/orders/{oid_own}', headers=h)
    assert r.status_code == 200, r.text
    r = client.get(f'/merchant/orders/{oid_other}', headers=h)
    assert r.status_code == 403
    r = client.post(f'/merchant/orders/{oid_other}/ship', headers=h)
    assert r.status_code == 403
    r = client.post(f'/merchant/orders/{oid_other}/logistics', json={'text': '测试节点'}, headers=h)
    assert r.status_code == 403
    assert client.get('/merchant/orders/O_NO_SUCH', headers=h).status_code == 404

def test_merchant_shops_endpoint(client):
    token = _register(client, 'mer_g', bind='S001')
    r = client.get('/merchant/shops', headers=_merchant_headers(token))
    assert r.status_code == 200
    assert [s['id'] for s in r.json()['shops']] == ['S001']

def test_admin_cannot_access_merchant_console(client):
    """平台管理员走独立管理后台，无权访问商家工作台（2026-08 决策）。"""
    token = _register(client, 'mer_admin', role='admin')
    r = client.get('/merchant/shops', headers=_merchant_headers(token))
    assert r.status_code == 403
    r = client.get('/merchant/stats', headers=_merchant_headers(token))
    assert r.status_code == 403

def test_merchant_plans_forbidden_outside_scope(client):
    token = _register(client, 'mer_h', bind='S001')
    r = client.get('/merchant/plans', params={'shop_id': 'S002'}, headers=_merchant_headers(token))
    assert r.status_code == 403

def test_merchant_upload_image(client, tmp_path):
    token = _register(client, 'mer_i', bind='S001')
    r = client.post('/merchant/upload', headers=_merchant_headers(token), files={'file': ('pic.jpg', b'\xff\xd8\xff\xe0fakejpg', 'image/jpeg')})
    assert r.status_code == 200, r.text
    url = r.json()['url']
    assert url.startswith('/uploads/m')
    assert url.endswith('.jpg')
    r = client.get(url)
    assert r.status_code == 200
    assert r.content == b'\xff\xd8\xff\xe0fakejpg'

def test_merchant_upload_rejects_bad_type(client):
    token = _register(client, 'mer_j', bind='S001')
    r = client.post('/merchant/upload', headers=_merchant_headers(token), files={'file': ('evil.exe', b'MZfake', 'application/octet-stream')})
    assert r.status_code == 400

def test_merchant_upload_rejects_oversize(client):
    token = _register(client, 'mer_k', bind='S001')
    r = client.post('/merchant/upload', headers=_merchant_headers(token), files={'file': ('big.png', b'0' * (5 * 1024 * 1024 + 1), 'image/png')})
    assert r.status_code == 400

def test_merchant_upload_requires_login(client):
    r = client.post('/merchant/upload', files={'file': ('a.jpg', b'x', 'image/jpeg')})
    assert r.status_code == 401

def test_merchant_orders_keyword_filter(client):
    """按商品名关键词过滤：命中 items 快照 JSON（兼容 order_items 为空）。"""
    token = _register(client, 'mer_l', bind='S001')
    _create_and_pay(client, token, shop='S001', price=66)
    r = client.get('/merchant/orders', params={'keyword': '康乃馨'}, headers=_merchant_headers(token))
    assert r.status_code == 200
    orders = r.json()['orders']
    assert orders, '关键词应命中订单'
    assert all('康乃馨' in ','.join(i.get('name', '') for i in o['items']) for o in orders)

def test_merchant_orders_date_filter(client):
    """按日期范围过滤：created_at 兼容 ISO 与空格两种格式。"""
    token = _register(client, 'mer_m', bind='S001')
    _create_and_pay(client, token, shop='S001', price=88)
    today = __import__('datetime').date.today().isoformat()
    r = client.get('/merchant/orders', params={'date_from': today, 'date_to': today}, headers=_merchant_headers(token))
    assert r.status_code == 200
    assert r.json()['orders'], '今日订单应被日期范围命中'

def test_merchant_categories_crud(client):
    token = _register(client, 'mer_n', bind='S001')
    h = _merchant_headers(token)
    r = client.get('/merchant/categories', headers=h)
    assert r.status_code == 200
    cats = r.json()['categories']
    assert cats and 'plan_count' in cats[0]
    r = client.post('/merchant/categories', json={'name': '测试分类'}, headers=h)
    assert r.status_code == 200, r.text
    cid = r.json()['category']['id']
    r = client.post('/merchant/categories', json={'name': '测试分类'}, headers=h)
    assert r.status_code == 400
    r = client.put(f'/merchant/categories/{cid}', json={'name': '测试分类2'}, headers=h)
    assert r.status_code == 200
    assert r.json()['category']['name'] == '测试分类2'
    r = client.delete(f'/merchant/categories/{cid}', headers=h)
    assert r.status_code == 200
    assert client.get('/merchant/categories').status_code == 401

def test_merchant_update_shop_decoration(client):
    token = _register(client, 'mer_o', bind='S001')
    h = _merchant_headers(token)
    r = client.put('/merchant/shop/S001', json={'cover': '/uploads/mcover.jpg', 'logo': '/uploads/mlogo.jpg', 'hours': '08:00 - 20:00', 'address': '测试路 1 号', 'notice': '测试公告'}, headers=h)
    assert r.status_code == 200, r.text
    r = client.get('/merchant/stats', headers=h)
    assert r.status_code == 200
    shop = next(s for s in r.json()['shops'] if s['id'] == 'S001')
    assert shop['cover'] == '/uploads/mcover.jpg'
    assert shop['logo'] == '/uploads/mlogo.jpg'
    assert shop['hours'] == '08:00 - 20:00'
    assert shop['address'] == '测试路 1 号'
    assert shop['notice'] == '测试公告'
    r = client.get('/shops/S001')
    assert r.status_code == 200
    d = r.json()['shop']
    assert d['cover'] == '/uploads/mcover.jpg'
    assert d['logo'] == '/uploads/mlogo.jpg'
    assert d['hours'] == '08:00 - 20:00'

def _user_headers(client, username):
    r = client.post('/auth/login', json={'username': username, 'password': 'secret123'})
    assert r.status_code == 200, r.text
    return {'Authorization': f"Bearer {r.json()['token']}"}

def test_merchant_accept_order_flow(client):
    """商家接单：paid 待确认 -> accepted，用户收到接单通知。"""
    user_t = _register(client, 'mer_acc_user', role='user')
    oid = _create_and_pay(client, user_t, shop='S001')
    mer_t = _register(client, 'mer_acc', bind='S001')
    # 接单前：paid + 待确认
    r = client.get(f'/merchant/orders/{oid}', headers=_merchant_headers(mer_t))
    assert r.status_code == 200, r.text
    o = r.json()['order']
    assert o['status'] == 'paid'
    assert o['merchant_status'] == ''
    # 接单
    r = client.post(f'/merchant/orders/{oid}/accept', headers=_merchant_headers(mer_t))
    assert r.status_code == 200, r.text
    assert r.json()['order']['merchant_status'] == 'accepted'
    # 用户收到「商家已接单」通知
    uh = _user_headers(client, 'mer_acc_user')
    r = client.get('/notifications', headers=uh)
    titles = [n['title'] for n in r.json()['notifications']]
    assert any('接单' in t for t in titles), titles

def test_merchant_reject_order_refunds_and_notifies(client):
    """商家拒单：paid -> canceled + payments refunded + 优惠券返还 + 用户收到通知。"""
    user_t = _register(client, 'mer_rej_user', role='user')
    oid = _create_and_pay(client, user_t, shop='S001')
    mer_t = _register(client, 'mer_rej', bind='S001')
    r = client.post(f'/merchant/orders/{oid}/reject', headers=_merchant_headers(mer_t), json={'reason': '花材不足'})
    assert r.status_code == 200, r.text
    o = r.json()['order']
    assert o['status'] == 'canceled'
    assert o['merchant_status'] == 'rejected'
    # payments 已退款
    from backend.storage import db_async as dba
    from backend.storage.db import _run_async
    async def _pay_status():
        async with dba.transaction() as c:
            rows = await c.execute('SELECT status FROM payments WHERE order_id=?', (oid,))
            return rows[0]['status'] if rows else None
    assert _run_async(_pay_status()) == 'refunded'
    # 用户收到「拒单退款」通知
    uh = _user_headers(client, 'mer_rej_user')
    r = client.get('/notifications', headers=uh)
    titles = [n['title'] for n in r.json()['notifications']]
    assert any('拒单' in t for t in titles), titles

def test_merchant_cannot_confirm_out_of_scope_order(client):
    """越权：未绑定该店铺的商家不能接单/拒单（403）。"""
    user_t = _register(client, 'mer_scp_user', role='user')
    oid = _create_and_pay(client, user_t, shop='S001')
    other_t = _register(client, 'mer_scp', bind='S002')
    r = client.post(f'/merchant/orders/{oid}/accept', headers=_merchant_headers(other_t))
    assert r.status_code == 403
    r = client.post(f'/merchant/orders/{oid}/reject', headers=_merchant_headers(other_t), json={'reason': 'x'})
    assert r.status_code == 403

def test_merchant_cannot_accept_non_paid_order(client):
    """未支付订单不可接单（400）。"""
    _register(client, 'mer_np_user', role='user')
    r = client.post('/orders', headers=_user_headers(client, 'mer_np_user'), json={'items': [{'plan_id': 'P001', 'name': 'x', 'price': 99, 'qty': 1, 'shop': 'S001'}]})
    oid = r.json()['order']['order_id']
    mer_t = _register(client, 'mer_np', bind='S001')
    r = client.post(f'/merchant/orders/{oid}/accept', headers=_merchant_headers(mer_t))
    assert r.status_code == 400
