"""routers/admin.py —— 管理后台（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    PlanWriteRequest,
    ShopWriteRequest,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    _require_admin,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)

router = APIRouter(tags=["admin"])
logger = logging.getLogger("api")

@router.get("/admin/plans")
async def admin_list_plans(request: Request) -> dict[str, Any]:
    """后台管理列表：返回全字段方案（含 style/category_id）。"""
    await _require_admin(request)
    return {"plans": await asyncio.to_thread(catalog_store.list_plans)}



@router.post("/admin/plans")
async def admin_create_plan(req: PlanWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    p = await asyncio.to_thread(catalog_store.create_plan, req.model_dump(exclude_none=True))
    return {"plan": p}



@router.put("/admin/plans/{plan_id}")
async def admin_update_plan(plan_id: str, req: PlanWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    p = await asyncio.to_thread(
        catalog_store.update_plan, plan_id, req.model_dump(exclude_none=True)
    )
    if not p:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"plan": p}



@router.delete("/admin/plans/{plan_id}")
async def admin_delete_plan(plan_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await asyncio.to_thread(catalog_store.delete_plan, plan_id):
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"ok": True}



@router.get("/admin/shops")
async def admin_list_shops(request: Request) -> dict[str, Any]:
    """后台管理列表：返回全字段店铺（含 plan_ids 关联）。"""
    await _require_admin(request)
    return {"shops": await asyncio.to_thread(catalog_store.list_shops)}



@router.post("/admin/shops")
async def admin_create_shop(req: ShopWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    s = await asyncio.to_thread(catalog_store.create_shop, req.model_dump(exclude_none=True))
    return {"shop": s}



@router.put("/admin/shops/{shop_id}")
async def admin_update_shop(shop_id: str, req: ShopWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    s = await asyncio.to_thread(
        catalog_store.update_shop, shop_id, req.model_dump(exclude_none=True)
    )
    if not s:
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"shop": s}



@router.delete("/admin/shops/{shop_id}")
async def admin_delete_shop(shop_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await asyncio.to_thread(catalog_store.delete_shop, shop_id):
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"ok": True}


