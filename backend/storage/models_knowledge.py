"""models_knowledge.py —— 花卉知识库数据模型。

定义花卉知识库的所有表结构，包括：
- 花材表 (flowers)
- 搭配方案表 (pairings)
- 搭配花材关系表 (pairing_flowers)
- 场景表 (occasions)
- 风格表 (styles)
- 预算方案表 (budget_plans)
- 包装方案表 (packaging)
- 知识变更日志 (knowledge_audit_log)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, validator


def _now() -> str:
    """返回当前 UTC 时间字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ========================================
# 花材模型
# ========================================

class FlowerBase(BaseModel):
    """花材基础模型。"""
    name: str = Field(..., min_length=1, max_length=100, description='花材名称')
    aliases: list[str] = Field(default_factory=list, description='别名列表')
    flower_language: list[str] = Field(default_factory=list, description='花语')
    colors: list[str] = Field(..., min_length=1, description='颜色列表')
    season: list[str] = Field(..., min_length=1, description='花期季节')
    price_tier: str = Field('中', description='价格档次：低/中/高')
    price_per_stem: float | None = Field(None, ge=0, description='单枝参考价（元）')
    freshness_days: int | None = Field(None, ge=0, description='保鲜天数')
    category: str = Field('主花', description='分类：主花/配花/配叶/特殊')
    care_tips: str = Field('', description='养护说明')
    pairing_notes: str = Field('', description='搭配说明')
    tags: list[str] = Field(default_factory=list, description='标签')

    @validator('price_tier')
    def validate_price_tier(cls, v: str) -> str:
        if v not in ('低', '中', '高'):
            raise ValueError('price_tier 必须是 低/中/高')
        return v

    @validator('category')
    def validate_category(cls, v: str) -> str:
        if v not in ('主花', '配花', '配叶', '特殊'):
            raise ValueError('category 必须是 主花/配花/配叶/特殊')
        return v


class FlowerCreate(FlowerBase):
    """创建花材请求模型。"""
    id: str = Field(..., min_length=1, max_length=50, description='花材ID，如 F_ROSE')


class FlowerUpdate(BaseModel):
    """更新花材请求模型（所有字段可选）。"""
    name: str | None = Field(None, min_length=1, max_length=100)
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

    @validator('price_tier')
    def validate_price_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in ('低', '中', '高'):
            raise ValueError('price_tier 必须是 低/中/高')
        return v

    @validator('category')
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in ('主花', '配花', '配叶', '特殊'):
            raise ValueError('category 必须是 主花/配花/配叶/特殊')
        return v

    @validator('status')
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ('active', 'archived'):
            raise ValueError('status 必须是 active/archived')
        return v


class Flower(FlowerBase):
    """花材完整模型（含数据库字段）。"""
    id: str
    status: str = 'active'
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    created_by: str | None = None
    version: int = 1

    class Config:
        from_attributes = True


# ========================================
# 搭配方案模型
# ========================================

class PairingBase(BaseModel):
    """搭配方案基础模型。"""
    name: str = Field(..., min_length=1, max_length=100, description='搭配名称')
    description: str = Field('', description='搭配说明')
    occasion_ids: list[str] = Field(default_factory=list, description='适用场景ID列表')
    style_ids: list[str] = Field(default_factory=list, description='适用风格ID列表')
    budget_min: float | None = Field(None, ge=0, description='最低预算（元）')
    budget_max: float | None = Field(None, ge=0, description='最高预算（元）')
    season: list[str] = Field(default_factory=list, description='适用季节')
    tags: list[str] = Field(default_factory=list, description='标签')


class PairingCreate(PairingBase):
    """创建搭配方案请求模型。"""
    id: str = Field(..., min_length=1, max_length=50, description='搭配ID，如 P_ROMANCE')
    flowers: list[PairingFlowerItem] = Field(default_factory=list, description='搭配花材列表')


class PairingFlowerItem(BaseModel):
    """搭配花材项。"""
    flower_id: str = Field(..., description='花材ID')
    flower_type: str = Field(..., description='花材类型：main/support/leaf')
    quantity_min: int = Field(1, ge=1, description='最少数量')
    quantity_max: int = Field(1, ge=1, description='最多数量')
    is_required: bool = Field(True, description='是否必需')
    sort_order: int = Field(0, description='排序')

    @validator('flower_type')
    def validate_flower_type(cls, v: str) -> str:
        if v not in ('main', 'support', 'leaf'):
            raise ValueError('flower_type 必须是 main/support/leaf')
        return v


# ========================================
# 场景模型
# ========================================

class OccasionBase(BaseModel):
    """场景基础模型。"""
    name: str = Field(..., min_length=1, max_length=100, description='场景名称')
    description: str = Field('', description='场景说明')
    keywords: list[str] = Field(default_factory=list, description='关键词')
    suggested_flowers: list[str] = Field(default_factory=list, description='推荐花材')
    tags: list[str] = Field(default_factory=list, description='标签')


