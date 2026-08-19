"""routers/merchant.py —— 商家工作台（api.py 拆分，2026-08 重构）。

权限模型：仅 merchant 角色可访问（平台管理员走独立管理后台，2026-08 决策）；
数据按「商家-店铺绑定」隔离——商家只能查看/管理自己绑定店铺的订单、
评价、商品与店铺资料，未绑定则看不到任何店铺数据。
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
from storage import admin as admin_store
from storage import chats as chat_store
from storage import commerce, diy
from storage.db import get_conn

router = APIRouter(tags=["merchant"])
logger = logging.getLogger("api")

# 上传图片扩展名白名单（防任意文件落地）
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


async def _assert_order_in_scope(order_id: str, scope: list[str]) -> None:
    """校验订单属于商家绑定店铺范围，否则 403（防跨店越权 IDOR）。

    orders.shop_id 存的是下单时的商家名快照（与 shops.id 不一致），
    与 _shop_scope_sql 一致：按 shop_id 或订单明细里的店名匹配 scope。
    """
    if scope is None:  # admin 不受限
        return
    o = await asyncio.to_thread(commerce.get_order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not scope:
        raise HTTPException(status_code=403, detail="无权访问该订单")

    def _shop_names(ids: list[str]) -> set[str]:
        if not ids:
            return set()
        ph = ",".join("?" * len(ids))
        rows = get_conn().execute(
            f"SELECT name FROM shops WHERE id IN ({ph})", ids
        ).fetchall()
        return {r["name"] for r in rows}

    keys = set(scope) | await asyncio.to_thread(_shop_names, scope)
    o_shop = o.get("shop_id") or ""
    items_shop = {it.get("shop") for it in (o.get("items") or []) if it.get("shop")}
    if o_shop not in keys and not (items_shop & keys):
        raise HTTPException(status_code=403, detail="无权访问该订单")

@router.get("/merchant/stats")
async def merchant_stats_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度经营统计（订单 / GMV / 待发货 / 已完成 / 评价），按绑定店铺隔离。"""
    _, scope = await _merchant_scope(request)
    if shop_id:
        _require_shop_in_scope(shop_id, scope)
    return await asyncio.to_thread(commerce.merchant_stats, scope, shop_id)



@router.get("/merchant/shops")
async def merchant_shops_endpoint(request: Request) -> dict[str, Any]:
    """商家可管理的店铺列表（按 merchant_shops 绑定隔离）。"""
    uid, _scope = await _merchant_scope(request)
    shops = await asyncio.to_thread(catalog_store.merchant_shops, uid)
    return {"shops": shops}



