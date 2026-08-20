"""tests/test_payment.py —— 支付网关抽象层 + commerce 支付逻辑。

覆盖点（均为纯逻辑、零网络、零 LLM）：
- SandboxProvider：下单即标记已付，pay_params 含模拟交易号。
- get_provider 注册表：默认 sandbox；未知渠道抛 PaymentConfigError。
- WeChatPayProvider / AlipayProvider：凭据未配置时 crea​te_payment / verify_notify 抛 PaymentConfigError。
- commerce.pay_order（sandbox）：落 payments 行 + 订单标记已付。
- commerce.mark_order_paid：回调确认后标记订单与 payments 已付。
- commerce.get_payment_status：轮询返回 paid/status。
"""

from __future__ import annotations

import pytest
from backend.storage import commerce
from backend.storage.db import init_db
from backend.storage.payment import (
    AlipayProvider,
    PaymentConfigError,
    SandboxProvider,
    WeChatPayProvider,
    get_provider,
)


def setup_module(module) -> None:
    # conftest 已将 DB_PATH 指向临时文件，这里建表 + 种子数据
    init_db()


# --------------------------------------------------------------------------- #
# Provider 抽象层
# --------------------------------------------------------------------------- #


def test_get_provider_default_is_sandbox() -> None:
    # 默认未配置时返回沙箱实例
    assert isinstance(get_provider(), SandboxProvider)
    assert isinstance(get_provider("sandbox"), SandboxProvider)


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(PaymentConfigError):
        get_provider("not_a_real_channel")


def test_sandbox_create_payment_marks_paid() -> None:
    order = {"order_id": "O_test1", "total_price": 99.0}
    intent = SandboxProvider().create_payment(order, "wechat")
    assert intent.paid is True
    assert intent.method == "wechat"
    assert intent.amount == 99.0
    assert intent.transaction_id and intent.transaction_id.startswith("SANDBOX_")
    assert intent.pay_params["sandbox"] is True
    # 沙箱无第三方回调
    assert SandboxProvider().verify_notify(b"{}", {}) is None


def test_wechat_missing_creds_raises() -> None:
    # 当前 .env 未配置微信凭据，创建支付必须抛 ConfigError（绝不静默工作）
    with pytest.raises(PaymentConfigError):
        WeChatPayProvider().create_payment({"order_id": "O_x", "total_price": 1.0}, "wechat", {"openid": "oABC"})


def test_alipay_missing_creds_raises() -> None:
    with pytest.raises(PaymentConfigError):
        AlipayProvider().create_payment({"order_id": "O_y", "total_price": 1.0}, "alipay")


# --------------------------------------------------------------------------- #
# commerce 支付逻辑
# --------------------------------------------------------------------------- #


def _make_order(user_id: str = "u_pay") -> str:
    """造一个已落库的测试订单（依赖 commerce.create_order）。

    注意：价格以目录为准（P001=199），客户端传 50 无效；2 件 → 总额 398。
    """
    items = [{"plan_id": "P001", "name": "测试花束", "price": 50.0, "qty": 2}]
    order = commerce.create_order(user_id, items)
    return order["order_id"]


def test_pay_order_sandbox_records_payment_and_marks_paid() -> None:
    order_id = _make_order()
    result = commerce.pay_order(order_id, "wechat")
    assert result is not None
    assert result["paid"] is True
    assert result["payment_id"]
    # 订单已标记已付
    order = commerce.get_order(order_id)
    assert order["paid"] is True
    assert order["status"] == "paid"
    # 应付金额 = 总额 - 优惠券抵扣（P001×2=398，自动满99减10 → 388）
    assert float(order["total_price"]) == 398.0
    assert float(order["discount"]) == 10.0
    # payments 行已落库且为 paid，金额 = 实付（已扣券）
    from backend.storage.db import get_conn

    pay_row = get_conn().execute(
        "SELECT * FROM payments WHERE order_id=?", (order_id,)
    ).fetchone()
    assert pay_row is not None
    assert pay_row["status"] == "paid"
    assert pay_row["method"] == "wechat"
    assert float(pay_row["amount"]) == 388.0


def test_pay_order_unknown_order_returns_none() -> None:
    assert commerce.pay_order("O_not_exist", "wechat") is None


def test_mark_order_paid_updates_order_and_payments() -> None:
    order_id = _make_order()
    # 先以沙箱下单（已 paid），这里测试 mark_order_paid 的幂等/回填逻辑：
    # 模拟一笔 pending 支付，再回调标记
    from backend.storage.db import get_conn

    conn = get_conn()
    conn.execute(
        "UPDATE orders SET paid=0, status='pending_payment' WHERE order_id=?", (order_id,)
    )
    conn.execute(
        "UPDATE payments SET status='pending', paid_at=NULL WHERE order_id=?", (order_id,)
    )
    conn.commit()

    ok = commerce.mark_order_paid(order_id, "WX_TXN_123")
    assert ok is True
    order = commerce.get_order(order_id)
    assert order["paid"] is True
    assert order["status"] == "paid"
    pay_row = conn.execute(
        "SELECT * FROM payments WHERE order_id=?", (order_id,)
    ).fetchone()
    assert pay_row["status"] == "paid"
    assert pay_row["transaction_id"] == "WX_TXN_123"


def test_get_payment_status_polling() -> None:
    order_id = _make_order()
    # 刚建单未支付：paid=False
    status = commerce.get_payment_status(order_id)
    assert status is not None
    assert status["order_id"] == order_id
    assert status["paid"] is False
    # 沙箱下单后：paid=True
    commerce.pay_order(order_id, "wechat")
    assert commerce.get_payment_status(order_id)["paid"] is True
    # 不存在的订单返回 None
    assert commerce.get_payment_status("O_not_exist") is None


def test_mark_order_paid_idempotent_no_double_points() -> None:
    """重复支付回调不重复发放积分 / 不重复插支付行（幂等）。"""
    from backend.storage.db import get_conn

    order_id = _make_order()
    conn = get_conn()
    conn.execute(
        "UPDATE orders SET paid=0, status='pending_payment' WHERE order_id=?", (order_id,)
    )
    conn.execute(
        "UPDATE payments SET status='pending', paid_at=NULL WHERE order_id=?", (order_id,)
    )
    conn.commit()

    def _rec_count():
        return conn.execute(
            "SELECT COUNT(*) FROM point_records WHERE order_id=?", (order_id,)
        ).fetchone()[0]

    assert _rec_count() == 0
    assert commerce.mark_order_paid(order_id, "TXN_1") is True
    assert _rec_count() == 1
    # 第二次回调：幂等跳过，不再发积分
    assert commerce.mark_order_paid(order_id, "TXN_2") is True
    assert _rec_count() == 1
    assert commerce.get_order(order_id)["paid"] is True
