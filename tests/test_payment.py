"""tests/test_payment.py —— 支付网关抽象层 + commerce 支付逻辑。

覆盖点（均为纯逻辑、零网络、零 LLM）：
- SandboxProvider：下单即标记已付，pay_params 含模拟交易号。
- get_provider 注册表：默认 sandbox；未知渠道抛 PaymentConfigError。
- WeChatPayProvider / AlipayProvider：凭据未配置时 crea\u200bte_payment / verify_notify 抛 PaymentConfigError。
- commerce.pay_order（sandbox）：落 payments 行 + 订单标记已付。
- commerce.mark_order_paid：回调确认后标记订单与 payments 已付。
- commerce.get_payment_status：轮询返回 paid/status。
"""
from __future__ import annotations

import asyncio

import pytest
from backend.storage import commerce
from backend.storage.db import init_db
from backend.storage.payment import (
    AlipayProvider,
    PaymentConfigError,
    PaymentError,
    SandboxProvider,
    WeChatPayProvider,
    WeChatPayV2Provider,
    get_provider,
)


def _fetch(sql: str, params: tuple = ()) -> list:
    """PG 模式走异步查询；sqlite 回退用同步 get_conn()。"""
    from backend.storage import db_async as dba
    if dba.dialect() == 'postgresql':
        from backend.storage.db import _run_async
        async def _f() -> list:
            async with dba.transaction() as c:
                return await c.execute(sql, params)
        return _run_async(_f())
    from backend.storage.db import get_conn
    return get_conn().execute(sql, params).fetchall()

def _exec(sql: str, params: tuple = ()) -> None:
    """PG 模式走异步写；sqlite 回退用同步 get_conn()（写后立即提交）。"""
    from backend.storage import db_async as dba
    if dba.dialect() == 'postgresql':
        from backend.storage.db import _run_async
        async def _f() -> None:
            async with dba.transaction() as c:
                await c.execute(sql, params)
        _run_async(_f())
        return
    from backend.storage.db import get_conn
    conn = get_conn()
    conn.execute(sql, params)
    conn.commit()


def setup_module(module) -> None:
    init_db()
    from backend.storage import config as config_store
    asyncio.run(config_store.set_config(config_store.K_SHIPPING, 5.0))

def test_get_provider_default_is_sandbox() -> None:
    assert isinstance(get_provider(), SandboxProvider)
    assert isinstance(get_provider('sandbox'), SandboxProvider)

def test_get_provider_unknown_raises() -> None:
    with pytest.raises(PaymentConfigError):
        get_provider('not_a_real_channel')

def test_sandbox_create_payment_marks_paid() -> None:
    order = {'order_id': 'O_test1', 'total_price': 99.0}
    intent = SandboxProvider().create_payment(order, 'wechat')
    assert intent.paid is True
    assert intent.method == 'wechat'
    assert intent.amount == 99.0
    assert intent.transaction_id and intent.transaction_id.startswith('SANDBOX_')
    assert intent.pay_params['sandbox'] is True
    assert SandboxProvider().verify_notify(b'{}', {}) is None

def test_wechat_missing_creds_raises() -> None:
    with pytest.raises(PaymentConfigError):
        WeChatPayProvider().create_payment({'order_id': 'O_x', 'total_price': 1.0}, 'wechat', {'openid': 'oABC'})

def test_alipay_missing_creds_raises() -> None:
    with pytest.raises(PaymentConfigError):
        AlipayProvider().create_payment({'order_id': 'O_y', 'total_price': 1.0}, 'alipay')

# ---------------- 退款（Refund）----------------

def test_base_provider_refund_unsupported() -> None:
    """未实现 request_refund 的渠道默认抛「暂不支持退款」。"""
    with pytest.raises(PaymentError):
        AlipayProvider().request_refund({'order_id': 'O_x', 'total_price': 1.0})

