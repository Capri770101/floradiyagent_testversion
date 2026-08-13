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
import uuid
from datetime import UTC, datetime

from config import settings
from storage.db import transaction
from storage.repository import repo
from tools import register_tool

logger = logging.getLogger("skills.order")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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

    # 解析占位符：'first' → 推荐列表首店；'latest' → 默认首方案
    shop = repo.get_shop(shop_id) if shop_id != "first" else repo.list_shops(None, None)[0]
    plan = repo.get_plan(plan_id) if plan_id != "latest" else repo.search_plans("")[0]
    if not shop or not plan:
        return json.dumps({"error": "店铺或方案不存在"}, ensure_ascii=False)

    order_id = "O_" + uuid.uuid4().hex[:10]
    total = float(plan["price"])
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

    pay_jump = {
        "order_id": order_id,
        "page_path": settings.pay_page_path,
        "params": {"order_id": order_id, "total_price": total, "shop_id": shop["shop_id"]},
    }
    logger.info("[skill_order] 订单 %s 已创建 user=%s shop=%s total=%.2f", order_id, user_id, shop["shop_id"], total)

    return json.dumps(
        {
            "order_id": order_id,
            "items": items,
            "total_price": total,
            "plan_type": plan_type,
            "pay_jump": pay_jump,
        },
        ensure_ascii=False,
    )
