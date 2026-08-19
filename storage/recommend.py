"""storage/recommend.py —— 个性化推荐（模块三：多信号融合规则推荐）。

score = w_distance * 距离分 + w_pref * 偏好分 + w_heat * 热度分

信号来源（全部真实 DB 数据，可解释、可 seed）：
- 距离：shops.lat/lng + 前端 getLocation() 传参，_haversine 真实距离归一化；
- 偏好：favorites（收藏方案）→ 风格/标签/价位带；orders（非取消）→ 方案风格 + 购买店铺；
- 热度：plans.rating/sold、shops.rating/sales（种子演示值，上线前可清空重灌）。

权重常量放 operations_config（键 recommend_weights），运营可调；未配置用 seed 默认。
无定位 / 无偏好时自动降级（距离分取中性值、偏好分为 0），永不报错、永不空返回。
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from storage.catalog import _haversine, _row_to_plan, _row_to_shop, _shop_plan_ids
from storage.config import DEFAULTS, K_REC_WEIGHTS, get_config
from storage.db import get_conn

#: 价格带划分（元）：偏好按方案价格落带匹配
PRICE_BANDS = [(0, 120), (121, 220), (221, 350), (351, 10_000)]

#: 风格词表分组：DIY 方案 style 是自由文本（如「北欧」），catalog 是固定词表（如「简约/ins」），
#: 匹配前先归一化到分组，避免 exact-match 永远落空（模块三「同风格方案」命中率）。
STYLE_GROUPS: dict[str, list[str]] = {
    "韩式": ["韩式"],
    "欧式": ["欧式"],
    "法式": ["法式"],
    "田园": ["田园"],
    "自然": ["自然", "野趣"],
    "简约": ["简约", "ins", "北欧", "极简", "现代", "高级"],
    "复古": ["复古", "法式复古"],
    "浪漫": ["浪漫", "告白"],
    "中式": ["中式", "国风"],
    "日式": ["日式", "和风"],
}


def _style_group(style: Any) -> str:
    """把任意风格词归一化到 STYLE_GROUPS 的分组名；未收录词按自身（首词）分组。"""
    if not style:
        return ""
    s = str(style).strip()
    for group, aliases in STYLE_GROUPS.items():
        if s in aliases:
            return group
    return s.split()[0] if s else ""


def _weights() -> dict[str, float]:
    w = get_config(K_REC_WEIGHTS, DEFAULTS[K_REC_WEIGHTS])
    return {
        "w_distance": float(w.get("w_distance", 0.4)),
        "w_pref": float(w.get("w_pref", 0.4)),
        "w_heat": float(w.get("w_heat", 0.2)),
    }


def _price_band(price: Any) -> int:
    try:
        p = float(price or 0)
    except (TypeError, ValueError):
        p = 0
    for i, (lo, hi) in enumerate(PRICE_BANDS):
        if lo <= p <= hi:
            return i
    return 0


# --------------------------------------------------------------------------- #
# 偏好提取：favorites + orders → 风格 / 标签 / 价位带 / 店铺
# --------------------------------------------------------------------------- #


def extract_preferences(user_id: str | None) -> dict[str, Any]:
    """从收藏与历史订单提取用户偏好画像（无用户/无数据 → 全空画像）。"""
    styles: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    bands: Counter[int] = Counter()
    shops: Counter[str] = Counter()
    if not user_id:
        return {"styles": {}, "tags": {}, "bands": {}, "shops": {}}
    conn = get_conn()
    favs = conn.execute(
        "SELECT p.style, p.tags, p.price FROM favorites f "
        "JOIN plans p ON p.id = f.plan_id WHERE f.user_id=?",
        (user_id,),
    ).fetchall()
    for r in favs:
        if r["style"]:
            styles[r["style"]] += 1
        bands[_price_band(r["price"])] += 1
        try:
            for t in json.loads(r["tags"]) if r["tags"] else []:
                tags[t] += 1
        except (json.JSONDecodeError, TypeError):
            pass
    orders = conn.execute(
        "SELECT order_id, shop_id, items FROM orders o WHERE o.user_id=? AND o.status <> 'canceled'",
        (user_id,),
    ).fetchall()
    plan_ids: list[str] = []
    for o in orders:
        if o["shop_id"]:
            shops[o["shop_id"]] += 1
        try:
            for it in json.loads(o["items"]) if o["items"] else []:
                if isinstance(it, dict) and it.get("plan_id"):
                    plan_ids.append(it["plan_id"])
        except (json.JSONDecodeError, TypeError):
            pass
    if plan_ids:
        ph = ",".join("?" * len(plan_ids))
        for r in conn.execute(
            f"SELECT style, price FROM plans WHERE id IN ({ph})", plan_ids
        ).fetchall():
            if r["style"]:
                styles[r["style"]] += 1
            if r["price"] is not None:
                bands[_price_band(r["price"])] += 1
    return {"styles": dict(styles), "tags": dict(tags), "bands": dict(bands), "shops": dict(shops)}


def _top_styles(prefs: dict[str, Any]) -> list[str]:
    return [s for s, _ in sorted(prefs["styles"].items(), key=lambda kv: -kv[1])]


def _top_bands(prefs: dict[str, Any]) -> list[int]:
    return [b for b, _ in sorted(prefs["bands"].items(), key=lambda kv: -kv[1])]


# --------------------------------------------------------------------------- #
# 方案推荐
# --------------------------------------------------------------------------- #


def recommend_plans(
    user_id: str | None,
    lat: float | None = None,
    lng: float | None = None,
    limit: int = 6,
    style: str | None = None,
) -> list[dict[str, Any]]:
    """个性化方案推荐：距离 + 偏好 + 热度融合排序。

    style 传值时对同风格方案加权（DIY 详情页「同风格方案」推荐位）。
    """
    conn = get_conn()
    prefs = extract_preferences(user_id)
    style_groups = {_style_group(s) for s in _top_styles(prefs)}
    bands = _top_bands(prefs)
    style_param_group = _style_group(style)
    w = _weights()
    rows = conn.execute("SELECT * FROM plans").fetchall()
    plans = [_row_to_plan(r) for r in rows]
    if not plans:
        return []
    max_sold = max(float(p.get("sold") or 0) for p in plans) or 1.0
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in plans:
        # 距离分：该方案承载店铺的真实距离；无定位 → 中性 0.5（不惩罚也不加分）
        dist = 0.5
        if lat is not None and lng is not None:
            shop_row = conn.execute(
                "SELECT lat, lng FROM shops WHERE id=?",
                (p.get("shop_id") or _shop_of(conn, p["plan_id"]),),
            ).fetchone()
            if shop_row and shop_row["lat"] is not None:
                d = _haversine(lat, lng, shop_row["lat"], shop_row["lng"])
                dist = max(0.0, 1.0 - d / 5.0)
        # 偏好分：风格命中 0.5 + 标签命中 0.3 + 价位带命中 0.2
        pref = 0.0
        if style_groups and _style_group(p.get("style")) in style_groups:
            pref += 0.5
        if prefs["tags"] and any(t in prefs["tags"] for t in (p.get("tags") or [])):
            pref += 0.3
        if bands and _price_band(p.get("price")) in bands:
            pref += 0.2
        if style and style_param_group and _style_group(p.get("style")) == style_param_group:
            pref += 0.3  # 同风格加权（软加权：仍保留其他风格兜底；词表分组归一化后命中）
        # 热度分：已售（主）+ 评分
        heat = 0.6 * (float(p.get("sold") or 0) / max_sold) + 0.4 * (float(p.get("rating") or 4.8) / 5.0)
        score = w["w_distance"] * dist + w["w_pref"] * pref + w["w_heat"] * heat
        scored.append((score, p))
    scored.sort(key=lambda kv: (-kv[0], -float(kv[1].get("sold") or 0)))
    return [p for _, p in scored[: max(1, int(limit or 6))]]


#: 当季臻选（Signature Collection）策展权重：角标气质 0.4 + 热度 0.4 + 距离 0.2
SIG_W_LABEL, SIG_W_HEAT, SIG_W_DIST = 0.4, 0.4, 0.2

#: 角标气质分（与 routers/common._plan_label 同规则）：Premium=高价精品 / Limited / New
_LABEL_BONUS = {"Premium": 0.5, "Limited": 0.3, "New": 0.1}


def _label_of(price: Any) -> str:
    """方案角标（与前端 PlanTag 同规则，storage 侧自足，避免依赖 routers）。"""
    try:
        p = float(price or 0)
    except (TypeError, ValueError):
        p = 0
    return "Premium" if p >= 300 else "Limited" if p >= 150 else "New"


def recommend_signature(
    lat: float | None = None,
    lng: float | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """当季臻选：策展式推荐（不依赖用户画像）。

    score = w_label*角标气质 + w_heat*热度 + w_dist*距离；
    距定位越近的同气质方案越靠前；无定位 → 距离取中性 0.5。
    返回方案卡并附带 `dist_km`（无定位/无坐标时为 None，前端按需展示）。
    """
    conn = get_conn()
    rows = conn.execute("SELECT * FROM plans").fetchall()
    plans = [_row_to_plan(r) for r in rows]
    if not plans:
        return []
    max_sold = max(float(p.get("sold") or 0) for p in plans) or 1.0
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in plans:
        dist = 0.5
        dist_km: float | None = None
        if lat is not None and lng is not None:
            shop_row = conn.execute(
                "SELECT lat, lng FROM shops WHERE id=?",
                (p.get("shop_id") or _shop_of(conn, p["plan_id"]),),
            ).fetchone()
            if shop_row and shop_row["lat"] is not None:
                d = _haversine(lat, lng, shop_row["lat"], shop_row["lng"])
                dist_km = d
                dist = max(0.0, 1.0 - d / 5.0)
        heat = 0.6 * (float(p.get("sold") or 0) / max_sold) + 0.4 * (float(p.get("rating") or 4.8) / 5.0)
        score = (
            SIG_W_LABEL * _LABEL_BONUS.get(_label_of(p.get("price")), 0.1)
            + SIG_W_HEAT * heat
            + SIG_W_DIST * dist
        )
        p = dict(p)
        p["dist_km"] = dist_km
        scored.append((score, p))
    scored.sort(key=lambda kv: (-kv[0], -float(kv[1].get("sold") or 0)))
    return [p for _, p in scored[: max(1, int(limit or 3))]]


def _shop_of(conn, plan_id: str) -> str | None:
    row = conn.execute("SELECT shop_id FROM shop_plans WHERE plan_id=? LIMIT 1", (plan_id,)).fetchone()
    return row["shop_id"] if row else None


# --------------------------------------------------------------------------- #
# 店铺推荐
# --------------------------------------------------------------------------- #


def recommend_shops(
    user_id: str | None,
    lat: float | None = None,
    lng: float | None = None,
    limit: int = 6,
    shop_id: str | None = None,
) -> list[dict[str, Any]]:
    """附近同类店铺推荐：距离 + 偏好（购买过的店/风格承载）+ 热度。

    shop_id 传值时排除自身，并给同价位带（同类）店铺小幅加权（店铺详情页推荐位）。
    """
    conn = get_conn()
    prefs = extract_preferences(user_id)
    style_groups = {_style_group(s) for s in _top_styles(prefs)}
    owned = set(prefs["shops"])
    w = _weights()
    shops_rows = conn.execute("SELECT * FROM shops").fetchall()
    shops = [_row_to_shop(r, _shop_plan_ids(conn, r["id"])) for r in shops_rows]
    if not shops:
        return []
    max_sales = max(float(s.get("sales") or 0) for s in shops) or 1.0
    self_shop = None
    if shop_id:
        self_shop = next((s for s in shops if s["shop_id"] == shop_id), None)
        shops = [s for s in shops if s["shop_id"] != shop_id]
    scored: list[tuple[float, dict[str, Any]]] = []
    for s in shops:
        dist = 0.5
        if lat is not None and lng is not None and s.get("lat") is not None:
            d = _haversine(lat, lng, s["lat"], s["lng"])
            dist = max(0.0, 1.0 - d / 5.0)
        pref = 0.0
        if s["shop_id"] in owned:
            pref += 0.5  # 历史购买过的店
        if style_groups:
            carried = conn.execute(
                "SELECT DISTINCT p.style FROM shop_plans sp JOIN plans p ON p.id=sp.plan_id "
                "WHERE sp.shop_id=? AND sp.status='on'",
                (s["shop_id"],),
            ).fetchall()
            if any(_style_group(r["style"]) in style_groups for r in carried):
                pref += 0.5  # 店内在售方案命中用户风格偏好（按词表分组）
        if self_shop and s.get("price_range") == self_shop.get("price_range"):
            pref += 0.15  # 同类（同价位带）加权
        heat = 0.5 * (float(s.get("rating") or 4.8) / 5.0) + 0.5 * (float(s.get("sales") or 0) / max_sales)
        score = w["w_distance"] * dist + w["w_pref"] * pref + w["w_heat"] * heat
        scored.append((score, s))
    scored.sort(key=lambda kv: (-kv[0], -float(kv[1].get("rating") or 0)))
    return [s for _, s in scored[: max(1, int(limit or 6))]]