@router.get("/merchant/orders")
async def merchant_orders_endpoint(
    request: Request,
    shop_id: str = "",
    status: str = "",
    limit: int = 50,
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    """商家视角订单列表（按绑定店铺隔离，可按店铺/状态/关键词/日期范围过滤）。"""
    _, scope = await _merchant_scope(request)
    if shop_id:
        _require_shop_in_scope(shop_id, scope)
    return {
        "orders": await asyncio.to_thread(
            commerce.merchant_orders, scope, shop_id, status, limit, keyword, date_from, date_to
        )
    }



@router.get("/merchant/orders/{order_id}")
async def merchant_order_detail_endpoint(order_id: str, request: Request) -> dict[str, Any]:
    """商家视角订单详情：附带 DIY 方案制作卡（花材配比/包装/步骤/卡片留言）。

    商家按单备货的唯一数据源：订单的 plan_id 关联 diy_plans，返回完整制作信息；
    非 DIY 方案（目录商品）不附带 plan 字段。
    """
    _, scope = await _merchant_scope(request)
    await _assert_order_in_scope(order_id, scope)
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
    _, scope = await _merchant_scope(request)
    await _assert_order_in_scope(order_id, scope)
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
    _, scope = await _merchant_scope(request)
    await _assert_order_in_scope(order_id, scope)
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


class BatchToggleRequest(BaseModel):
    shop_id: str = Field(..., min_length=1, max_length=40)
    plan_ids: list[str] = Field(..., min_length=1, max_length=200)
    on: bool = Field(True, description="True=上架，False=下架")


@router.post("/merchant/plans/batch-toggle")
async def merchant_batch_toggle_endpoint(req: BatchToggleRequest, request: Request) -> dict[str, Any]:
    """批量上下架：一次性设置多家商品为 on/off（省去逐条点击）。"""
    _, scope = await _merchant_scope(request)
    _require_shop_in_scope(req.shop_id, scope)
    n = await asyncio.to_thread(
        catalog_store.merchant_batch_toggle_plans, req.shop_id, req.plan_ids, req.on
    )
    return {"updated": n}



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


class CategoryWriteRequest(BaseModel):
    """分类新增/改名请求体。"""

    name: str = Field(..., min_length=1, max_length=20)


@router.get("/merchant/categories")
async def merchant_categories_endpoint(request: Request) -> dict[str, Any]:
    """商品分类列表（含挂靠商品数，供分类管理 / 商品表单下拉）。"""
    await _require_merchant(request)
    return {"categories": await asyncio.to_thread(catalog_store.list_categories)}


@router.post("/merchant/categories")
async def merchant_create_category_endpoint(
    req: CategoryWriteRequest, request: Request
) -> dict[str, Any]:
    """新增分类。"""
    await _require_merchant(request)
    c = await asyncio.to_thread(catalog_store.create_category, req.name)
    if not c:
        raise HTTPException(status_code=400, detail="分类名不能为空或已存在")
    return {"category": c}


@router.put("/merchant/categories/{cat_id}")
async def merchant_rename_category_endpoint(
    cat_id: str, req: CategoryWriteRequest, request: Request
) -> dict[str, Any]:
    """分类改名。"""
    await _require_merchant(request)
    c = await asyncio.to_thread(catalog_store.rename_category, cat_id, req.name)
    if not c:
        raise HTTPException(status_code=400, detail="分类不存在或名称重复")
    return {"category": c}


@router.delete("/merchant/categories/{cat_id}")
async def merchant_delete_category_endpoint(cat_id: str, request: Request) -> dict[str, Any]:
    """删除分类（挂靠商品自动回落到默认分类）。"""
    await _require_merchant(request)
    if not await asyncio.to_thread(catalog_store.delete_category, cat_id):
        raise HTTPException(status_code=404, detail="分类不存在")
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


class ChatSendRequest(BaseModel):
    """商家发送会话消息请求体。"""

    content: str = Field(..., min_length=1, max_length=1000, description="消息内容")


class ChatWithUserRequest(BaseModel):
    """商家发起与某顾客的会话请求体。"""

    user_id: str = Field(..., min_length=1, max_length=64, description="顾客用户 ID")
    shop_id: str = Field(..., min_length=1, max_length=64, description="店铺 ID")


class ReviewReplyRequest(BaseModel):
    """评价回复请求体。"""

    reply: str = Field(..., min_length=1, max_length=500, description="回复内容")


@router.get("/merchant/chats")
async def merchant_chats_endpoint(request: Request) -> dict[str, Any]:
    """商家会话列表（按绑定店铺隔离，附顾客昵称/头像/店铺名与未读数）。"""
    _, scope = await _merchant_scope(request)
    return {"chats": await asyncio.to_thread(chat_store.list_merchant_chats, scope)}


@router.get("/merchant/chats/{chat_id}/messages")
async def merchant_chat_messages_endpoint(chat_id: str, request: Request) -> dict[str, Any]:
    """商家读取会话消息（读取即清零商家侧未读），校验会话店铺在商家范围内。"""
    _, scope = await _merchant_scope(request)
    chat = await asyncio.to_thread(chat_store.get_chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="会话不存在")
    if scope is not None and chat["shop_id"] not in scope:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    messages = await asyncio.to_thread(
        chat_store.list_messages, chat_id, chat_store.SENDER_MERCHANT
    )
    return {"chat": chat, "messages": messages}


@router.post("/merchant/chats/{chat_id}/messages")
async def merchant_send_message_endpoint(
    chat_id: str, req: ChatSendRequest, request: Request
) -> dict[str, Any]:
    """商家发送消息（顾客未读 +1）。"""
    _, scope = await _merchant_scope(request)
    chat = await asyncio.to_thread(chat_store.get_chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="会话不存在")
    if scope is not None and chat["shop_id"] not in scope:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    message = await asyncio.to_thread(
        chat_store.send_message, chat_id, chat_store.SENDER_MERCHANT, req.content.strip()
    )
    return {"message": message}


@router.post("/merchant/chats/with-user")
async def merchant_chat_with_user_endpoint(
    req: ChatWithUserRequest, request: Request
) -> dict[str, Any]:
    """商家发起与某顾客的会话（不存在则创建），返回会话 + 最近消息。"""
    _, scope = await _merchant_scope(request)
    if scope is not None and req.shop_id not in scope:
        raise HTTPException(status_code=403, detail="无权操作该店铺")
    chat = await asyncio.to_thread(
        chat_store.get_or_create_chat, req.shop_id, req.user_id
    )
    messages = await asyncio.to_thread(
        chat_store.list_messages, chat["id"], chat_store.SENDER_MERCHANT
    )
    return {"chat": chat, "messages": messages}


@router.post("/merchant/reviews/{review_id}/reply")
async def merchant_review_reply_endpoint(
    review_id: str, req: ReviewReplyRequest, request: Request
) -> dict[str, Any]:
    """商家回复评价（写 reply/reply_at；评价须属于商家范围内店铺的订单）。"""
    _, scope = await _merchant_scope(request)
    review = await asyncio.to_thread(commerce.merchant_review_get, review_id, scope)
    if not review:
        raise HTTPException(status_code=404, detail="评价不存在或不属于你的店铺")
    updated = await asyncio.to_thread(chat_store.reply_review, review_id, req.reply)
    return {"review": updated}


class MerchantApplyRequest(BaseModel):
    """商家入驻申请请求体（M5，登录即可提交，角色不限 user）。"""

    shop_name: str = Field(..., min_length=1, max_length=40)
    contact_name: str = Field("", max_length=30)
    contact_phone: str = Field("", max_length=20)
    license_no: str = Field("", max_length=40)
    license_img: str = Field("", max_length=200)
    address: str = Field("", max_length=120)
    intro: str = Field("", max_length=200)


@router.post("/merchant/apply")
async def merchant_apply_endpoint(req: MerchantApplyRequest, request: Request) -> dict[str, Any]:
    """提交商家入驻申请（管理员在后台审核，通过后提权并建店）。"""
    uid = await resolve_uid(request, None)
    try:
        app = await asyncio.to_thread(
            admin_store.create_application,
            uid, req.shop_name, req.contact_name, req.contact_phone,
            req.license_no, req.license_img, req.address, req.intro,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"application": app}


@router.get("/me/merchant-application")
async def my_merchant_application_endpoint(request: Request) -> dict[str, Any]:
    """我的入驻申请（倒序，前端展示审核进度）。"""
    uid = await resolve_uid(request, None)
    rows = get_conn().execute(
        "SELECT * FROM merchant_applications WHERE applicant_user_id=? ORDER BY created_at DESC",
        (uid,),
    ).fetchall()
    return {"applications": [dict(r) for r in rows]}


