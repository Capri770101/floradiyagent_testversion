"""skills/skill_order.py —— 下单技能（独立自包含模块）。

作为「技能」而非普通工具注册：自描述（docstring + schema）+ 自注册（@register_tool）。
职责边界清晰：
- 组装订单数据（从仓库取方案/店铺，计算金额）
- 写入 orders 表
- 返回 pay_jump 参数（小程序的 /pages/order/confirm 跳转信息）
**不直接调用微信支付**——支付由小程序承接，后端只负责把订单和跳转参数交给前端。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime

from config import settings
from storage.commerce import apply_best_coupon
from storage.db import transaction
from storage.repository import repo
from tools import _resolve_session_plan, register_tool

logger = logging.getLogger("skills.order")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _plan_price(plan: dict) -> float:
    """方案金额：预设方案取 price；DIY 方案无 price 字段，用预算明细的估算价兜底。"""
    if isinstance(plan.get("price"), (int, float)):
        return float(plan["price"])
    breakdown = plan.get("budget_breakdown") or {}
    if isinstance(breakdown.get("total_estimate"), (int, float)):
        return float(breakdown["total_estimate"])
    m = re.search(r"(\d+(?:\.\d+)?)", str(plan.get("estimated_price", "")))
    return float(m.group(1)) if m else 0.0


@register_tool(
    name="create_order",
    description="组装订单并生成小程序支付跳转参数（pay_jump）。不直接调用微信支付，支付由小程序承接。",
    parameters={
        "type": "object",
        "properties": {
            "shop_id": {"type": "string", "description": "店铺 ID，或 'first' 表示推荐列表第一家"},
            "plan_id": {"type": "string", "description": "方案 ID，或 'latest' 表示当前方案"},
            "plan_type": {"type": "string", "description": "existing | diy"},
        },
        "required": ["shop_id", "plan_id", "plan_type"],
    },
    inject_context=True,
    tags=["order"],
)
def create_order(
    shop_id: str, plan_id: str, plan_type: str, _context: dict | None = None
) -> str:
    """组装订单并写入 orders 表，返回 order_card + pay_jump 数据。"""
    user_id = (_context or {}).get("user_id", "anonymous")

    # 解析占位符：'first' → 推荐列表首店；方案引用经会话解析（latest → 会话最近引用方案，
    # 与 search_shops 推荐的是同一份，不再固定取首条预设方案导致下错单）
    shop = repo.get_shop(shop_id) if shop_id != "first" else repo.list_shops(None, None)[0]
    plan = _resolve_session_plan(plan_id, _context)
    if not shop or not plan:
        return json.dumps({"error": "店铺或方案不存在"}, ensure_ascii=False)

    # DIY 方案（diy=True）的 plan_type 由方案自身决定，忽略模型传入的占位值
    if plan.get("diy"):
        plan_type = "diy"

    order_id = "O_" + uuid.uuid4().hex[:10]
    total = _plan_price(plan)
    items = [{"plan_id": plan["plan_id"], "name": plan["name"], "price": total, "qty": 1}]

    with transaction() as c:
        c.execute(
            "INSERT INTO orders(order_id, user_id, plan_id, plan_type, shop_id, items, total_price, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                order_id,
                user_id,
                plan["plan_id"],
                plan_type,
                shop["shop_id"],
                json.dumps(items, ensure_ascii=False),
                total,
                _now(),
            ),
        )
    # 与 /orders 下单链路一致：自动抵扣最优优惠券（新人立减等）
    discount = apply_best_coupon(order_id, user_id, total)

    pay_jump = {
        "order_id": order_id,
        "page_path": settings.pay_page_path,
        "params": {
            "order_id": order_id,
            "total_price": total,
            "discount": discount,
            "shop_id": shop["shop_id"],
        },
    }
    logger.info("[skill_order] 订单 %s 已创建 user=%s shop=%s total=%.2f discount=%.2f", order_id, user_id, shop["shop_id"], total, discount)

    return json.dumps(
        {
            "order_id": order_id,
            "items": items,
            "total_price": total,
            "discount": discount,
            "plan_type": plan_type,
            "pay_jump": pay_jump,
        },
        ensure_ascii=False,
    )
