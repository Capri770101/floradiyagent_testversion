"""routers/merchant.py —— 商家工作台（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    _require_merchant,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)
from storage import commerce

router = APIRouter(tags=["merchant"])
logger = logging.getLogger("api")

@router.get("/merchant/stats")
async def merchant_stats_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度经营统计（订单 / GMV / 待发货 / 已完成 / 评价）。"""
    await _require_merchant(request)
    return await asyncio.to_thread(commerce.merchant_stats, shop_id)



@router.get("/merchant/orders")
async def merchant_orders_endpoint(
    request: Request, shop_id: str = "", status: str = "", limit: int = 50
) -> dict[str, Any]:
    """商家视角订单列表（任意用户，可按店铺 / 状态过滤）。"""
    await _require_merchant(request)
    return {"orders": await asyncio.to_thread(commerce.merchant_orders, shop_id, status, limit)}



@router.post("/merchant/orders/{order_id}/ship")
async def merchant_ship_endpoint(order_id: str, request: Request) -> dict[str, Any]:
    """商家代发货（不受订单归属限制）：paid -> shipped。"""
    await _require_merchant(request)
    try:
        o = await asyncio.to_thread(commerce.merchant_ship, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}



@router.get("/merchant/reviews")
async def merchant_reviews_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度评价列表。"""
    await _require_merchant(request)
    return {"reviews": await asyncio.to_thread(commerce.merchant_reviews, shop_id)}


