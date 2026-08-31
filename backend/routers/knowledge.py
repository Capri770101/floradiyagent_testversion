"""routers/knowledge.py —— 知识库管理后台 API。

提供花材、搭配方案、场景、风格的 CRUD 操作。
仅管理员可访问。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.routers.common import _require_admin
from backend.storage import knowledge_db as kdb

logger = logging.getLogger('routers.knowledge')
router = APIRouter(prefix='/knowledge', tags=['knowledge'])


# ========================================
# 请求/响应模型
# ========================================

class FlowerCreate(BaseModel):
    """创建花材请求。"""
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    flower_language: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    price_tier: str = Field(default='中')
    price_per_stem: float | None = None
    freshness_days: int | None = None
    category: str = Field(default='主花')
    care_tips: str = ''
    pairing_notes: str = ''
    tags: list[str] = Field(default_factory=list)


class FlowerUpdate(BaseModel):
    """更新花材请求。"""
    name: str | None = None
    aliases: list[str] | None = None
    flower_language: list[str] | None = None
    colors: list[str] | None = None
    season: list[str] | None = None
    price_tier: str | None = None
    price_per_stem: float | None = None
    freshness_days: int | None = None
    category: str | None = None
    care_tips: str | None = None
    pairing_notes: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class PairingCreate(BaseModel):
    """创建搭配方案请求。"""
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    description: str = ''
    occasion_ids: list[str] = Field(default_factory=list)
    style_ids: list[str] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    season: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    flowers: list[dict[str, Any]] = Field(default_factory=list)


class OccasionCreate(BaseModel):
    """创建场景请求。"""
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    description: str = ''
    keywords: list[str] = Field(default_factory=list)
    suggested_flowers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class StyleCreate(BaseModel):
    """创建风格请求。"""
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    description: str = ''
    color_scheme: list[str] = Field(default_factory=list)
    flower_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ========================================
# 花材接口
# ========================================

@router.get('/flowers')
async def list_flowers(
    request: Request,
    category: str = Query('', description='分类筛选'),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """分页查询花材。"""
    await _require_admin(request)
    flowers, total = await kdb.list_flowers(category=category, page=page, page_size=page_size)
    return {
        'items': flowers,
        'total': total,
        'page': page,
        'page_size': page_size,
    }


@router.get('/flowers/{flower_id}')
async def get_flower(flower_id: str, request: Request):
    """获取花材详情。"""
    await _require_admin(request)
    flower = await kdb.get_flower(flower_id)
    if not flower:
        raise HTTPException(status_code=404, detail='花材不存在')
    return flower


@router.post('/flowers')
async def create_flower(data: FlowerCreate, request: Request):
    """创建花材。"""
    admin_uid = await _require_admin(request)
    existing = await kdb.get_flower(data.id)
    if existing:
        raise HTTPException(status_code=409, detail='花材 ID 已存在')
    flower = await kdb.create_flower(data.model_dump(), created_by=admin_uid)
    return flower


@router.put('/flowers/{flower_id}')
async def update_flower(
    flower_id: str,
    data: FlowerUpdate,
    request: Request,
):
    """更新花材。"""
    admin_uid = await _require_admin(request)
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail='无更新内容')
    flower = await kdb.update_flower(flower_id, updates, updated_by=admin_uid)
    if not flower:
        raise HTTPException(status_code=404, detail='花材不存在')
    return flower


@router.delete('/flowers/{flower_id}')
async def delete_flower(flower_id: str, request: Request):
    """删除花材（软删除）。"""
    admin_uid = await _require_admin(request)
    ok = await kdb.delete_flower(flower_id, deleted_by=admin_uid)
    if not ok:
        raise HTTPException(status_code=404, detail='花材不存在')
    return {'ok': True}


# ========================================
# 搭配方案接口
# ========================================

@router.get('/pairings')
async def list_pairings(
    request: Request,
    occasion: str = Query('', description='场景筛选'),
    style: str = Query('', description='风格筛选'),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """分页查询搭配方案。"""
    await _require_admin(request)
    pairings, total = await kdb.list_pairings(occasion=occasion, style=style, page=page, page_size=page_size)
    return {
        'items': pairings,
        'total': total,
        'page': page,
        'page_size': page_size,
    }


@router.get('/pairings/{pairing_id}')
async def get_pairing(pairing_id: str, request: Request):
    """获取搭配方案详情。"""
    await _require_admin(request)
    pairing = await kdb.get_pairing(pairing_id)
    if not pairing:
        raise HTTPException(status_code=404, detail='搭配方案不存在')
    return pairing


@router.post('/pairings')
async def create_pairing(data: PairingCreate, request: Request):
    """创建搭配方案。"""
    admin_uid = await _require_admin(request)
    existing = await kdb.get_pairing(data.id)
    if existing:
        raise HTTPException(status_code=409, detail='搭配方案 ID 已存在')
    pairing = await kdb.create_pairing(data.model_dump(), created_by=admin_uid)
    return pairing


@router.put('/pairings/{pairing_id}')
async def update_pairing(
    pairing_id: str,
    data: PairingCreate,
    request: Request,
):
    """更新搭配方案。"""
    admin_uid = await _require_admin(request)
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail='无更新内容')
    pairing = await kdb.update_pairing(pairing_id, updates, updated_by=admin_uid)
    if not pairing:
        raise HTTPException(status_code=404, detail='搭配方案不存在')
    return pairing


@router.delete('/pairings/{pairing_id}')
async def delete_pairing(pairing_id: str, request: Request):
    """删除搭配方案（软删除）。"""
    admin_uid = await _require_admin(request)
    ok = await kdb.delete_pairing(pairing_id, deleted_by=admin_uid)
    if not ok:
        raise HTTPException(status_code=404, detail='搭配方案不存在')
    return {'ok': True}


@router.get('/pairings/trending')
async def trending_pairings(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
):
    """获取热门搭配方案（按使用次数排序）。"""
    await _require_admin(request)
    pairings = await kdb.get_trending_pairings(limit=limit)
    return {'items': pairings, 'total': len(pairings)}


@router.get('/pairings/stats')
async def pairing_stats(request: Request):
    """获取搭配方案使用统计。"""
    await _require_admin(request)
    stats = await kdb.get_pairing_stats()
    return stats


# ========================================
# 场景接口
# ========================================

@router.get('/occasions')
async def list_occasions(request: Request):
    """查询场景列表。"""
    await _require_admin(request)
    occasions = await kdb.list_occasions()
    return {'items': occasions, 'total': len(occasions)}


@router.get('/occasions/{occasion_id}')
async def get_occasion(occasion_id: str, request: Request):
    """获取场景详情。"""
    await _require_admin(request)
    occasion = await kdb.get_occasion(occasion_id)
    if not occasion:
        raise HTTPException(status_code=404, detail='场景不存在')
    return occasion


@router.post('/occasions')
async def create_occasion(data: OccasionCreate, request: Request):
    """创建场景。"""
    admin_uid = await _require_admin(request)
    existing = await kdb.get_occasion(data.id)
    if existing:
        raise HTTPException(status_code=409, detail='场景 ID 已存在')
    occasion = await kdb.create_occasion(data.model_dump(), created_by=admin_uid)
    return occasion


@router.put('/occasions/{occasion_id}')
async def update_occasion(
    occasion_id: str,
    data: OccasionCreate,
    request: Request,
):
    """更新场景。"""
    admin_uid = await _require_admin(request)
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail='无更新内容')
    occasion = await kdb.update_occasion(occasion_id, updates, updated_by=admin_uid)
    if not occasion:
        raise HTTPException(status_code=404, detail='场景不存在')
    return occasion


@router.delete('/occasions/{occasion_id}')
async def delete_occasion(occasion_id: str, request: Request):
    """删除场景（软删除）。"""
    admin_uid = await _require_admin(request)
    ok = await kdb.delete_occasion(occasion_id, deleted_by=admin_uid)
    if not ok:
        raise HTTPException(status_code=404, detail='场景不存在')
    return {'ok': True}


# ========================================
# 风格接口
# ========================================

@router.get('/styles')
async def list_styles(request: Request):
    """查询风格列表。"""
    await _require_admin(request)
    styles = await kdb.list_styles()
    return {'items': styles, 'total': len(styles)}


@router.get('/styles/{style_id}')
async def get_style(style_id: str, request: Request):
    """获取风格详情。"""
    await _require_admin(request)
    style = await kdb.get_style(style_id)
    if not style:
        raise HTTPException(status_code=404, detail='风格不存在')
    return style


@router.post('/styles')
async def create_style(data: StyleCreate, request: Request):
    """创建风格。"""
    admin_uid = await _require_admin(request)
    existing = await kdb.get_style(data.id)
    if existing:
        raise HTTPException(status_code=409, detail='风格 ID 已存在')
    style = await kdb.create_style(data.model_dump(), created_by=admin_uid)
    return style


@router.put('/styles/{style_id}')
async def update_style(
    style_id: str,
    data: StyleCreate,
    request: Request,
):
    """更新风格。"""
    admin_uid = await _require_admin(request)
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail='无更新内容')
    style = await kdb.update_style(style_id, updates, updated_by=admin_uid)
    if not style:
        raise HTTPException(status_code=404, detail='风格不存在')
    return style


@router.delete('/styles/{style_id}')
async def delete_style(style_id: str, request: Request):
    """删除风格（软删除）。"""
    admin_uid = await _require_admin(request)
    ok = await kdb.delete_style(style_id, deleted_by=admin_uid)
    if not ok:
        raise HTTPException(status_code=404, detail='风格不存在')
    return {'ok': True}


# ========================================
# 预算方案接口
# ========================================

class BudgetPlanCreate(BaseModel):
    """创建预算方案请求。"""
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    min_budget: float
    max_budget: float | None = None
    main_count_min: int | None = None
    main_count_max: int | None = None
    support_count: int | None = None
    packaging_level: str | None = None
    suggested_flowers: list[str] = Field(default_factory=list)
    description: str = ''


@router.get('/budgets')
async def list_budgets(request: Request):
    """查询预算方案列表。"""
    await _require_admin(request)
    budgets = await kdb.list_budget_plans()
    return {'items': budgets, 'total': len(budgets)}


@router.get('/budgets/{budget_id}')
async def get_budget(budget_id: str, request: Request):
    """获取预算方案详情。"""
    await _require_admin(request)
    budget = await kdb.get_budget_plan(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail='预算方案不存在')
    return budget


@router.post('/budgets')
async def create_budget(data: BudgetPlanCreate, request: Request):
    """创建预算方案。"""
    admin_uid = await _require_admin(request)
    existing = await kdb.get_budget_plan(data.id)
    if existing:
        raise HTTPException(status_code=409, detail='预算方案 ID 已存在')
    budget = await kdb.create_budget_plan(data.model_dump(), created_by=admin_uid)
    return budget


# ========================================
# 包装方案接口
# ========================================

class PackagingCreate(BaseModel):
    """创建包装方案请求。"""
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    material: str | None = None
    color: str | None = None
    price: float
    description: str = ''
    tags: list[str] = Field(default_factory=list)


@router.get('/packagings')
async def list_packagings(request: Request):
    """查询包装方案列表。"""
    await _require_admin(request)
    packagings = await kdb.list_packaging()
    return {'items': packagings, 'total': len(packagings)}


@router.get('/packagings/{packaging_id}')
async def get_packaging(packaging_id: str, request: Request):
    """获取包装方案详情。"""
    await _require_admin(request)
    packaging = await kdb.get_packaging(packaging_id)
    if not packaging:
        raise HTTPException(status_code=404, detail='包装方案不存在')
    return packaging


@router.post('/packagings')
async def create_packaging(data: PackagingCreate, request: Request):
    """创建包装方案。"""
    admin_uid = await _require_admin(request)
    existing = await kdb.get_packaging(data.id)
    if existing:
        raise HTTPException(status_code=409, detail='包装方案 ID 已存在')
    packaging = await kdb.create_packaging(data.model_dump(), created_by=admin_uid)
    return packaging


# ========================================
# 统计接口
# ========================================

@router.get('/stats')
async def get_stats(request: Request):
    """获取知识库统计信息。"""
    await _require_admin(request)
    stats = await kdb.get_knowledge_stats()
    return stats
