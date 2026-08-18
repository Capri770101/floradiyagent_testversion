"""storage/config.py —— 运营配置（M7/M9）：key-value JSON 存取 + 公开聚合。

前端写死的配送时段 / 运费 / 优惠券规则 / FAQ / 公告统一后端化（红线2）。
未配置时由后端返回 seed 默认值（后端兜底，前端不做业务兜底）。
"""
from __future__ import annotations

import json
from typing import Any

from storage.db import get_conn, transaction

# 键名
K_DELIVERY = "delivery_options"
K_SHIPPING = "shipping_fee"
K_COUPON = "coupon_rules"
K_FAQS = "faqs"
K_ANNOUNCE = "announcements"

# seed 默认值（上线前可改/清空重灌）
DEFAULTS: dict[str, Any] = {
    K_DELIVERY: ["今天 18:00–20:00", "明天 10:00–12:00", "后天 14:00–16:00"],
    K_SHIPPING: 5,
    K_COUPON: {
        "满减示例": "满 199 减 20（sandbox 规则，上线前配置）",
    },
    K_FAQS: [
        {"q": "下单后多久发货？", "a": "支付成功后 24 小时内由花店发货，配送时间 1-3 天，节假日顺延。"},
        {"q": "花束可以指定配送时间吗？", "a": "可以，在确认订单页选择配送时段，花店会按选择安排。"},
        {"q": "收到的花不满意怎么办？", "a": "可在订单完成后评价并联系客服，我们将按流程处理退换。"},
        {"q": "积分有什么用？", "a": "每笔支付都会返还积分，未来可在积分商城兑换鲜花券与周边。"},
    ],
    K_ANNOUNCE: [],
}


def _load(key: str) -> Any | None:
    row = get_conn().execute(
        "SELECT value FROM operations_config WHERE key=?", (key,)
    ).fetchone()
    if not row or not row["value"]:
        return None
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return None


def _save(key: str, value: Any) -> None:
    with transaction() as c:
        c.execute(
            "INSERT INTO operations_config(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def get_config(key: str, default: Any = None) -> Any:
    """读取配置（未设置返回 default）。"""
    v = _load(key)
    return v if v is not None else default


def set_config(key: str, value: Any) -> Any:
    """写入配置（返回落库值）。"""
    _save(key, value)
    return value


def public_config() -> dict[str, Any]:
    """公开聚合配置（H5 消费；未配置项用 seed 默认值，前端不做业务兜底）。"""
    return {
        "delivery_options": get_config(K_DELIVERY, DEFAULTS[K_DELIVERY]),
        "shipping_fee": get_config(K_SHIPPING, DEFAULTS[K_SHIPPING]),
        "coupon_rules": get_config(K_COUPON, DEFAULTS[K_COUPON]),
        "faqs": get_config(K_FAQS, DEFAULTS[K_FAQS]),
        "announcements": get_config(K_ANNOUNCE, DEFAULTS[K_ANNOUNCE]),
    }


def admin_config() -> dict[str, Any]:
    """管理端配置读取（与公开一致，便于表单回显）。"""
    return public_config()


def update_operations(data: dict[str, Any]) -> dict[str, Any]:
    """管理端整体写运营配置（仅更新传入字段）。"""
    if "delivery_options" in data:
        opts = data["delivery_options"]
        if not isinstance(opts, list) or not all(isinstance(x, str) and x.strip() for x in opts):
            raise ValueError("配送时段必须是字符串数组")
        set_config(K_DELIVERY, [x.strip()[:40] for x in opts])
    if "shipping_fee" in data:
        fee = data["shipping_fee"]
        if not isinstance(fee, (int, float)) or fee < 0:
            raise ValueError("配送费必须是非负数字")
        set_config(K_SHIPPING, float(fee))
    if "coupon_rules" in data:
        rules = data["coupon_rules"]
        if not isinstance(rules, dict):
            raise ValueError("优惠券规则必须是对象")
        set_config(K_COUPON, rules)
    return public_config()


def update_faqs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """整体写 FAQ（[{q,a}]）。"""
    cleaned = []
    for it in items:
        q = str(it.get("q", "")).strip()
        a = str(it.get("a", "")).strip()
        if q or a:
            cleaned.append({"q": q[:100], "a": a[:500]})
    set_config(K_FAQS, cleaned)
    return cleaned


def update_announcements(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """整体写公告（[{text, link?}] 或 [{content}]，归一为 {content}）。"""
    cleaned = []
    for it in items:
        content = str(it.get("content") or it.get("text") or "").strip()
        if content:
            cleaned.append({"content": content[:200]})
    set_config(K_ANNOUNCE, cleaned)
    return cleaned
