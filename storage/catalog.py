"""storage/catalog.py —— 基于 SQLite 的花艺商品目录仓储（DB 为唯一来源）。

交付级设计：
- 取代 MockRepository 成为默认数据来源（init_db 时由 seed_catalog 灌入示例数据），
  业务/工具层通过统一的 Repository 契约（search_plans/get_plan/list_shops/get_shop）
  访问，切换数据源时零改动。
- 检索与 Mock 行为对齐：空关键词=浏览全部；非空无命中=返回空（诚实）；
  结构化需求做「软过滤」（某条件全不中时回退不过滤，避免演示空结果）。
- 店铺按真实经纬度（location 透传后）做 haversine 距离排序，无定位时退回静态 distance_km。

注意：本模块刻意不 import storage.repository（避免循环依赖），与 MockRepository 保持契约一致即可。
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import uuid
from typing import Any

from storage.db import get_conn

logger = logging.getLogger("catalog")


# --------------------------------------------------------------------------- #
# 检索辅助（与 MockRepository 同逻辑，数据来源改为 DB）
# --------------------------------------------------------------------------- #


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间距离（km）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _parse_price_range(s: str | None) -> tuple[float | None, float | None]:
    """解析 '100-300' 价位区间，失败返回 (None, None)。"""
    if not s:
        return None, None
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(s))
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _filter_plans_by_requirement(
    plans: list[dict[str, Any]], requirement: Any | None
) -> list[dict[str, Any]]:
    """按结构化需求对方案做「软过滤」。"""
    if not requirement:
        return plans
    out = plans
    if requirement.budget_min is not None:
        lo = requirement.budget_min
        hi = requirement.budget_max or requirement.budget_min
        filtered = [p for p in out if lo <= p.get("price", 0) <= hi * 1.5]
        out = filtered or out
    if requirement.colors:
        def hit(p: dict[str, Any]) -> bool:
            blob = (p.get("name", "") + p.get("desc", "") + " ".join(p.get("tags", []))).lower()
            return any(c.lower() in blob for c in requirement.colors)

        filtered = [p for p in out if hit(p)]
        out = filtered or out
    return out


# --------------------------------------------------------------------------- #
# 种子数据（首次 init 灌入；与 MockRepository 示例数据一致）
# --------------------------------------------------------------------------- #

_CATEGORIES = [
    {"id": "cat_holiday", "name": "节日祝福", "sort": 1},
    {"id": "cat_love", "name": "浪漫告白", "sort": 2},
    {"id": "cat_daily", "name": "日常陪伴", "sort": 3},
]

_PLANS = [
    {
        "plan_id": "P001",
        "name": "康乃馨感恩花束",
        "price": 199.0,
        "desc": "11 支粉色康乃馨 + 满天星，适合送给母亲表达感恩。",
        "effect_image_url": "/generated/plan_P001.png",
        "merchant_name": "花漾工坊",
        "tags": ["母亲节", "康乃馨", "温馨"],
        "style": "韩式",
        "category_id": "cat_holiday",
    },
    {
        "plan_id": "P002",
        "name": "玫瑰轻奢花盒",
        "price": 299.0,
        "desc": "19 朵红玫瑰礼盒装，高级感拉满，适合纪念日。",
        "effect_image_url": "/generated/plan_P002.png",
        "merchant_name": "花漾工坊",
        "tags": ["玫瑰", "礼盒", "高端"],
        "style": "欧式",
        "category_id": "cat_love",
    },
    {
        "plan_id": "P003",
        "name": "向日葵花束",
        "price": 159.0,
        "desc": "阳光向日葵 + 尤加利叶，元气满满。",
        "effect_image_url": "/generated/plan_P003.png",
        "merchant_name": "绿野花艺",
        "tags": ["向日葵", "活力", "平价"],
        "style": "田园",
        "category_id": "cat_daily",
    },
]

_SHOPS = [
    {
        "shop_id": "S001",
        "name": "花漾工坊(盐田店)",
        "distance_km": 1.2,
        "price_range": "100-300",
        "rating": 4.8,
        "plan_ids": ["P001", "P002"],
        "lat": 22.560,
        "lng": 114.242,
        "intro": "专注鲜花定制与同城速递，包装精致、准时送达。",
    },
    {
        "shop_id": "S002",
        "name": "绿野花艺",
        "distance_km": 2.5,
        "price_range": "80-250",
        "rating": 4.6,
        "plan_ids": ["P003"],
        "lat": 22.572,
        "lng": 114.230,
        "intro": "主打自然风花艺，绿植与鲜切花搭配清新。",
    },
    {
        "shop_id": "S003",
        "name": "都市花房",
        "distance_km": 3.8,
        "price_range": "150-400",
        "rating": 4.9,
        "plan_ids": ["P001", "P002", "P003"],
        "lat": 22.548,
        "lng": 114.255,
        "intro": "高端花艺空间，节日礼盒与商务花艺俱佳。",
    },
]

# 生成占位效果图的方案（与 MockRepository 保持一致）
_PLACEHOLDER_PLANS = ["P001", "P002", "P003"]


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")


def catalog_ready() -> bool:
    """目录是否已灌入数据。表尚未创建（如导入期、测试未 init）时安全返回 False。"""
    try:
        conn = get_conn()
        row = conn.execute("SELECT COUNT(*) AS c FROM plans").fetchone()
        return bool(row and row["c"] > 0)
    except sqlite3.OperationalError:
        return False


def seed_catalog() -> None:
    """若 plans 为空，则灌入种子数据（幂等）。"""
    if catalog_ready():
        return
    from storage import tasks  # 延迟导入，避免循环依赖

    conn = get_conn()
    with conn:  # 单事务批量写入
        for c in _CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO categories(id, name, sort, created_at) VALUES (?,?,?,?)",
                (c["id"], c["name"], c["sort"], _now()),
            )
        for p in _PLANS:
            conn.execute(
                """INSERT OR IGNORE INTO plans
                   (id, name, price, desc, effect_image_url, merchant_name, tags, style, category_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    p["plan_id"], p["name"], p["price"], p["desc"], p["effect_image_url"],
                    p["merchant_name"], json.dumps(p["tags"], ensure_ascii=False),
                    p["style"], p["category_id"], _now(),
                ),
            )
        for s in _SHOPS:
            conn.execute(
                """INSERT OR IGNORE INTO shops
                   (id, name, rating, distance_km, price_range, lat, lng, status, intro, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    s["shop_id"], s["name"], s["rating"], s["distance_km"], s["price_range"],
                    s["lat"], s["lng"], "营业中", s["intro"], _now(),
                ),
            )
            for pid in s["plan_ids"]:
                conn.execute(
                    "INSERT OR IGNORE INTO shop_plans(shop_id, plan_id) VALUES (?,?)",
                    (s["shop_id"], pid),
                )
    # 生成占位效果图（dev/演示用，不依赖真实生图）
    for pid in _PLACEHOLDER_PLANS:
        try:
            tasks._write_mock_placeholder(f"plan_{pid}")
        except Exception:  # pragma: no cover
            logger.warning("占位图生成失败: %s", pid)
    logger.info("目录种子数据已灌入：%d 方案 / %d 店铺", len(_PLANS), len(_SHOPS))


# --------------------------------------------------------------------------- #
# DB 目录仓储（实现与 MockRepository 一致的契约）
# --------------------------------------------------------------------------- #


def _row_to_plan(row: Any) -> dict[str, Any]:
    d = dict(row)
    try:
        d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    # 对外契约使用 plan_id（与 MockRepository / api 映射一致）
    d["plan_id"] = d.pop("id")
    return d


def _shop_plan_ids(conn, shop_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT plan_id FROM shop_plans WHERE shop_id=?", (shop_id,)
    ).fetchall()
    return [r["plan_id"] for r in rows]


def _row_to_shop(row: Any, plan_ids: list[str]) -> dict[str, Any]:
    d = dict(row)
    d["shop_id"] = d.pop("id")
    d["plan_ids"] = plan_ids
    return d


class DBCatalogRepository:
    """基于 SQLite 的花艺商品目录仓储。

    提供与 MockRepository 完全一致的 4 个查询方法，供 tools/agent/api 调用。
    """

    def search_plans(
        self, keyword: str, requirement: Any | None = None
    ) -> list[dict[str, Any]]:
        conn = get_conn()
        kw = (keyword or "").lower()
        if not kw:
            rows = conn.execute("SELECT * FROM plans").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM plans WHERE lower(name) LIKE ? OR lower(desc) LIKE ?",
                (f"%{kw}%", f"%{kw}%"),
            ).fetchall()
            # 标签命中（轻量，覆盖关键词在标签而非名称的情况）
            tagged = conn.execute(
                "SELECT * FROM plans WHERE tags LIKE ?", (f"%{kw}%",)
            ).fetchall()
            seen = {r["id"] for r in rows}
            rows = list(rows) + [r for r in tagged if r["id"] not in seen]
        plans = [_row_to_plan(r) for r in rows]
        return _filter_plans_by_requirement(plans, requirement)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        conn = get_conn()
        row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return _row_to_plan(row) if row else None

    def list_shops(
        self,
        plan: dict[str, Any] | None,
        location: dict[str, float] | None = None,
        requirement: Any | None = None,
    ) -> list[dict[str, Any]]:
        conn = get_conn()
        shops = conn.execute("SELECT * FROM shops").fetchall()
        result: list[dict[str, Any]] = []
        for s in shops:
            plan_ids = _shop_plan_ids(conn, s["id"])
            result.append(_row_to_shop(s, plan_ids))

        plan_id = plan.get("plan_id") if plan else None

        def dist(s: dict[str, Any]) -> float:
            if location and s.get("lat") is not None:
                return _haversine(location["lat"], location["lng"], s["lat"], s["lng"])
            return float(s.get("distance_km", 999))

        def sort_key(s: dict[str, Any]) -> tuple:
            has_plan = 0 if (plan_id and plan_id in s.get("plan_ids", [])) else 1
            budget_penalty = 0
            if requirement and requirement.budget_min is not None:
                lo, hi = _parse_price_range(s.get("price_range", ""))
                if lo is not None:
                    rmin = requirement.budget_min
                    rmax = requirement.budget_max or requirement.budget_min
                    if hi < rmin or lo > rmax * 1.5:
                        budget_penalty = 1
            return (has_plan, budget_penalty, dist(s), -s.get("rating", 0))

        return sorted(result, key=sort_key)

    def get_shop(self, shop_id: str) -> dict[str, Any] | None:
        conn = get_conn()
        row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not row:
            return None
        return _row_to_shop(row, _shop_plan_ids(conn, shop_id))