def test_sandbox_request_refund_success() -> None:
    """沙箱退款模拟成功，回填模拟退款单号。"""
    r = SandboxProvider().request_refund({'order_id': 'O_rf', 'total_price': 99.0})
    assert r.refund_id.startswith('SANDBOX_REFUND_')
    assert r.amount == 99.0
    assert r.status == 'refunded'
    # 部分退款金额
    r2 = SandboxProvider().request_refund({'order_id': 'O_rf', 'total_price': 99.0}, amount=30.0)
    assert r2.amount == 30.0

def test_wechat_v2_refund_missing_creds_raises() -> None:
    with pytest.raises(PaymentConfigError):
        WeChatPayV2Provider().request_refund({'order_id': 'O_rf', 'total_price': 1.0})

def test_wechat_v2_refund_missing_cert_raises() -> None:
    """v2 退款走双向 TLS，未配 apiclient 证书就拒绝（绝不静默成功）。"""
    from backend.config import settings
    # 临时清空凭据（包括 .env 里的路径），确保 _load_pem 返回空
    old_cert = settings.wechatpay_v2_cert
    old_key = settings.wechatpay_v2_private_key
    old_mchid = settings.wechatpay_v2_mch_id
    old_apikey = settings.wechatpay_v2_api_key
    settings.wechatpay_v2_mch_id = '123'
    settings.wechatpay_v2_api_key = 'k' * 32
    settings.wechatpay_v2_cert = ''
    settings.wechatpay_v2_private_key = ''
    try:
        with pytest.raises(PaymentConfigError):
            WeChatPayV2Provider().request_refund({'order_id': 'O_rf', 'total_price': 1.0})
    finally:
        settings.wechatpay_v2_cert = old_cert
        settings.wechatpay_v2_private_key = old_key
        settings.wechatpay_v2_mch_id = old_mchid
        settings.wechatpay_v2_api_key = old_apikey

def _make_order(user_id: str='u_pay') -> str:
    """造一个已落库的测试订单（依赖 commerce.create_order）。

    注意：价格以目录为准（P001=199），客户端传 50 无效；2 件 → 总额 398。
    """
    items = [{'plan_id': 'P001', 'name': '测试花束', 'price': 50.0, 'qty': 2}]
    order = asyncio.run(commerce.create_order(user_id, items))
    return order['order_id']

def test_pay_order_sandbox_records_payment_and_marks_paid() -> None:
    order_id = _make_order()
    result = asyncio.run(commerce.pay_order(order_id, 'wechat'))
    assert result is not None
    assert result['paid'] is True
    assert result['payment_id']
    order = asyncio.run(commerce.get_order(order_id))
    assert order['paid'] is True
    assert order['status'] == 'paid'
    assert float(order['total_price']) == 398.0
    assert float(order['discount']) == 10.0
    pay_rows = _fetch('SELECT * FROM payments WHERE order_id=?', (order_id,))
    pay_row = pay_rows[0] if pay_rows else None
    assert pay_row is not None
    assert pay_row['status'] == 'paid'
    assert pay_row['method'] == 'wechat'
    assert float(pay_row['amount']) == 393.0

def test_pay_order_unknown_order_returns_none() -> None:
    assert asyncio.run(commerce.pay_order('O_not_exist', 'wechat')) is None

def test_mark_order_paid_updates_order_and_payments() -> None:
    order_id = _make_order()
    _exec("UPDATE orders SET paid=0, status='pending_payment' WHERE order_id=?", (order_id,))
    _exec("UPDATE payments SET status='pending', paid_at=NULL WHERE order_id=?", (order_id,))
    ok = asyncio.run(commerce.mark_order_paid(order_id, 'WX_TXN_123'))
    assert ok is True
    order = asyncio.run(commerce.get_order(order_id))
    assert order['paid'] is True
    assert order['status'] == 'paid'
    pay_rows = _fetch('SELECT * FROM payments WHERE order_id=?', (order_id,))
    pay_row = pay_rows[0] if pay_rows else None
    assert pay_row['status'] == 'paid'
    assert pay_row['transaction_id'] == 'WX_TXN_123'

