"""内容举报闭环测试（阶段5 内容审核体系：举报巡查）。

覆盖：
- 未登录举报 → 401；非法 target_type → 400
- 用户举报 plan/shop → pending；列表可见举报人昵称与目标摘要
- 非 admin 查列表 / 处理 → 403
- admin 处理 banned → 目标商品下架（shop_plans.status=off）
- 处理不存在的举报 → 404
"""
import backend.api as api
import pytest
from backend.security import set_user_role
from backend.storage.db import get_conn
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c

def _register(client, username, role='user'):
    r = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'nickname': username})
    if r.status_code == 409:
        path = '/auth/admin-login' if role == 'admin' else '/auth/login'
        r = client.post(path, json={'username': username, 'password': 'secret123'})
        assert r.status_code == 200, r.text
        token = r.json()['token']
        uid = r.json()['user_id']
        if role != 'user':
            set_user_role(uid, role)
        return (token, uid)
    assert r.status_code == 200, r.text
    token = r.json()['token']
    uid = r.json()['user_id']
    if role != 'user':
        set_user_role(uid, role)
    return (token, uid)

def _h(token):
    return {'Authorization': f'Bearer {token}'}

def _shop_plan_status(plan_id):
    from backend.storage import db_async as dba
    if dba.dialect() == 'postgresql':
        from backend.storage.db import _run_async
        async def _q():
            async with dba.transaction() as c:
                rows = await c.execute('SELECT status FROM shop_plans WHERE plan_id=?', (plan_id,))
                return rows[0][0] if rows else None
        return _run_async(_q())
    conn = get_conn()
    row = conn.execute('SELECT status FROM shop_plans WHERE plan_id = ?', (plan_id,)).fetchone()
    return row[0] if row else None

def test_report_requires_login(client):
    r = client.post('/reports', json={'target_type': 'plan', 'target_id': 'P001', 'reason': '违规内容'})
    assert r.status_code == 401

def test_report_create_and_invalid_type(client):
    token, _ = _register(client, 'rep_u1')
    r = client.post('/reports', json={'target_type': 'plan', 'target_id': 'P001', 'reason': '图片违规', 'content': '涉嫌违规图'}, headers=_h(token))
    assert r.status_code == 200, r.text
    item = r.json()['report']
    assert item['status'] == 'pending'
    assert item['target_type'] == 'plan'
    assert item['target_id'] == 'P001'
    assert item['user_id']
    r = client.post('/reports', json={'target_type': 'bogus', 'target_id': 'P001', 'reason': 'x'}, headers=_h(token))
    assert r.status_code == 400

def test_report_shop_and_list_scoped(client):
    token, _ = _register(client, 'rep_u2')
    client.post('/reports', json={'target_type': 'shop', 'target_id': 'S001', 'reason': '虚假宣传'}, headers=_h(token))
    r = client.get('/reports', headers=_h(token))
    assert r.status_code == 403
    at, _ = _register(client, 'rep_admin', role='admin')
    r = client.get('/reports', headers=_h(at))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['total'] >= 1
    shop_rep = next(x for x in body['reports'] if x['target_type'] == 'shop')
    assert shop_rep['reporter'] == 'rep_u2'
    assert shop_rep['target_title']

def test_report_admin_handle_banned_takes_down_plan(client):
    token, _ = _register(client, 'rep_u3')
    r = client.post('/reports', json={'target_type': 'plan', 'target_id': 'P001', 'reason': '违禁品'}, headers=_h(token))
    report_id = r.json()['report']['id']
    assert _shop_plan_status('P001') == 'on'
    at, _ = _register(client, 'rep_admin2', role='admin')
    r = client.post(f'/reports/{report_id}/handle', json={'status': 'banned'}, headers=_h(at))
    assert r.status_code == 200, r.text
    assert r.json()['report']['status'] == 'banned'
    assert _shop_plan_status('P001') == 'off'
    r2 = client.post('/reports', json={'target_type': 'shop', 'target_id': 'S001', 'reason': 'x'}, headers=_h(token))
    rid2 = r2.json()['report']['id']
    assert client.post(f'/reports/{rid2}/handle', json={'status': 'bogus'}, headers=_h(at)).status_code == 400
    assert client.post('/reports/R_NOPE/handle', json={'status': 'rejected'}, headers=_h(at)).status_code == 404

def test_report_handle_rejected_and_review_target(client):
    token, _ = _register(client, 'rep_u4')
    r = client.post('/reports', json={'target_type': 'review', 'target_id': 'RV_NOPE', 'reason': '辱骂'}, headers=_h(token))
    rid = r.json()['report']['id']
    at, _ = _register(client, 'rep_admin3', role='admin')
    r = client.post(f'/reports/{rid}/handle', json={'status': 'rejected'}, headers=_h(at))
    assert r.status_code == 200, r.text
    assert r.json()['report']['status'] == 'rejected'
    r = client.get('/reports?status=rejected', headers=_h(at))
    assert r.status_code == 200
    assert all(x['status'] == 'rejected' for x in r.json()['reports'])
