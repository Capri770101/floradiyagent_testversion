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
from typing import Any

from storage.db import get_conn, transaction

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
    {
        "plan_id": "P004",
        "name": "满天星小清新花束",
        "price": 99.0,
        "desc": "白绿满天星点缀尤加利，清爽治愈，日常陪伴首选。",
        "effect_image_url": "/generated/plan_P004.png",
        "merchant_name": "巷陌花集",
        "tags": ["满天星", "小清新", "平价"],
        "style": "自然",
        "category_id": "cat_daily",
    },
    {
        "plan_id": "P005",
        "name": "郁金香春日花束",
        "price": 189.0,
        "desc": "进口郁金香混搭洋桔梗，春日气息，告白送礼两相宜。",
        "effect_image_url": "/generated/plan_P005.png",
        "merchant_name": "兰庭花礼",
        "tags": ["郁金香", "春日", "告白"],
        "style": "浪漫",
        "category_id": "cat_love",
    },
    {
        "plan_id": "P006",
        "name": "牡丹雅韵礼盒",
        "price": 399.0,
        "desc": "重瓣牡丹礼盒装，华贵大气，适合商务馈赠与重要场合。",
        "effect_image_url": "/generated/plan_P006.png",
        "merchant_name": "兰庭花礼",
        "tags": ["牡丹", "礼盒", "高端"],
        "style": "中式",
        "category_id": "cat_holiday",
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
    {
        "shop_id": "S004",
        "name": "巷陌花集",
        "distance_km": 0.8,
        "price_range": "50-150",
        "rating": 4.5,
        "plan_ids": ["P004"],
        "lat": 22.565,
        "lng": 114.238,
        "intro": "街角平价花铺，日常随手一束，治愈每一天。",
    },
    {
        "shop_id": "S005",
        "name": "兰庭花礼",
        "distance_km": 2.1,
        "price_range": "150-500",
        "rating": 4.7,
        "plan_ids": ["P005", "P006"],
        "lat": 22.553,
        "lng": 114.248,
        "intro": "中高端花礼定制，名品花材与雅致包装。",
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
    """灌入种子数据（幂等：全部 INSERT OR IGNORE，可增量补种新增条目）。"""
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


# --------------------------------------------------------------------------- #
# 后台管理 CRUD（简易管理后台：方案 / 店铺的新增、编辑、删除）
# --------------------------------------------------------------------------- #


def create_plan(data: dict[str, Any]) -> dict[str, Any]:
    """新增方案，返回完整方案对象。plan_id 缺失时自动生成。"""
    import uuid as _uuid

    plan_id = (data.get("plan_id") or "").strip() or f"P{_uuid.uuid4().hex[:6]}"
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
    with transaction() as c:
        c.execute(
            """INSERT INTO plans
               (id, name, price, desc, effect_image_url, merchant_name, tags, style, category_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                plan_id,
                (data.get("name") or "未命名方案")[:60],
                float(data.get("price") or 0),
                (data.get("desc") or "")[:200],
                data.get("effect_image_url") or f"/generated/plan_{plan_id}.png",
                (data.get("merchant_name") or "")[:30],
                json.dumps(tags, ensure_ascii=False),
                (data.get("style") or "")[:20],
                data.get("category_id") or "cat_daily",
                _now(),
            ),
        )
    plan = get_conn().execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    return _row_to_plan(plan)


def update_plan(plan_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """更新方案字段（仅传入的字段），方案不存在返回 None。"""
    sets, vals = [], []
    if "name" in data:
        sets.append("name=?")
        vals.append((data["name"] or "")[:60])
    if "price" in data:
        sets.append("price=?")
        vals.append(float(data["price"] or 0))
    if "desc" in data:
        sets.append("desc=?")
        vals.append((data["desc"] or "")[:200])
    if "merchant_name" in data:
        sets.append("merchant_name=?")
        vals.append((data["merchant_name"] or "")[:30])
    if "style" in data:
        sets.append("style=?")
        vals.append((data["style"] or "")[:20])
    if "category_id" in data:
        sets.append("category_id=?")
        vals.append(data["category_id"] or "cat_daily")
    if "tags" in data:
        tags = data["tags"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        sets.append("tags=?")
        vals.append(json.dumps(tags, ensure_ascii=False))
    if "effect_image_url" in data:
        sets.append("effect_image_url=?")
        vals.append(data["effect_image_url"] or "")
    if not sets:
        return DBCatalogRepository().get_plan(plan_id)
    with transaction() as c:
        c.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id=?", vals + [plan_id])
    return DBCatalogRepository().get_plan(plan_id)


def delete_plan(plan_id: str) -> bool:
    """删除方案（连带清 shop_plans 关联）。返回是否真的删到了。"""
    conn = get_conn()
    if not conn.execute("SELECT id FROM plans WHERE id=?", (plan_id,)).fetchone():
        return False
    with transaction() as c:
        c.execute("DELETE FROM shop_plans WHERE plan_id=?", (plan_id,))
        c.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    return True


def create_shop(data: dict[str, Any]) -> dict[str, Any]:
    """新增店铺，返回完整店铺对象。shop_id 缺失时自动生成。"""
    import uuid as _uuid

    shop_id = (data.get("shop_id") or "").strip() or f"S{_uuid.uuid4().hex[:6]}"
    plan_ids = data.get("plan_ids") or []
    if isinstance(plan_ids, str):
        plan_ids = [p.strip() for p in plan_ids.replace("，", ",").split(",") if p.strip()]
    with transaction() as c:
        c.execute(
            """INSERT INTO shops
               (id, name, rating, distance_km, price_range, lat, lng, status, intro, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                shop_id,
                (data.get("name") or "未命名店铺")[:40],
                float(data.get("rating") or 4.5),
                float(data.get("distance_km") or 1.0),
                str(data.get("price_range") or "50-200"),
                float(data.get("lat") or 22.55),
                float(data.get("lng") or 114.24),
                (data.get("status") or "营业中")[:10],
                (data.get("intro") or "")[:120],
                _now(),
            ),
        )
        for pid in plan_ids:
            c.execute(
                "INSERT OR IGNORE INTO shop_plans(shop_id, plan_id) VALUES (?,?)",
                (shop_id, pid),
            )
    return DBCatalogRepository().get_shop(shop_id)


def update_shop(shop_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """更新店铺字段（仅传入的字段），店铺不存在返回 None。"""
    sets, vals = [], []
    if "name" in data:
        sets.append("name=?")
        vals.append((data["name"] or "")[:40])
    if "rating" in data:
        sets.append("rating=?")
        vals.append(float(data["rating"] or 0))
    if "distance_km" in data:
        sets.append("distance_km=?")
        vals.append(float(data["distance_km"] or 0))
    if "price_range" in data:
        sets.append("price_range=?")
        vals.append(str(data["price_range"] or ""))
    if "intro" in data:
        sets.append("intro=?")
        vals.append((data["intro"] or "")[:120])
    if "status" in data:
        sets.append("status=?")
        vals.append((data["status"] or "营业中")[:10])
    if "plan_ids" in data:
        plan_ids = data["plan_ids"]
        if isinstance(plan_ids, str):
            plan_ids = [p.strip() for p in plan_ids.replace("，", ",").split(",") if p.strip()]
        with transaction() as c:
            c.execute("DELETE FROM shop_plans WHERE shop_id=?", (shop_id,))
            for pid in plan_ids:
                c.execute(
                    "INSERT OR IGNORE INTO shop_plans(shop_id, plan_id) VALUES (?,?)",
                    (shop_id, pid),
                )
    if sets:
        with transaction() as c:
            c.execute(f"UPDATE shops SET {', '.join(sets)} WHERE id=?", vals + [shop_id])
    return DBCatalogRepository().get_shop(shop_id)


def delete_shop(shop_id: str) -> bool:
    """删除店铺（连带清 shop_plans 关联）。返回是否真的删到了。"""
    conn = get_conn()
    if not conn.execute("SELECT id FROM shops WHERE id=?", (shop_id,)).fetchone():
        return False
    with transaction() as c:
        c.execute("DELETE FROM shop_plans WHERE shop_id=?", (shop_id,))
        c.execute("DELETE FROM shops WHERE id=?", (shop_id,))
    return True


def list_plans() -> list[dict[str, Any]]:
    """后台管理用：返回全字段方案列表（含 style / category_id）。"""
    rows = get_conn().execute("SELECT * FROM plans ORDER BY created_at").fetchall()
    return [_row_to_plan(r) for r in rows]


def list_categories() -> list[dict[str, Any]]:
    """全部分类（按 sort 升序），供店铺详情页的分类菜单 / 管理后台使用。"""
    rows = get_conn().execute("SELECT * FROM categories ORDER BY sort ASC, id ASC").fetchall()
    return [dict(r) for r in rows]


def list_shops() -> list[dict[str, Any]]:
    """后台管理用：返回全字段店铺列表（含 plan_ids 关联）。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM shops ORDER BY created_at").fetchall()
    return [_row_to_shop(r, _shop_plan_ids(conn, r["id"])) for r in rows]


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
