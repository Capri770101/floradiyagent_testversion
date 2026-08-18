"""routers/commerce.py —— 购物车/订单/支付/评价/券/地址/收藏（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from config import settings
from routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    AddressPatchRequest,
    AddressWriteRequest,
    CartAddRequest,
    CartMergeRequest,
    CartUpdateRequest,
    FavoriteRequest,
    OrderActionRequest,
    OrderCreateRequest,
    OrderPatchRequest,
    PayRequest,
    ReviewRequest,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)
from storage import admin as admin_store
from storage import commerce
from storage import payment as payment_module

router = APIRouter(tags=["commerce"])
logger = logging.getLogger("api")

@router.get("/cart")
async def get_cart(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查看某用户购物车。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    items = await asyncio.to_thread(commerce.list_cart, uid)
    return {"items": items}



@router.post("/cart")
async def post_cart(req: CartAddRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, req.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    item = await asyncio.to_thread(
        commerce.add_to_cart, uid, req.plan_id, req.name, req.price, req.shop
    )
    return {"item": item}



@router.post("/cart/merge")
async def merge_cart_endpoint(req: CartMergeRequest, request: Request) -> dict[str, Any]:
    """游客购物车合并：登录后把匿名 uid 的购物车并入当前账号（同方案数量相加）。

    to 用户以令牌身份为准（resolve_uid 忽略请求体 user_id），杜绝越权合并他人购物车。
    """
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    if not req.from_user_id or req.from_user_id == uid:
        items = await asyncio.to_thread(commerce.list_cart, uid)
        return {"merged": 0, "items": items}
    merged = await asyncio.to_thread(commerce.merge_cart, req.from_user_id, uid)
    items = await asyncio.to_thread(commerce.list_cart, uid)
    return {"merged": merged, "items": items}



@router.put("/cart/{item_id}")
async def put_cart(item_id: str, req: CartUpdateRequest) -> dict[str, Any]:
    item = await asyncio.to_thread(commerce.update_cart_item, item_id, req.qty, req.selected)
    if not item:
        raise HTTPException(status_code=404, detail="购物车项不存在")
    return {"item": item}



@router.delete("/cart/{item_id}")
async def del_cart(item_id: str) -> dict[str, Any]:
    ok = await asyncio.to_thread(commerce.remove_cart_item, item_id)
    return {"ok": ok}



@router.post("/orders")
async def post_order(req: OrderCreateRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, req.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    try:
        order = await asyncio.to_thread(
            commerce.create_order,
            uid,
            [it.model_dump() for it in req.items],
            req.recipient,
            req.delivery,
            req.note,
            req.address_id,
        )
    except ValueError as exc:
        # 方案不存在/已下架（服务端取价失败）→ 400，绝不信客户端价格
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"order": order}



@router.get("/orders")
async def list_orders_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出某用户全部订单（新→旧，含物流时间线）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    orders = await asyncio.to_thread(commerce.list_orders, uid)
    return {"orders": orders}



@router.get("/coupons")
async def list_coupons_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出用户优惠券（新用户自动发放新人立减券）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    coupons = await asyncio.to_thread(commerce.list_coupons, uid)
    return {"coupons": coupons}



@router.get("/points")
async def points_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查询用户积分余额与流水。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    points = await asyncio.to_thread(commerce.get_points, uid)
    return points


# --------------------------------------------------------------------------- #
# 领券中心 / 积分商城
# --------------------------------------------------------------------------- #



@router.get("/coupon-offers")
async def list_coupon_offers_endpoint(
    request: Request, user_id: str | None = None
) -> dict[str, Any]:
    """上架中的券模板（登录后附带每人限领状态 claimed；未登录同样可浏览）。"""
    uid = None
    try:
        uid = await resolve_uid(request, user_id)
    except HTTPException:
        uid = None
    offers = await asyncio.to_thread(commerce.list_coupon_offers, uid or "")
    return {"offers": offers}



@router.post("/coupon-offers/{offer_id}/claim")
async def claim_coupon_offer_endpoint(offer_id: str, request: Request) -> dict[str, Any]:
    """领取 / 积分兑换一张券（points_cost=0 免费领；>0 扣积分）。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    try:
        coupon = await asyncio.to_thread(commerce.claim_coupon_offer, uid, offer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"coupon": coupon}


# --------------------------------------------------------------------------- #
# 收货地址
# --------------------------------------------------------------------------- #



@router.get("/addresses")
async def list_addresses_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出用户收货地址（默认排前）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    return {"addresses": await asyncio.to_thread(commerce.list_addresses, uid)}



