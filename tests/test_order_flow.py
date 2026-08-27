"""订单状态流转 + 物流时间线：created -> paid -> shipped -> done，以及取消。

覆盖「订单状态机」后端链路：发货 / 签收 / 取消的动作端点（POST /orders/{id}/action）
必须：owner 校验、非法流转 400、物流事件按 seq 追加并随详情返回。
"""
import backend.api as api
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c

def _register(client, username):
    r = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'nickname': username})
    assert r.status_code == 200, r.text
    return r.json()['token']

def _create_order(client, token):
    r = client.post('/orders', headers={'Authorization': f'Bearer {token}'}, json={'items': [{'plan_id': 'P001', 'name': '测试花束', 'price': 99, 'qty': 1, 'shop': 'S001'}]})
    assert r.status_code == 200, r.text
    return r.json()['order']['order_id']

def _pay(client, token, oid):
    r = client.post('/pay', headers={'Authorization': f'Bearer {token}'}, json={'order_id': oid, 'method': 'wechat'})
    assert r.status_code == 200, r.text

def _action(client, token, oid, action):
    return client.post(f'/orders/{oid}/action', headers={'Authorization': f'Bearer {token}'}, json={'action': action})

def test_full_status_flow_with_logistics(client):
    token = _register(client, 'flow_a')
    oid = _create_order(client, token)
    o = client.get(f'/orders/{oid}', headers={'Authorization': f'Bearer {token}'}).json()['order']
    assert o['status'] == 'created'
    assert any('等待支付' in e['text'] for e in o['logistics'])
    _pay(client, token, oid)
    o = client.get(f'/orders/{oid}', headers={'Authorization': f'Bearer {token}'}).json()['order']
    assert o['status'] == 'paid'
    assert any('支付成功' in e['text'] for e in o['logistics'])
    r = _action(client, token, oid, 'ship')
    assert r.status_code == 200, r.text
    o = r.json()['order']
    assert o['status'] == 'shipped'
    texts = [e['text'] for e in o['logistics']]
    assert any('已发货' in t for t in texts)
    assert any('转运中心' in t for t in texts)
    assert len(o['logistics']) >= 4
    r = _action(client, token, oid, 'complete')
    assert r.status_code == 200, r.text
    o = r.json()['order']
    assert o['status'] == 'done'
    assert any('已签收' in e['text'] for e in o['logistics'])
    r = _action(client, token, oid, 'ship')
    assert r.status_code == 400

def test_cancel_created_order(client):
    token = _register(client, 'flow_b')
    oid = _create_order(client, token)
    r = _action(client, token, oid, 'cancel')
    assert r.status_code == 200
    assert r.json()['order']['status'] == 'canceled'

def test_cannot_cancel_paid_order(client):
    token = _register(client, 'flow_c')
    oid = _create_order(client, token)
    _pay(client, token, oid)
    r = _action(client, token, oid, 'cancel')
    assert r.status_code == 400

def test_action_requires_owner(client):
    token_a = _register(client, 'flow_d')
    token_b = _register(client, 'flow_e')
    oid = _create_order(client, token_a)
    _pay(client, token_a, oid)
    r = _action(client, token_b, oid, 'ship')
    assert r.status_code == 403

def test_list_orders_returns_own_orders(client):
    token = _register(client, 'flow_f')
    oid = _create_order(client, token)
    _pay(client, token, oid)
    r = client.get('/orders', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    ids = [o['order_id'] for o in r.json()['orders']]
    assert oid in ids
    assert all('logistics' in o for o in r.json()['orders'])
