"""优惠券自动抵扣 + 支付返积分：新人券发放、下单用券、积分落账。

覆盖「优惠券/积分」后端链路：GET /coupons 新用户自动发券、下单自动抵扣最优券
（金额落订单 discount + 券标记 used）、支付成功按金额返积分（GET /points）。
"""
import asyncio

import backend.api as api
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _fixed_shipping():
    """固定配送费=5，避免受其他测试（test_admin_ext 改 8）污染，保证积分断言确定。"""
    from backend.storage import config as config_store
    asyncio.run(config_store.set_config(config_store.K_SHIPPING, 5.0))
    yield

@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c

def _register(client, username):
    r = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'nickname': username})
    assert r.status_code == 200, r.text
    return r.json()['token']

def _create_order(client, token, price=99):
    r = client.post('/orders', headers={'Authorization': f'Bearer {token}'}, json={'items': [{'plan_id': 'P001', 'name': '测试花束', 'price': price, 'qty': 1, 'shop': 'S001'}]})
    assert r.status_code == 200, r.text
    return r.json()['order']

def test_welcome_coupon_auto_issued(client):
    token = _register(client, 'cp_a')
    r = client.get('/coupons', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    coupons = r.json()['coupons']
    assert len(coupons) == 1
    assert coupons[0]['discount'] == 10
    assert coupons[0]['status'] == 'unused'

def test_order_auto_applies_best_coupon(client):
    token = _register(client, 'cp_b')
    order = _create_order(client, token, price=99)
    assert order['total_price'] == 199
    assert order['discount'] == 10
    assert order['coupon_id']
    coupons = client.get('/coupons', headers={'Authorization': f'Bearer {token}'}).json()['coupons']
    used = [c for c in coupons if c['id'] == order['coupon_id']]
    assert used and used[0]['status'] == 'used'
    order2 = _create_order(client, token, price=199)
    assert order2['discount'] == 0

def test_pay_awards_points(client):
    token = _register(client, 'cp_c')
    order = _create_order(client, token, price=99)
    r = client.post('/pay', headers={'Authorization': f'Bearer {token}'}, json={'order_id': order['order_id'], 'method': 'sandbox'})
    assert r.status_code == 200
    points = client.get('/points', headers={'Authorization': f'Bearer {token}'}).json()
    assert points['balance'] == 194
    assert any('返积分' in rec['reason'] for rec in points['records'])

def test_points_not_awarded_before_pay(client):
    token = _register(client, 'cp_d')
    _create_order(client, token, price=99)
    points = client.get('/points', headers={'Authorization': f'Bearer {token}'}).json()
    assert points['balance'] == 0