class OccasionCreate(OccasionBase):
    """创建场景请求模型。"""
    id: str = Field(..., min_length=1, max_length=50, description='场景ID，如 SC_BIRTHDAY')


class Occasion(OccasionBase):
    """场景完整模型。"""
    id: str
    status: str = 'active'
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    version: int = 1

    class Config:
        from_attributes = True


# ========================================
# 风格模型
# ========================================

class StyleBase(BaseModel):
    """风格基础模型。"""
    name: str = Field(..., min_length=1, max_length=100, description='风格名称')
    description: str = Field('', description='风格说明')
    color_scheme: list[str] = Field(default_factory=list, description='配色方案')
    flower_types: list[str] = Field(default_factory=list, description='推荐花材')
    keywords: list[str] = Field(default_factory=list, description='关键词')
    tags: list[str] = Field(default_factory=list, description='标签')


class StyleCreate(StyleBase):
    """创建风格请求模型。"""
    id: str = Field(..., min_length=1, max_length=50, description='风格ID，如 S_ROMANTIC')


class Style(StyleBase):
    """风格完整模型。"""
    id: str
    status: str = 'active'
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    version: int = 1

    class Config:
        from_attributes = True


# ========================================
# 预算方案模型
# ========================================

class BudgetPlanBase(BaseModel):
    """预算方案基础模型。"""
    name: str = Field(..., min_length=1, max_length=100, description='方案名称')
    min_budget: float = Field(..., ge=0, description='最低预算')
    max_budget: float | None = Field(None, ge=0, description='最高预算（NULL=无上限）')
    main_count_min: int | None = Field(None, ge=0, description='主花最少数量')
    main_count_max: int | None = Field(None, ge=0, description='主花最多数量')
    support_count: int | None = Field(None, ge=0, description='配花数量')
    packaging_level: str = Field('', description='包装档次：简约/精美/高档')
    suggested_flowers: list[str] = Field(default_factory=list, description='推荐花材')
    description: str = Field('', description='说明')


class BudgetPlanCreate(BudgetPlanBase):
    """创建预算方案请求模型。"""
    id: str = Field(..., min_length=1, max_length=50, description='方案ID，如 B_ECONOMY')


class BudgetPlan(BudgetPlanBase):
    """预算方案完整模型。"""
    id: str
    status: str = 'active'
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    version: int = 1

    class Config:
        from_attributes = True


# ========================================
# 包装方案模型
# ========================================

class PackagingBase(BaseModel):
    """包装方案基础模型。"""
    name: str = Field(..., min_length=1, max_length=100, description='包装名称')
    material: str = Field('', description='材质')
    color: str = Field('', description='颜色')
    price: float = Field(..., ge=0, description='价格')
    description: str = Field('', description='说明')
    tags: list[str] = Field(default_factory=list, description='标签')


class PackagingCreate(PackagingBase):
    """创建包装方案请求模型。"""
    id: str = Field(..., min_length=1, max_length=50, description='包装ID，如 PK_SIMPLE')


class Packaging(PackagingBase):
    """包装方案完整模型。"""
    id: str
    status: str = 'active'
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    version: int = 1

    class Config:
        from_attributes = True


# ========================================
# 审计日志模型
# ========================================

class AuditLog(BaseModel):
    """知识变更审计日志。"""
    id: int | None = None
    table_name: str = Field(..., description='表名')
    record_id: str = Field(..., description='记录ID')
    action: str = Field(..., description='操作：INSERT/UPDATE/DELETE')
    old_value: dict[str, Any] | None = Field(None, description='旧值')
    new_value: dict[str, Any] | None = Field(None, description='新值')
    changed_by: str | None = Field(None, description='操作人')
    changed_at: str = Field(default_factory=_now, description='变更时间')
    reason: str | None = Field(None, description='变更原因')

    @validator('action')
    def validate_action(cls, v: str) -> str:
        if v not in ('INSERT', 'UPDATE', 'DELETE'):
            raise ValueError('action 必须是 INSERT/UPDATE/DELETE')
        return v


# ========================================
# 查询响应模型
# ========================================

class PaginatedResponse(BaseModel):
    """分页响应模型。"""
    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int


class KnowledgeStats(BaseModel):
    """知识库统计模型。"""
    flowers_count: int
    pairings_count: int
    occasions_count: int
    styles_count: int
    budget_plans_count: int
    packaging_count: int
    last_updated: str | None = None


# ========================================
# 数据库表结构定义
# ========================================