@router.post("/addresses")
async def post_address(req: AddressWriteRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    a = await asyncio.to_thread(
        commerce.add_address, uid, req.name, req.phone, req.address, req.is_default
    )
    return {"address": a}



@router.put("/addresses/{addr_id}")
async def put_address(addr_id: str, req: AddressPatchRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    a = await asyncio.to_thread(
        commerce.update_address, addr_id, uid, req.name, req.phone, req.address, req.is_default
    )
    if not a:
        raise HTTPException(status_code=404, detail="地址不存在")
    return {"address": a}



@router.delete("/addresses/{addr_id}")
async def del_address(addr_id: str, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    if not await asyncio.to_thread(commerce.delete_address, addr_id, uid):
        raise HTTPException(status_code=404, detail="地址不存在")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 收藏
# --------------------------------------------------------------------------- #



@router.get("/favorites")
async def list_favorites_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出收藏（含方案信息，新→旧）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    items = await asyncio.to_thread(commerce.list_favorites, uid)
    return {"favorites": items, "count": len(items)}



@router.post("/favorites")
async def post_favorite(req: FavoriteRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    await asyncio.to_thread(commerce.add_favorite, uid, req.plan_id)
    return {"ok": True, "favorited": True}



@router.delete("/favorites/{plan_id}")
async def del_favorite(plan_id: str, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    await asyncio.to_thread(commerce.remove_favorite, uid, plan_id)
    return {"ok": True, "favorited": False}



@router.get("/favorites/{plan_id}/status")
async def favorite_status(plan_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查询某方案是否已收藏（商品详情页心形按钮状态）。

    未登录视为未收藏（返回 favorited=false），避免详情页未登录时刷 401 噪音。
    """
    uid = await resolve_uid(request, user_id)
    if not uid:
        return {"plan_id": plan_id, "favorited": False}
    return {"plan_id": plan_id, "favorited": await asyncio.to_thread(commerce.is_favorite, uid, plan_id)}


# --------------------------------------------------------------------------- #
# 商家端（店铺维度经营数据 / 代发货）
# 权限：仅 merchant / admin 角色可访问（users.role 字段）。
# --------------------------------------------------------------------------- #



@router.get("/orders/{order_id}")
async def get_order_endpoint(order_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    uid = await resolve_uid(request, user_id)
    await _assert_order_owner(order_id, uid)
    o = await asyncio.to_thread(commerce.get_order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}



@router.patch("/orders/{order_id}")
async def patch_order(order_id: str, req: OrderPatchRequest, request: Request) -> dict[str, Any]:
    """更新订单收货信息（收货人 / 配送时间 / 备注），仅订单主人可改，且只能改传入字段。"""
    uid = await resolve_uid(request, None)
    await _assert_order_owner(order_id, uid)
    o = await asyncio.to_thread(
        commerce.update_order, order_id, req.recipient, req.delivery, req.note
    )
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}



@router.post("/orders/{order_id}/action")
async def order_action_endpoint(
    order_id: str, req: OrderActionRequest, request: Request
) -> dict[str, Any]:
    """订单状态流转（物流模拟）：发货 / 签收 / 取消，仅订单主人可操作。"""
    uid = await resolve_uid(request, None)
    await _assert_order_owner(order_id, uid)
    try:
        if req.action == "ship":
            o = await asyncio.to_thread(commerce.ship_order, order_id)
        elif req.action == "complete":
            o = await asyncio.to_thread(commerce.complete_order, order_id)
        else:
            o = await asyncio.to_thread(commerce.cancel_order, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}


class AftersaleCreateRequest(BaseModel):
    """用户发起售后请求体。"""

    type: str = Field("refund", description="refund|return|exchange")
    reason: str = Field("", max_length=200)
    description: str = Field("", max_length=1000)
    evidence_imgs: list[str] = Field(default_factory=list)


@router.post("/orders/{order_id}/aftersale")
async def create_aftersale_endpoint(
    order_id: str, req: AftersaleCreateRequest, request: Request
) -> dict[str, Any]:
    """用户对自己已支付订单发起售后（退款/退货/换货）。"""
    uid = await resolve_uid(request, None)
    await _assert_order_owner(order_id, uid)
    try:
        a = await asyncio.to_thread(
            admin_store.create_aftersale,
            order_id, uid, req.type, req.reason, req.description, req.evidence_imgs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"aftersale": a}


@router.get("/orders/{order_id}/aftersales")
async def order_aftersales_endpoint(order_id: str, request: Request) -> dict[str, Any]:
    """该订单的售后单列表（本人可见）。"""
    uid = await resolve_uid(request, None)
    await _assert_order_owner(order_id, uid)
    from storage.db import get_conn

    rows = get_conn().execute(
        "SELECT * FROM aftersales WHERE order_id=? ORDER BY created_at DESC", (order_id,)
    ).fetchall()
    return {"aftersales": [dict(r) for r in rows]}


@router.get("/me/aftersales")
async def my_aftersales_endpoint(request: Request) -> dict[str, Any]:
    """我的售后单列表。"""
    uid = await resolve_uid(request, None)
    return {"aftersales": await asyncio.to_thread(admin_store.list_user_aftersales, uid)}



@router.post("/pay")
async def pay_endpoint(req: PayRequest, request: Request) -> dict[str, Any]:
    """发起支付：按配置渠道（默认 sandbox）调统一下单，返回前端拉起支付所需参数。

    微信返回 ``pay.pay_params`` 即 ``wx.requestPayment`` 入参；支付宝返回 ``pay_params.pay_url``
    供前端跳转。真实网关返回的 ``paid`` 为 False，待 ``/pay/notify/{provider}`` 回调确认。
    """
    uid = await resolve_uid(request, None)
    await _assert_order_owner(req.order_id, uid)
    extra = {}
    if req.openid:
        extra["openid"] = req.openid
    if req.description:
        extra["description"] = req.description
    try:
        result = await asyncio.to_thread(commerce.pay_order, req.order_id, req.method, extra)
    except ValueError as exc:
        # 状态机保护（如订单已取消 / 超时未支付）与业务校验
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except payment_module.PaymentConfigError as exc:
        # 真实渠道凭据未配置：明确 400，避免「半成品」上线
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except payment_module.PaymentGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"pay": result}



@router.post("/pay/notify/{provider}")
async def pay_notify(provider: str, request: Request) -> Response:
    """支付回调（微信 v3 / 支付宝）。验签解密通过后标记订单已支付。

    微信期望返回 ``200 + {"code":"SUCCESS","message":"成功"}``；支付宝期望返回纯文本 ``success``。
    验签失败返回渠道约定的「重试」响应（微信 FAIL / 支付宝 failure）。
    """
    try:
        prov = payment_module.get_provider(provider)
    except payment_module.PaymentConfigError as exc:
        logger.warning("[pay/notify] 渠道未配置: %s", exc)
        if provider == "alipay":
            return Response(content="failure", media_type="text/plain")
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": str(exc)})

    body = await request.body()
    headers = dict(request.headers)
    try:
        result = await asyncio.to_thread(prov.verify_notify, body, headers)
    except Exception as exc:  # noqa: BLE001
        # 服务端处理异常（区别于验签不通过）：显式记录并返回 500 让渠道重试，
        # 不误当「验签失败」吞掉掩盖问题
        logger.error("[pay/notify] 验签处理异常 provider=%s: %r", provider, exc)
        if provider == "alipay":
            return Response(content="failure", media_type="text/plain")
        return JSONResponse(status_code=500, content={"code": "FAIL", "message": "回调处理异常"})

    if not result or not getattr(result, "paid", False):
        # 验签不通过：要求渠道重试（不标记订单）
        if provider == "alipay":
            return Response(content="failure", media_type="text/plain")
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "验签失败"})

    await asyncio.to_thread(commerce.mark_order_paid, result.order_id, result.transaction_id)
    # 返回渠道约定的成功响应
    if provider == "alipay":
        return Response(content="success", media_type="text/plain")
    return JSONResponse(content={"code": "SUCCESS", "message": "成功"})



@router.get("/pay/{order_id}/status")
async def pay_status(order_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查询订单支付状态（客户端轮询兜底，用于回调不可达场景）。"""
    uid = await resolve_uid(request, user_id)
    await _assert_order_owner(order_id, uid)
    st = await asyncio.to_thread(commerce.get_payment_status, order_id)
    if not st:
        raise HTTPException(status_code=404, detail="订单不存在")
    return st


# --------------------------------------------------------------------------- #
# 评价
# --------------------------------------------------------------------------- #



@router.post("/reviews")
async def post_review(req: ReviewRequest, request: Request) -> dict[str, Any]:
    """订单完成后写评价：仅订单主人 + 已签收订单；同单重复评价即更新。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    try:
        rev = await asyncio.to_thread(commerce.create_review, uid, req.order_id, req.rating, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"review": rev}



@router.get("/reviews")
async def list_reviews_endpoint(plan_id: str = "") -> dict[str, Any]:
    """公开查询方案评价列表（商品详情页展示）。"""
    return {"reviews": await asyncio.to_thread(commerce.list_reviews, plan_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host=settings.api_host, port=settings.api_port, reload=settings.debug, log_level=settings.log_level.lower())
