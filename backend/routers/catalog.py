"""routers/catalog.py —— 目录（方案/店铺）与运维端点（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent.tools import get_tool_specs
from backend.config import settings
from backend.routers.common import METRICS, _plan_card, _plan_full, _shop_card, _shop_full, repo
from backend.storage import catalog as catalog_store
from backend.storage import config as config_store
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=['catalog'])
logger = logging.getLogger('api')

@router.get('/geocode')
async def geocode(lat: float, lng: float) -> dict[str, Any]:
    """逆地理编码：坐标 → 地址（腾讯位置服务 WebService API，后端代理避免前端 CORS）。

    供订单确认页地图选点后把坐标转为地址文本。未配置 TENCENT_MAP_KEY 时返回空 address。
    """
    if not settings.tencent_map_key:
        return {'status': 'no_key', 'address': ''}
    import httpx
    params = {'location': f'{lat},{lng}', 'key': settings.tencent_map_key, 'get_poi': '0'}
    try:
        resp = await asyncio.to_thread(lambda: httpx.get(settings.tencent_geocode_url, params=params, timeout=8.0).json())
    except Exception as exc:
        logger.warning('[geocode] 逆地理编码失败 lat=%s lng=%s: %s', lat, lng, exc)
        return {'status': 'error', 'address': ''}
    if resp.get('status') != 0:
        return {'status': str(resp.get('status', 'error')), 'address': ''}
    result = resp.get('result') or {}
    return {'status': 'ok', 'address': result.get('formatted_addresses', {}).get('recommend') or result.get('address') or ''}

@router.get('/config')
async def public_config() -> dict[str, Any]:
    """公开运营配置（H5 读：配送时段/运费/FAQ/公告；后端 seed 兜底，前端不做业务兜底）。"""
    return await config_store.public_config()

@router.get('/health')
async def health() -> dict[str, Any]:
    return {'status': 'ok', 'llm_mode': 'live' if settings.llm_enabled else 'mock', 'image_mode': 'live' if settings.image_enabled else 'mock', 'auth': 'required' if settings.auth_required else 'dev', 'data_source': settings.data_source, 'rag_enabled': settings.rag_enabled, 'tools': len(get_tool_specs())}

@router.get('/metrics')
async def metrics() -> dict[str, Any]:
    """轻量运行时指标 + 配置快照（接入 Prometheus 前先用这个看板）。"""
    return {'requests_total': METRICS['requests_total'], 'requests_by_path': METRICS['requests_by_path'], 'status_codes': METRICS['status_codes'], 'config': {'llm_mode': 'live' if settings.llm_enabled else 'mock', 'image_mode': 'live' if settings.image_enabled else 'mock', 'auth': 'required' if settings.auth_required else 'dev', 'data_source': settings.data_source, 'rag_enabled': settings.rag_enabled, 'rag_top_k': settings.rag_top_k, 'tools': len(get_tool_specs())}}

@router.get('/tools')
async def list_tools() -> dict[str, Any]:
    return {'count': len(get_tool_specs()), 'tools': [{'name': t.name, 'description': t.description, 'parameters': t.parameters, 'tags': list(t.tags)} for t in get_tool_specs()]}

@router.get('/plans')
async def list_plans(keyword: str='') -> dict[str, Any]:
    """浏览/搜索方案（空关键词 = 全部）。"""
    plans = await repo.search_plans(keyword)
    return {'plans': [await _plan_card(p) for p in plans]}

@router.get('/plans/{plan_id}')
async def plan_detail(plan_id: str) -> dict[str, Any]:
    p = await repo.get_plan(plan_id)
    if p:
        return {'plan': await _plan_full(p)}
    from backend.storage import diy as diy_store
    p = await diy_store.get_diy_plan(plan_id)
    if not p:
        raise HTTPException(status_code=404, detail='方案不存在')
    return {'plan': p}

@router.get('/shops')
async def list_shops_endpoint(lat: float | None=None, lng: float | None=None) -> dict[str, Any]:
    """店铺列表（C 端）。

    强制先选位置：未传 lat/lng 时返回空列表并置 require_location=True，由前端引导用户
    选择定位后再请求。传入定位时仅返回「状态=营业中 且 距定位 ≤ delivery_radius_km」的店，
    按距离升序，确保顾客看到的都是可配送、在营的真实店铺。
    """
    if lat is None or lng is None:
        return {'shops': [], 'require_location': True}
    location = {'lat': lat, 'lng': lng}
    all_shops = await repo.list_shops(None, location)
    radius = settings.delivery_radius_km
    out = []
    for s in all_shops:
        if s.get('status') != '营业中':
            continue
        if s.get('lat') is not None:
            d = catalog_store.distance_km(lat, lng, s['lat'], s['lng'])
            if d > radius:
                continue
        out.append(_shop_card(s, location))
    return {'shops': out, 'require_location': False}

@router.get('/shops/{shop_id}')
async def shop_detail_endpoint(shop_id: str) -> dict[str, Any]:
    s = await repo.get_shop(shop_id)
    if not s:
        raise HTTPException(status_code=404, detail='店铺不存在')
    return {'shop': await _shop_full(s)}