KNOWLEDGE_SCHEMA = """
-- 花卉知识库表结构

-- 1. 花材表
CREATE TABLE IF NOT EXISTS flowers (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    aliases         TEXT,                       -- JSON 数组
    flower_language TEXT,                       -- JSON 数组
    colors          TEXT NOT NULL,              -- JSON 数组
    season          TEXT NOT NULL,              -- JSON 数组
    price_tier      TEXT NOT NULL DEFAULT '中',
    price_per_stem  REAL,
    freshness_days  INTEGER,
    category        TEXT NOT NULL DEFAULT '主花',
    care_tips       TEXT,
    pairing_notes   TEXT,
    tags            TEXT,                       -- JSON 数组
    source          TEXT NOT NULL DEFAULT 'manual',  -- manual/crawler/llm/import
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    created_by      TEXT,
    version         INTEGER NOT NULL DEFAULT 1
);

-- 2. 搭配方案表
CREATE TABLE IF NOT EXISTS pairings (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    occasion_ids    TEXT,                       -- JSON 数组
    style_ids       TEXT,                       -- JSON 数组
    budget_min      REAL,
    budget_max      REAL,
    season          TEXT,                       -- JSON 数组
    tags            TEXT,                       -- JSON 数组
    use_count       INTEGER DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'manual',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    created_by      TEXT,
    version         INTEGER NOT NULL DEFAULT 1
);

-- 3. 搭配花材关系表
CREATE TABLE IF NOT EXISTS pairing_flowers (
    pairing_id      TEXT NOT NULL,
    flower_id       TEXT NOT NULL,
    flower_type     TEXT NOT NULL,              -- main/support/leaf
    quantity_min    INTEGER DEFAULT 1,
    quantity_max    INTEGER DEFAULT 1,
    is_required     INTEGER DEFAULT 1,
    sort_order      INTEGER DEFAULT 0,
    PRIMARY KEY (pairing_id, flower_id, flower_type)
);

-- 4. 场景表
CREATE TABLE IF NOT EXISTS occasions (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    keywords        TEXT,                       -- JSON 数组
    suggested_flowers TEXT,                     -- JSON 数组
    tags            TEXT,                       -- JSON 数组
    source          TEXT NOT NULL DEFAULT 'manual',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

-- 5. 风格表
CREATE TABLE IF NOT EXISTS styles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    color_scheme    TEXT,                       -- JSON 数组
    flower_types    TEXT,                       -- JSON 数组
    keywords        TEXT,                       -- JSON 数组
    tags            TEXT,                       -- JSON 数组
    source          TEXT NOT NULL DEFAULT 'manual',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

-- 6. 预算方案表
CREATE TABLE IF NOT EXISTS budget_plans (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    min_budget      REAL NOT NULL,
    max_budget      REAL,
    main_count_min  INTEGER,
    main_count_max  INTEGER,
    support_count   INTEGER,
    packaging_level TEXT,
    suggested_flowers TEXT,                     -- JSON 数组
    description     TEXT,
    source          TEXT NOT NULL DEFAULT 'manual',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

-- 7. 包装方案表
CREATE TABLE IF NOT EXISTS packaging (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    material        TEXT,
    color           TEXT,
    price           REAL NOT NULL,
    description     TEXT,
    tags            TEXT,                       -- JSON 数组
    source          TEXT NOT NULL DEFAULT 'manual',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

-- 8. 知识变更审计日志
CREATE TABLE IF NOT EXISTS knowledge_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name      TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    action          TEXT NOT NULL,
    old_value       TEXT,                       -- JSON
    new_value       TEXT,                       -- JSON
    changed_by      TEXT,
    changed_at      TEXT NOT NULL,
    reason          TEXT
);
"""

KNOWLEDGE_INDEXES = """
-- 知识库索引
CREATE INDEX IF NOT EXISTS idx_flowers_name ON flowers(name);
CREATE INDEX IF NOT EXISTS idx_flowers_category ON flowers(category);
CREATE INDEX IF NOT EXISTS idx_flowers_status ON flowers(status);
CREATE INDEX IF NOT EXISTS idx_flowers_price_tier ON flowers(price_tier);
CREATE INDEX IF NOT EXISTS idx_pairings_status ON pairings(status);
CREATE INDEX IF NOT EXISTS idx_pairing_flowers_pairing ON pairing_flowers(pairing_id);
CREATE INDEX IF NOT EXISTS idx_pairing_flowers_flower ON pairing_flowers(flower_id);
CREATE INDEX IF NOT EXISTS idx_occasions_status ON occasions(status);
CREATE INDEX IF NOT EXISTS idx_styles_status ON styles(status);
CREATE INDEX IF NOT EXISTS idx_budget_plans_status ON budget_plans(status);
CREATE INDEX IF NOT EXISTS idx_packaging_status ON packaging(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_table ON knowledge_audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_record ON knowledge_audit_log(record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON knowledge_audit_log(changed_at);
"""
