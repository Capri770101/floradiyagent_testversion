"""routers/catalog.py —— 目录（方案/店铺）与运维端点（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent.tools import get_tool_specs
from backend.config import settings
from backend.routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    _plan_card,
    _plan_full,
    _shop_card,
    _shop_full,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)
from backend.storage import config as config_store

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["catalog"])
logger = logging.getLogger("api")

@router.get("/geocode")
async def geocode(lat: float, lng: float) -> dict[str, Any]:
    """逆地理编码：坐标 → 地址（腾讯位置服务 WebService API，后端代理避免前端 CORS）。

    供订单确认页地图选点后把坐标转为地址文本。未配置 TENCENT_MAP_KEY 时返回空 address。
    """
    if not settings.tencent_map_key:
        return {"status": "no_key", "address": ""}
    import httpx

    params = {
        "location": f"{lat},{lng}",
        "key": settings.tencent_map_key,
        "get_poi": "0",
    }
    try:
        resp = await asyncio.to_thread(
            lambda: httpx.get(settings.tencent_geocode_url, params=params, timeout=8.0).json()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[geocode] 逆地理编码失败 lat=%s lng=%s: %s", lat, lng, exc)
        return {"status": "error", "address": ""}
    if resp.get("status") != 0:
        return {"status": str(resp.get("status", "error")), "address": ""}
    result = resp.get("result") or {}
    return {
        "status": "ok",
        "address": result.get("formatted_addresses", {}).get("recommend")
        or result.get("address")
        or "",
    }

@router.get("/config")
async def public_config() -> dict[str, Any]:
    """公开运营配置（H5 读：配送时段/运费/FAQ/公告；后端 seed 兜底，前端不做业务兜底）。"""
    return await asyncio.to_thread(config_store.public_config)

@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_mode": "live" if settings.llm_enabled else "mock",
        "image_mode": "live" if settings.image_enabled else "mock",
        "auth": "required" if settings.auth_required else "dev",
        "data_source": settings.data_source,
        "rag_enabled": settings.rag_enabled,
        "tools": len(get_tool_specs()),
    }



@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """轻量运行时指标 + 配置快照（接入 Prometheus 前先用这个看板）。"""
    return {
        "requests_total": METRICS["requests_total"],
        "requests_by_path": METRICS["requests_by_path"],
        "status_codes": METRICS["status_codes"],
        "config": {
            "llm_mode": "live" if settings.llm_enabled else "mock",
            "image_mode": "live" if settings.image_enabled else "mock",
            "auth": "required" if settings.auth_required else "dev",
            "data_source": settings.data_source,
            "rag_enabled": settings.rag_enabled,
            "rag_top_k": settings.rag_top_k,
            "tools": len(get_tool_specs()),
        },
    }



@router.get("/tools")
async def list_tools() -> dict[str, Any]:
    return {
        "count": len(get_tool_specs()),
        "tools": [
            {"name": t.name, "description": t.description, "parameters": t.parameters, "tags": list(t.tags)}
            for t in get_tool_specs()
        ],
    }


# --------------------------------------------------------------------------- #
# 电商接口（方案 / 店铺 / 购物车 / 订单 / 支付）
# 说明：方案与店铺数据来自 storage.repository.repo（默认 MockRepository，含示例
# 数据；DATA_SOURCE=remote 时自动切真实后端），购物车/订单/支付走 SQLite 持久化。
# H5 通过 /api 代理访问，本服务路由不带 /api 前缀。
# --------------------------------------------------------------------------- #



@router.get("/plans")
async def list_plans(keyword: str = "") -> dict[str, Any]:
    """浏览/搜索方案（空关键词 = 全部）。"""
    plans = await asyncio.to_thread(repo.search_plans, keyword)
    return {"plans": [_plan_card(p) for p in plans]}



@router.get("/plans/{plan_id}")
async def plan_detail(plan_id: str) -> dict[str, Any]:
    p = await asyncio.to_thread(repo.get_plan, plan_id)
    if p:
        return {"plan": _plan_full(p)}
    # DIY_ 前缀方案（用户自定义）回落 diy_plans 资产库，支持刷新/直链进入详情页。
    # 注意：DIY 方案直接返回资产库原样结构（与对话「确认方案」传入的 plan 一致，
    # 前端 DiyDetail.normalizePlan 直接消费 design/effect_prompt/diy_steps 等字段），
    # 不走 _plan_full——那是商品详情序列化器，会丢弃 DIY 专属字段。
    from backend.storage import diy as diy_store

    p = await asyncio.to_thread(diy_store.get_diy_plan, plan_id)
    if not p:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"plan": p}



@router.get("/shops")
async def list_shops_endpoint(lat: float | None = None, lng: float | None = None) -> dict[str, Any]:
    """店铺列表；传入 lat/lng（用户定位）时按真实经纬度排序并展示计算距离。"""
    location = {"lat": lat, "lng": lng} if lat is not None and lng is not None else None
    shops = await asyncio.to_thread(repo.list_shops, None, location)
    return {"shops": [_shop_card(s, location) for s in shops]}



@router.get("/shops/{shop_id}")
async def shop_detail_endpoint(shop_id: str) -> dict[str, Any]:
    s = await asyncio.to_thread(repo.get_shop, shop_id)
    if not s:
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"shop": _shop_full(s)}


# --------------------------------------------------------------------------- #
# 管理后台（方案 / 店铺 CRUD）
# 权限：仅 admin 角色可访问；未登录 401，非管理员 403（users.role 字段，
# 用 `python cli.py make-admin <username>` 授予管理员角色）。
# --------------------------------------------------------------------------- #


