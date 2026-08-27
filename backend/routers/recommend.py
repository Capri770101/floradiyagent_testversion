"""routers/recommend.py —— 个性化推荐端点（模块三）。

- GET /recommend/plans：猜你喜欢 / 同风格方案（定位 + 偏好 + 热度融合）
- GET /recommend/shops：附近同类店铺（店铺详情页推荐位）
- GET /recommend/signature：当季臻选（角标气质 + 热度 + 距离策展，不依赖画像）

可选登录：有 token 用账号偏好，无 token（匿名）仅定位 + 热度，永不报错。
"""
from __future__ import annotations

from typing import Any

from backend.routers.common import _plan_card, _shop_card, resolve_uid
from backend.storage import recommend as rec
from fastapi import APIRouter, Query, Request

router = APIRouter(prefix='/recommend', tags=['recommend'])

@router.get('/plans')
async def recommend_plans_endpoint(request: Request, lat: float | None=Query(None, ge=-90, le=90), lng: float | None=Query(None, ge=-180, le=180), limit: int=Query(6, ge=1, le=20), style: str | None=Query(None, max_length=20), user_id: str | None=None) -> dict[str, Any]:
    """个性化方案推荐：定位 + 偏好 + 热度；style 传值时同风格方案加权。"""
    uid = await resolve_uid(request, user_id)
    items = await rec.recommend_plans(uid, lat, lng, limit, style)
    return {'items': [await _plan_card(p) for p in items], 'total': len(items)}

@router.get('/shops')
async def recommend_shops_endpoint(request: Request, lat: float | None=Query(None, ge=-90, le=90), lng: float | None=Query(None, ge=-180, le=180), limit: int=Query(6, ge=1, le=20), shop_id: str | None=Query(None, max_length=64), user_id: str | None=None) -> dict[str, Any]:
    """附近同类店铺推荐：排除自身（shop_id），同价位带加权。"""
    uid = await resolve_uid(request, user_id)
    location = {'lat': lat, 'lng': lng} if lat is not None and lng is not None else None
    items = await rec.recommend_shops(uid, lat, lng, limit, shop_id)
    return {'items': [_shop_card(s, location) for s in items], 'total': len(items)}

@router.get('/signature')
async def recommend_signature_endpoint(lat: float | None=Query(None, ge=-90, le=90), lng: float | None=Query(None, ge=-180, le=180), limit: int=Query(3, ge=1, le=10)) -> dict[str, Any]:
    """当季臻选：策展式推荐（角标气质 + 热度 + 距离），首页 Signature Collection 位。"""
    items = await rec.recommend_signature(lat, lng, limit)
    out = []
    for p in items:
        card = await _plan_card(p)
        d = p.pop('dist_km', None)
        if d is not None:
            card['dist_km'] = round(d, 1)
        out.append(card)
    return {'items': out, 'total': len(out)}
