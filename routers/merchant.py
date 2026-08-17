"""routers/merchant.py —— 商家工作台（api.py 拆分，2026-08 重构）。

权限模型：merchant/admin 角色可访问；数据按「商家-店铺绑定」隔离——
普通商家只能查看/管理自己绑定店铺的订单、评价、商品与店铺资料，
admin 不受绑定限制（scope=None 表示全部店铺）。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from config import settings
from routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    PlanWriteRequest,
    ShopWriteRequest,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    _merchant_scope,
    _require_merchant,
    _require_shop_in_scope,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)
from storage import commerce, diy

router = APIRouter(tags=["merchant"])
logger = logging.getLogger("api")

# 上传图片扩展名白名单（防任意文件落地）
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

@router.get("/merchant/stats")
async def merchant_stats_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度经营统计（订单 / GMV / 待发货 / 已完成 / 评价），按绑定店铺隔离。"""
    _, scope = await _merchant_scope(request)
    if shop_id:
        _require_shop_in_scope(shop_id, scope)
    return await asyncio.to_thread(commerce.merchant_stats, scope, shop_id)



@router.get("/merchant/shops")
async def merchant_shops_endpoint(request: Request) -> dict[str, Any]:
    """商家可管理的店铺列表（admin 返回全部店铺）。"""
    uid, scope = await _merchant_scope(request)
    shops = await asyncio.to_thread(catalog_store.merchant_shops, uid)
    if scope is None:
        shops = await asyncio.to_thread(catalog_store.list_shops)
    return {"shops": shops}



@router.get("/merchant/orders")
async def merchant_orders_endpoint(
    request: Request, shop_id: str = "", status: str = "", limit: int = 50
) -> dict[str, Any]:
    """商家视角订单列表（按绑定店铺隔离，可按店铺 / 状态过滤）。"""
    _, scope = await _merchant_scope(request)
    if shop_id:
        _require_shop_in_scope(shop_id, scope)
    return {"orders": await asyncio.to_thread(commerce.merchant_orders, scope, shop_id, status, limit)}



@router.get("/merchant/orders/{order_id}")
async def merchant_order_detail_endpoint(order_id: str, request: Request) -> dict[str, Any]:
    """商家视角订单详情：附带 DIY 方案制作卡（花材配比/包装/步骤/卡片留言）。

    商家按单备货的唯一数据源：订单的 plan_id 关联 diy_plans，返回完整制作信息；
    非 DIY 方案（目录商品）不附带 plan 字段。
    """
    await _require_merchant(request)
    o = await asyncio.to_thread(commerce.get_order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    if o.get("plan_id"):
        plan = await asyncio.to_thread(diy.get_diy_plan, o["plan_id"])
        if plan:
            o["plan"] = plan
    return {"order": o}



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


class LogisticsWriteRequest(BaseModel):
    """商家追加物流节点请求体。"""

    text: str = Field(..., min_length=1, max_length=200)


@router.post("/merchant/orders/{order_id}/logistics")
async def merchant_add_logistics_endpoint(
    order_id: str, body: LogisticsWriteRequest, request: Request
) -> dict[str, Any]:
    """商家手动追加物流节点（仅配送中 shipped 状态可追加）。"""
    await _require_merchant(request)
    try:
        o = await asyncio.to_thread(commerce.add_logistics_event, order_id, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}



@router.get("/merchant/reviews")
async def merchant_reviews_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度评价列表（按绑定店铺隔离）。"""
    _, scope = await _merchant_scope(request)
    if shop_id:
        _require_shop_in_scope(shop_id, scope)
    return {"reviews": await asyncio.to_thread(commerce.merchant_reviews, scope, shop_id)}



@router.post("/merchant/upload")
async def merchant_upload_endpoint(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008  # FastAPI 依赖标记
    """商家上传图片（商品图 / 店铺图）：校验类型与大小，落盘后返回 /uploads/... URL。"""
    await _require_merchant(request)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"仅支持 {', '.join(sorted(_ALLOWED_EXTS))} 格式")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status_code=400, detail="图片不能超过 5MB")
    name = f"m{uuid.uuid4().hex[:12]}{ext}"
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.joinpath(name).write_bytes(data)
    return {"url": f"/uploads/{name}"}


# --------------------------------------------------------------------------- #
# 商家端：店铺商品管理（归属 = shop_plans 关联；status 控制店铺内上下架）
# 权限：shop_id 必须在商家绑定范围内（admin 不限），否则 403。
# --------------------------------------------------------------------------- #


@router.get("/merchant/plans")
async def merchant_plans_endpoint(shop_id: str, request: Request) -> dict[str, Any]:
    """商家视角：店铺关联方案列表（含在售/下架状态 shop_status）。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(shop_id, scope)
    return {"plans": await asyncio.to_thread(catalog_store.merchant_shop_plans, shop_id)}



@router.post("/merchant/plans")
async def merchant_create_plan_endpoint(
    req: PlanWriteRequest, shop_id: str, request: Request
) -> dict[str, Any]:
    """商家新建方案并挂到自家店铺（默认在售）。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(shop_id, scope)
    p = await asyncio.to_thread(
        catalog_store.merchant_create_plan, shop_id, req.model_dump(exclude_none=True)
    )
    return {"plan": p}



@router.put("/merchant/plans/{plan_id}")
async def merchant_update_plan_endpoint(
    plan_id: str, req: PlanWriteRequest, shop_id: str, request: Request
) -> dict[str, Any]:
    """商家更新自家店铺关联的方案（名称/价格/描述/图片等）。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(shop_id, scope)
    p = await asyncio.to_thread(
        catalog_store.merchant_update_plan, plan_id, shop_id, req.model_dump(exclude_none=True)
    )
    if not p:
        raise HTTPException(status_code=404, detail="方案不存在或不属于该店铺")
    return {"plan": p}



@router.post("/merchant/plans/{plan_id}/toggle")
async def merchant_toggle_plan_endpoint(
    plan_id: str, shop_id: str, request: Request
) -> dict[str, Any]:
    """上下架切换：翻转该店铺内 shop_plans.status。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(shop_id, scope)
    p = await asyncio.to_thread(catalog_store.merchant_toggle_plan, plan_id, shop_id)
    if not p:
        raise HTTPException(status_code=404, detail="方案不存在或不属于该店铺")
    return {"plan": p}



@router.delete("/merchant/plans/{plan_id}")
async def merchant_delete_plan_endpoint(
    plan_id: str, shop_id: str, request: Request
) -> dict[str, Any]:
    """商家下掉商品：解除店铺关联（无其他店关联则连方案删除）。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(shop_id, scope)
    if not await asyncio.to_thread(catalog_store.merchant_delete_plan, plan_id, shop_id):
        raise HTTPException(status_code=404, detail="方案不存在或不属于该店铺")
    return {"ok": True}



@router.put("/merchant/shop/{shop_id}")
async def merchant_update_shop_endpoint(
    shop_id: str, req: ShopWriteRequest, request: Request
) -> dict[str, Any]:
    """商家编辑店铺资料（店名/简介/价格区间/营业状态/店铺图片）。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(shop_id, scope)
    s = await asyncio.to_thread(
        catalog_store.update_shop, shop_id, req.model_dump(exclude_none=True)
    )
    if not s:
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"shop": s}