def test_get_payment_status_polling() -> None:
    order_id = _make_order()
    status = asyncio.run(commerce.get_payment_status(order_id))
    assert status is not None
    assert status['order_id'] == order_id
    assert status['paid'] is False
    asyncio.run(commerce.pay_order(order_id, 'wechat'))
    assert asyncio.run(commerce.get_payment_status(order_id))['paid'] is True
    assert asyncio.run(commerce.get_payment_status('O_not_exist')) is None

def test_mark_order_paid_idempotent_no_double_points() -> None:
    """重复支付回调不重复发放积分 / 不重复插支付行（幂等）。"""
    order_id = _make_order()
    _exec("UPDATE orders SET paid=0, status='pending_payment' WHERE order_id=?", (order_id,))
    _exec("UPDATE payments SET status='pending', paid_at=NULL WHERE order_id=?", (order_id,))

    def _rec_count():
        rows = _fetch('SELECT COUNT(*) FROM point_records WHERE order_id=?', (order_id,))
        return rows[0][0]
    assert _rec_count() == 0
    assert asyncio.run(commerce.mark_order_paid(order_id, 'TXN_1')) is True
    assert _rec_count() == 1
    assert asyncio.run(commerce.mark_order_paid(order_id, 'TXN_2')) is True
    assert _rec_count() == 1
    assert asyncio.run(commerce.get_order(order_id))['paid'] is True

# ---------------- commerce.refund_order（sandbox）----------------

def _ensure_plan_p001() -> None:
    """确保测试库有 id=P001 的目录商品（部分 seed 用动态 id，这里按需补一条）。"""
    if not _fetch('SELECT 1 FROM plans WHERE id=?', ('P001',)):
        _exec("INSERT INTO plans (id,name,price,desc,effect_image_url,merchant_name,tags,style,rating,sold,ai_reason,created_at)\n           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              ('P001', '测试花束', 199.0, '', '', '测试店', '[]', '', 4.8, 0, '', '2024-01-01 00:00:00'))

def _make_paid_order(user_id: str = 'u_rf') -> str:
    """造一个已落库且已支付订单（含 payments 行，status='paid'）。"""
    from backend.config import settings
    settings.payment_provider = 'sandbox'
    _ensure_plan_p001()
    order = asyncio.run(commerce.create_order(user_id, [{'plan_id': 'P001', 'name': 'x', 'price': 1, 'qty': 1}]))
    asyncio.run(commerce.mark_order_paid(order['order_id'], 'WX_TXN_MAKE'))
    return order['order_id']

def test_refund_order_marks_payment_refunded() -> None:
    """refund_order（sandbox）把已支付 payments 翻为 refunded，返回模拟退款单号。"""
    order_id = _make_paid_order()
    res = asyncio.run(commerce.refund_order(order_id))
    assert res is not None
    assert res['refund_id'].startswith('SANDBOX_REFUND_')
    pay_rows = _fetch('SELECT * FROM payments WHERE order_id=?', (order_id,))
    assert pay_rows[0]['status'] == 'refunded'
    logs = _fetch('SELECT * FROM order_logistics WHERE order_id=?', (order_id,))
    assert any('退款' in r['text'] for r in logs)

def test_refund_order_unpaid_raises() -> None:
    """未支付订单退款应拒绝。"""
    from backend.config import settings
    settings.payment_provider = 'sandbox'
    _ensure_plan_p001()
    order = asyncio.run(commerce.create_order('u_rf2', [{'plan_id': 'P001', 'name': 'x', 'price': 1, 'qty': 1}]))
    with pytest.raises(ValueError):
        asyncio.run(commerce.refund_order(order['order_id']))

def test_merchant_reject_marks_payment_refunded() -> None:
    """商家拒单触发真实退款：订单 canceled/rejected，payments 翻 refunded。"""
    order_id = _make_paid_order('u_rf3')
    o = asyncio.run(commerce.merchant_reject_order(order_id, '拒单测试'))
    assert o['status'] == 'canceled'
    assert o['merchant_status'] == 'rejected'
    pay_rows = _fetch('SELECT * FROM payments WHERE order_id=?', (order_id,))
    assert pay_rows[0]['status'] == 'refunded'
