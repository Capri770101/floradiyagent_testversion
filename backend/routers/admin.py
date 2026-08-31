"""routers/admin.py —— 管理后台（api.py 拆分，2026-08 重构）。

覆盖：M1 目录 CRUD（已有）+ M0 提权 / M2 用户管理 / M3 全局订单 /
M4 售后审核 / M5 商家入驻审核。全部端点 `_require_admin` 守护。
"""
from __future__ import annotations

import logging
from typing import Any

from backend.routers.common import PlanWriteRequest, ShopWriteRequest, _require_admin, catalog_store
from backend.storage import admin as admin_store
from backend.storage import config as config_store
from backend.storage import payment as payment_module
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=['admin'])
logger = logging.getLogger('api')

@router.get('/admin/plans')
async def admin_list_plans(request: Request) -> dict[str, Any]:
    """后台管理列表：返回全字段方案（含 style/category_id）。"""
    await _require_admin(request)
    return {'plans': await catalog_store.list_plans()}

@router.post('/admin/plans')
async def admin_create_plan(req: PlanWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    p = await catalog_store.create_plan(req.model_dump(exclude_none=True))
    return {'plan': p}

@router.put('/admin/plans/{plan_id}')
async def admin_update_plan(plan_id: str, req: PlanWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    p = await catalog_store.update_plan(plan_id, req.model_dump(exclude_none=True))
    if not p:
        raise HTTPException(status_code=404, detail='方案不存在')
    return {'plan': p}

@router.delete('/admin/plans/{plan_id}')
async def admin_delete_plan(plan_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await catalog_store.delete_plan(plan_id):
        raise HTTPException(status_code=404, detail='方案不存在')
    return {'ok': True}

@router.get('/admin/shops')
async def admin_list_shops(request: Request) -> dict[str, Any]:
    """后台管理列表：返回全字段店铺（含 plan_ids 关联）。"""
    await _require_admin(request)
    return {'shops': await catalog_store.list_shops()}

@router.post('/admin/shops')
async def admin_create_shop(req: ShopWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    s = await catalog_store.create_shop(req.model_dump(exclude_none=True))
    return {'shop': s}

@router.put('/admin/shops/{shop_id}')
async def admin_update_shop(shop_id: str, req: ShopWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    s = await catalog_store.update_shop(shop_id, req.model_dump(exclude_none=True))
    if not s:
        raise HTTPException(status_code=404, detail='店铺不存在')
    return {'shop': s}

@router.delete('/admin/shops/{shop_id}')
async def admin_delete_shop(shop_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await catalog_store.delete_shop(shop_id):
        raise HTTPException(status_code=404, detail='店铺不存在')
    return {'ok': True}

class RoleWriteRequest(BaseModel):
    role: str = Field(..., description='user | merchant | admin')

class StatusWriteRequest(BaseModel):
    status: str = Field(..., description='active | banned')

@router.get('/admin/users')
async def admin_list_users(request: Request, keyword: str='', role: str='', status: str='', limit: int=Query(50, ge=1, le=200), offset: int=Query(0, ge=0)) -> dict[str, Any]:
    """用户列表：关键词/角色/状态筛选 + 分页。"""
    await _require_admin(request)
    users, total = await admin_store.list_users(keyword, role, status, limit, offset)
    return {'users': users, 'total': total, 'limit': limit, 'offset': offset}

@router.get('/admin/users/{user_id}')
async def admin_get_user(user_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    u = await admin_store.get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail='用户不存在')
    return {'user': u}

@router.post('/admin/users/{user_id}/role')
async def admin_set_user_role(user_id: str, req: RoleWriteRequest, request: Request) -> dict[str, Any]:
    """提权/降权（user|merchant|admin）。"""
    await _require_admin(request)
    try:
        ok = await admin_store.set_user_role(user_id, req.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail='用户不存在')
    return {'ok': True, 'user_id': user_id, 'role': req.role}

@router.post('/admin/users/{user_id}/ban')
async def admin_ban_user(user_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await admin_store.set_user_status(user_id, 'banned'):
        raise HTTPException(status_code=404, detail='用户不存在')
    return {'ok': True, 'user_id': user_id, 'status': 'banned'}

@router.post('/admin/users/{user_id}/unban')
async def admin_unban_user(user_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await admin_store.set_user_status(user_id, 'active'):
        raise HTTPException(status_code=404, detail='用户不存在')
    return {'ok': True, 'user_id': user_id, 'status': 'active'}

class OrderStatusWriteRequest(BaseModel):
    status: str = Field(..., description='created|paid|shipped|done|canceled')

@router.get('/admin/orders')
async def admin_list_orders(request: Request, status: str='', user_id: str='', shop_id: str='', keyword: str='', date_from: str='', date_to: str='', limit: int=Query(50, ge=1, le=200), offset: int=Query(0, ge=0)) -> dict[str, Any]:
    """全平台订单：状态/用户/店铺/关键词/日期筛选 + 分页。"""
    await _require_admin(request)
    ids, total = await admin_store.list_all_orders(status, user_id, shop_id, keyword, date_from, date_to, limit, offset)
    from backend.storage import commerce
    orders = [await commerce.get_order(oid) for oid in ids]
    orders = [o for o in orders if o]
    return {'orders': orders, 'total': total, 'limit': limit, 'offset': offset}

@router.get('/admin/orders/{order_id}')
async def admin_get_order(order_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    from backend.storage import commerce
    o = await commerce.get_order(order_id)
    if not o:
        raise HTTPException(status_code=404, detail='订单不存在')
    return {'order': o}

@router.post('/admin/orders/{order_id}/status')
async def admin_set_order_status(order_id: str, req: OrderStatusWriteRequest, request: Request) -> dict[str, Any]:
    """管理员干预订单状态（绕过用户/商家流程直接落库）。"""
    await _require_admin(request)
    if req.status not in ('created', 'paid', 'shipped', 'done', 'canceled'):
        raise HTTPException(status_code=400, detail='非法订单状态')
    o = await admin_store.set_order_status(order_id, req.status)
    if not o:
        raise HTTPException(status_code=404, detail='订单不存在')
    return {'order': o}

class AftersaleRejectRequest(BaseModel):
    note: str = Field('', max_length=500, description='拒绝原因')

class AftersaleRefundRequest(BaseModel):
    refund_amount: float | None = Field(None, ge=0, description='退款金额，缺省用订单实付')

@router.get('/admin/aftersales')
async def admin_list_aftersales(request: Request, status: str='', limit: int=Query(50, ge=1, le=200), offset: int=Query(0, ge=0)) -> dict[str, Any]:
    await _require_admin(request)
    items, total = await admin_store.list_aftersales(status, limit, offset)
    return {'aftersales': items, 'total': total, 'limit': limit, 'offset': offset}

@router.get('/admin/aftersales/{as_id}')
async def admin_get_aftersale(as_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    a = await admin_store.get_aftersale(as_id)
    if not a:
        raise HTTPException(status_code=404, detail='售后单不存在')
    return {'aftersale': a}

@router.post('/admin/aftersales/{as_id}/approve')
async def admin_approve_aftersale(as_id: str, request: Request) -> dict[str, Any]:
    admin_uid = await _require_admin(request)
    a = await admin_store.approve_aftersale(as_id, admin_uid)
    if not a:
        raise HTTPException(status_code=404, detail='售后单不存在')
    return {'aftersale': a}

@router.post('/admin/aftersales/{as_id}/reject')
async def admin_reject_aftersale(as_id: str, req: AftersaleRejectRequest, request: Request) -> dict[str, Any]:
    admin_uid = await _require_admin(request)
    a = await admin_store.reject_aftersale(as_id, admin_uid, req.note)
    if not a:
        raise HTTPException(status_code=404, detail='售后单不存在')
    return {'aftersale': a}

@router.post('/admin/aftersales/{as_id}/refund')
async def admin_refund_aftersale(as_id: str, request: Request, req: AftersaleRefundRequest | None=None) -> dict[str, Any]:
    """通过并退款：真实网关按订单原路退款（微信 v2 / 支付宝），沙箱为模拟，落库支付记录。"""
    from backend.storage import commerce
    admin_uid = await _require_admin(request)
    a = await admin_store.get_aftersale(as_id)
    if not a:
        raise HTTPException(status_code=404, detail='售后单不存在')
    amount = req.refund_amount if req else None
    try:
        refund = await commerce.refund_order(a['order_id'], amount, '售后审核通过，原路退款')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except payment_module.PaymentConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except payment_module.PaymentGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if refund is None:
        raise HTTPException(status_code=404, detail='订单不存在')
    a2 = await admin_store.refund_aftersale(as_id, admin_uid, amount)
    if not a2:
        raise HTTPException(status_code=404, detail='售后单不存在')
    a2['refund'] = refund
    return {'aftersale': a2}

# ---------------- 商家提现审核 ----------------

class WithdrawalActRequest(BaseModel):
    note: str = Field('', max_length=500, description='审核备注 / 打款凭证号')

@router.get('/admin/withdrawals')
async def admin_list_withdrawals(request: Request, status: str='', limit: int=Query(50, ge=1, le=200), offset: int=Query(0, ge=0)) -> dict[str, Any]:
    """提现申请列表（可按状态筛选）。"""
    await _require_admin(request)
    items, total = await admin_store.list_withdrawals(status, limit, offset)
    return {'withdrawals': items, 'total': total, 'limit': limit, 'offset': offset}

@router.post('/admin/withdrawals/{wd_id}/approve')
async def admin_approve_withdrawal(wd_id: str, request: Request) -> dict[str, Any]:
    """通过提现申请（待线下打款）。"""
    admin_uid = await _require_admin(request)
    w = await admin_store.update_withdrawal(wd_id, 'approved', admin_uid)
    if not w:
        raise HTTPException(status_code=404, detail='提现单不存在')
    return {'withdrawal': w}

@router.post('/admin/withdrawals/{wd_id}/paid')
async def admin_pay_withdrawal(wd_id: str, req: WithdrawalActRequest, request: Request) -> dict[str, Any]:
    """标记已打款（线下完成转账后登记凭证号）。"""
    admin_uid = await _require_admin(request)
    w = await admin_store.update_withdrawal(wd_id, 'paid', admin_uid, req.note)
    if not w:
        raise HTTPException(status_code=404, detail='提现单不存在')
    return {'withdrawal': w}

@router.post('/admin/withdrawals/{wd_id}/reject')
async def admin_reject_withdrawal(wd_id: str, req: WithdrawalActRequest, request: Request) -> dict[str, Any]:
    """拒绝提现申请。"""
    admin_uid = await _require_admin(request)
    w = await admin_store.update_withdrawal(wd_id, 'rejected', admin_uid, req.note)
    if not w:
        raise HTTPException(status_code=404, detail='提现单不存在')
    return {'withdrawal': w}

class ApplyRejectRequest(BaseModel):
    note: str = Field('', max_length=500, description='拒绝原因')

@router.get('/admin/merchant-applications')
async def admin_list_applications(request: Request, status: str='', limit: int=Query(50, ge=1, le=200), offset: int=Query(0, ge=0)) -> dict[str, Any]:
    await _require_admin(request)
    items, total = await admin_store.list_applications(status, limit, offset)
    return {'applications': items, 'total': total, 'limit': limit, 'offset': offset}

@router.get('/admin/merchant-applications/{app_id}')
async def admin_get_application(app_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    a = await admin_store.get_application(app_id)
    if not a:
        raise HTTPException(status_code=404, detail='申请不存在')
    return {'application': a}

@router.post('/admin/merchant-applications/{app_id}/approve')
async def admin_approve_application(app_id: str, request: Request) -> dict[str, Any]:
    """通过：申请人提权 merchant + 创建店铺 + 绑定 merchant_shops。"""
    admin_uid = await _require_admin(request)
    try:
        a = await admin_store.approve_application(app_id, admin_uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not a:
        raise HTTPException(status_code=404, detail='申请不存在')
    return {'application': a}

@router.post('/admin/merchant-applications/{app_id}/reject')
async def admin_reject_application(app_id: str, req: ApplyRejectRequest, request: Request) -> dict[str, Any]:
    admin_uid = await _require_admin(request)
    a = await admin_store.reject_application(app_id, admin_uid, req.note)
    if not a:
        raise HTTPException(status_code=404, detail='申请不存在')
    return {'application': a}

@router.get('/admin/merchants')
async def admin_list_merchants(request: Request) -> dict[str, Any]:
    """已入驻商家（merchant 角色 + 绑定店铺）。"""
    await _require_admin(request)
    return {'merchants': await admin_store.list_merchants()}

@router.get('/admin/reviews')
async def admin_list_reviews(request: Request, status: str='', keyword: str='', limit: int=Query(50, ge=1, le=200), offset: int=Query(0, ge=0)) -> dict[str, Any]:
    """全平台评价列表（含已隐藏，可按状态/关键词筛选）。"""
    await _require_admin(request)
    reviews, total = await admin_store.list_reviews(status, keyword, limit, offset)
    return {'reviews': reviews, 'total': total, 'limit': limit, 'offset': offset}

@router.post('/admin/reviews/{review_id}/hide')
async def admin_hide_review(review_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await admin_store.set_review_status(review_id, 'hidden'):
        raise HTTPException(status_code=404, detail='评价不存在')
    return {'ok': True, 'review_id': review_id, 'status': 'hidden'}

@router.post('/admin/reviews/{review_id}/show')
async def admin_show_review(review_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await admin_store.set_review_status(review_id, 'visible'):
        raise HTTPException(status_code=404, detail='评价不存在')
    return {'ok': True, 'review_id': review_id, 'status': 'visible'}

@router.delete('/admin/reviews/{review_id}')
async def admin_delete_review(review_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await admin_store.delete_review(review_id):
        raise HTTPException(status_code=404, detail='评价不存在')
    return {'ok': True}

@router.get('/admin/dashboard')
async def admin_dashboard(request: Request, days: int=Query(7, ge=1, le=90)) -> dict[str, Any]:
    """平台数据看板（GMV/订单/用户/热销/趋势）。"""
    await _require_admin(request)
    return await admin_store.dashboard_stats(days)

class OperationsWriteRequest(BaseModel):
    """运营配置整体写请求（仅更新传入字段）。"""
    delivery_options: list[str] | None = None
    shipping_fee: float | None = Field(None, ge=0)
    coupon_rules: dict[str, Any] | None = None
    recommend_weights: dict[str, float] | None = None

@router.get('/admin/config')
async def admin_get_config(request: Request) -> dict[str, Any]:
    await _require_admin(request)
    return await config_store.admin_config()

@router.put('/admin/config')
async def admin_put_config(req: OperationsWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    try:
        data = await config_store.update_operations(req.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return data

class FaqsWriteRequest(BaseModel):
    faqs: list[dict[str, Any]] = Field(default_factory=list)

@router.get('/admin/content/faqs')
async def admin_get_faqs(request: Request) -> dict[str, Any]:
    await _require_admin(request)
    return {'faqs': await config_store.get_config(config_store.K_FAQS, config_store.DEFAULTS[config_store.K_FAQS])}

@router.put('/admin/content/faqs')
async def admin_put_faqs(req: FaqsWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    return {'faqs': await config_store.update_faqs(req.faqs)}

class AnnouncementsWriteRequest(BaseModel):
    announcements: list[dict[str, Any]] = Field(default_factory=list)

@router.get('/admin/content/announcements')
async def admin_get_announcements(request: Request) -> dict[str, Any]:
    await _require_admin(request)
    return {'announcements': await config_store.get_config(config_store.K_ANNOUNCE, config_store.DEFAULTS[config_store.K_ANNOUNCE])}

@router.put('/admin/content/announcements')
async def admin_put_announcements(req: AnnouncementsWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    return {'announcements': await config_store.update_announcements(req.announcements)}

@router.get('/admin/categories')
async def admin_list_categories(request: Request) -> dict[str, Any]:
    await _require_admin(request)
    return {'categories': await catalog_store.list_categories()}

class CategoryWriteRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)

@router.post('/admin/categories')
async def admin_create_category(req: CategoryWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    c = await catalog_store.create_category(req.name)
    if not c:
        raise HTTPException(status_code=400, detail='分类名不能为空或已存在')
    return {'category': c}

@router.put('/admin/categories/{cat_id}')
async def admin_rename_category(cat_id: str, req: CategoryWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    c = await catalog_store.rename_category(cat_id, req.name)
    if not c:
        raise HTTPException(status_code=400, detail='分类不存在或名称重复')
    return {'category': c}

@router.delete('/admin/categories/{cat_id}')
async def admin_delete_category(cat_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await catalog_store.delete_category(cat_id):
        raise HTTPException(status_code=404, detail='分类不存在')
    return {'ok': True}
