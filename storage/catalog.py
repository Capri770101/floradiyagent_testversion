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
    {"id": "cat_giftbox", "name": "花礼礼盒", "sort": 4},
    {"id": "cat_green", "name": "绿植花艺", "sort": 5},
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
    {
        "plan_id": "P007",
        "name": "百合雅致花束",
        "price": 259.0,
        "desc": "白百合混搭洋桔梗，素净雅致，探望长辈与乔迁皆宜。",
        "effect_image_url": "/generated/plan_P007.png",
        "merchant_name": "兰庭花礼",
        "tags": ["百合", "雅致", "探望"],
        "style": "简约",
        "category_id": "cat_holiday",
    },
    {
        "plan_id": "P008",
        "name": "绣球梦幻花束",
        "price": 229.0,
        "desc": "蓝紫绣球点缀尤加利叶，清新梦幻，日常陪伴首选。",
        "effect_image_url": "/generated/plan_P008.png",
        "merchant_name": "山茶花集",
        "tags": ["绣球", "清新", "日常"],
        "style": "自然",
        "category_id": "cat_daily",
    },
    {
        "plan_id": "P009",
        "name": "芍药繁花礼盒",
        "price": 359.0,
        "desc": "重瓣芍药配进口玫瑰礼盒，华丽丰盛，纪念日与表白佳选。",
        "effect_image_url": "/generated/plan_P009.png",
        "merchant_name": "玫瑰花园",
        "tags": ["芍药", "玫瑰", "礼盒"],
        "style": "复古",
        "category_id": "cat_love",
    },
    {
        "plan_id": "P010",
        "name": "满天星永生花盒",
        "price": 199.0,
        "desc": "永生花工艺，长久陪伴不凋谢，浪漫告白心意之选。",
        "effect_image_url": "/generated/plan_P010.png",
        "merchant_name": "花漾工坊",
        "tags": ["永生花", "礼盒", "告白"],
        "style": "ins",
        "category_id": "cat_giftbox",
    },
    {
        "plan_id": "P011",
        "name": "绿萝桌面盆栽",
        "price": 69.0,
        "desc": "小盆绿萝配白瓷盆，净化空气，办公室与桌面小清新。",
        "effect_image_url": "/generated/plan_P011.png",
        "merchant_name": "绿野花艺",
        "tags": ["绿植", "桌面", "平价"],
        "style": "自然",
        "category_id": "cat_green",
    },
    {
        "plan_id": "P012",
        "name": "缤纷花篮",
        "price": 329.0,
        "desc": "玫瑰康乃馨混搭花篮，缤纷热烈，乔迁开业送礼首选。",
        "effect_image_url": "/generated/plan_P012.png",
        "merchant_name": "花间小筑",
        "tags": ["花篮", "混搭", "乔迁"],
        "style": "欧式",
        "category_id": "cat_giftbox",
    },
    {
        "plan_id": "P013",
        "name": "香槟玫瑰告白花束",
        "price": 229.0,
        "desc": "香槟玫瑰混搭洋桔梗，温柔不张扬，告白纪念两相宜。",
        "effect_image_url": "/generated/plan_P013.png",
        "merchant_name": "花语花集",
        "tags": ["香槟玫瑰", "告白", "温柔"],
        "style": "韩式",
        "category_id": "cat_love",
    },
    {
        "plan_id": "P014",
        "name": "禅意竹艺插花",
        "price": 269.0,
        "desc": "日式禅意插花，竹器留白，清雅克制，适合书房与茶室。",
        "effect_image_url": "/generated/plan_P014.png",
        "merchant_name": "半夏花房",
        "tags": ["日式", "禅意", "插花"],
        "style": "日式",
        "category_id": "cat_giftbox",
    },
    {
        "plan_id": "P015",
        "name": "复古玫瑰礼盒",
        "price": 459.0,
        "desc": "复古色系玫瑰配丝绒礼盒，浓郁华美，宴会婚礼皆宜。",
        "effect_image_url": "/generated/plan_P015.png",
        "merchant_name": "暮色花园",
        "tags": ["复古", "玫瑰", "礼盒"],
        "style": "复古",
        "category_id": "cat_giftbox",
    },
    {
        "plan_id": "P016",
        "name": "野趣雏菊小花束",
        "price": 79.0,
        "desc": "小雏菊配尤加利叶，野趣清新，随手一束治愈日常。",
        "effect_image_url": "/generated/plan_P016.png",
        "merchant_name": "拾野花铺",
        "tags": ["雏菊", "野趣", "平价"],
        "style": "自然",
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
        "plan_ids": ["P001", "P002", "P010"],
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
        "plan_ids": ["P003", "P011"],
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
        "plan_ids": ["P001", "P002", "P003", "P009", "P012"],
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
        "plan_ids": ["P004", "P008"],
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
        "plan_ids": ["P005", "P006", "P007"],
        "lat": 22.553,
        "lng": 114.248,
        "intro": "中高端花礼定制，名品花材与雅致包装。",
    },
    {
        "shop_id": "S006",
        "name": "玫瑰花园",
        "distance_km": 4.6,
        "price_range": "120-400",
        "rating": 4.7,
        "plan_ids": ["P002", "P009"],
        "lat": 22.541,
        "lng": 114.055,
        "intro": "玫瑰主题花店，全品类玫瑰与法式礼盒。",
    },
    {
        "shop_id": "S007",
        "name": "山茶花集",
        "distance_km": 5.2,
        "price_range": "60-200",
        "rating": 4.6,
        "plan_ids": ["P004", "P008"],
        "lat": 22.533,
        "lng": 113.930,
        "intro": "南山街角花店，小众花材与清新手作。",
    },
    {
        "shop_id": "S008",
        "name": "花间小筑",
        "distance_km": 3.1,
        "price_range": "200-600",
        "rating": 4.9,
        "plan_ids": ["P006", "P009", "P012"],
        "lat": 22.560,
        "lng": 114.131,
        "intro": "高端花艺定制，宴会布置与定制花篮。",
    },
    {
        "shop_id": "S009",
        "name": "花语花集(福田CBD店)",
        "distance_km": 1.6,
        "price_range": "120-350",
        "rating": 4.8,
        "plan_ids": ["P013", "P005"],
        "lat": 22.542,
        "lng": 114.057,
        "intro": "写字楼商圈花店，韩式温柔风，告白生日人气之选。",
    },
    {
        "shop_id": "S010",
        "name": "半夏花房",
        "distance_km": 2.8,
        "price_range": "150-450",
        "rating": 4.7,
        "plan_ids": ["P014", "P007"],
        "lat": 22.549,
        "lng": 114.066,
        "intro": "日式禅意花房，极简留白，雅致礼盒与茶室插花。",
    },
    {
        "shop_id": "S011",
        "name": "暮色花园",
        "distance_km": 4.2,
        "price_range": "250-800",
        "rating": 4.9,
        "plan_ids": ["P015", "P009"],
        "lat": 22.535,
        "lng": 114.072,
        "intro": "复古法式花艺工作室，婚礼宴会布置与高端花礼。",
    },
    {
        "shop_id": "S012",
        "name": "拾野花铺",
        "distance_km": 1.9,
        "price_range": "50-160",
        "rating": 4.5,
        "plan_ids": ["P016", "P004"],
        "lat": 22.555,
        "lng": 114.060,
        "intro": "街角野趣花铺，自然系小花束，治愈日常。",
    },
    {
        "shop_id": "S013",
        "name": "白昼花研所",
        "distance_km": 2.3,
        "price_range": "100-300",
        "rating": 4.6,
        "plan_ids": ["P013", "P010"],
        "lat": 22.546,
        "lng": 114.052,
        "intro": "明亮 ins 风花店，毕业季与圣诞节日花束人气店。",
    },
    {
        "shop_id": "S014",
        "name": "云上花礼",
        "distance_km": 5.6,
        "price_range": "200-700",
        "rating": 4.8,
        "plan_ids": ["P006", "P012"],
        "lat": 22.531,
        "lng": 114.080,
        "intro": "高端商务花礼定制，企业订花与重要节日礼赠。",
    },
    {
        "shop_id": "S015",
        "name": "南巷花事",
        "distance_km": 0.9,
        "price_range": "40-130",
        "rating": 4.4,
        "plan_ids": ["P016", "P011"],
        "lat": 22.561,
        "lng": 114.050,
        "intro": "平价社区花店，日常陪伴与探病花束随手可得。",
    },
    {
        "shop_id": "S016",
        "name": "半亩花园",
        "distance_km": 3.4,
        "price_range": "90-280",
        "rating": 4.7,
        "plan_ids": ["P011", "P008", "P016"],
        "lat": 22.553,
        "lng": 114.043,
        "intro": "北欧自然风花园店，绿植与居家花艺搭配。",
    },
]

# 生成占位效果图的方案（与 MockRepository 保持一致）
_PLACEHOLDER_PLANS = ["P001", "P002", "P003", "P007", "P008", "P009", "P010", "P011", "P012", "P013", "P014", "P015", "P016"]

# 商家智库档案（1:1 shops）。styles/scenes 的 style_id/scene_id 分别引用
# knowledge/styles.json（S_*）与 knowledge/scenes.json（SC_*）的实体 id。
_SHOP_PROFILES = [
    {
        "shop_id": "S001",
        "brand_story": "发源于盐田老街区的社区花店，靠精准守时的同城速递与精致包装积累口碑，是附近居民节日订花的首选。",
        "price_level": "中端",
        "packaging": "雾面韩素纸 + 雪纺丝带，强调留白与高级感。",
        "services": ["同城速递", "节日定制", "每周一花订阅"],
        "strengths": "同城准时送达、节日主题花束成熟、包装精致",
        "keywords": "盐田,同城速递,节日花束,康乃馨,精致包装",
        "styles": [("S_KOREAN", 1), ("S_INS", 2)],
        "scenes": [("SC_MOTHER", 1), ("SC_VALENTINE", 2), ("SC_ANNIVERSARY", 2)],
    },
    {
        "shop_id": "S002",
        "name_hint": "绿野花艺",
        "brand_story": "主打自然风花艺与绿植的清新小店，鲜切花与绿植搭配是招牌，适合喜欢清新日常的顾客。",
        "price_level": "经济",
        "packaging": "牛皮纸 + 麻绳，或透明玻璃纸露出花材质感。",
        "services": ["同城速递", "绿植养护咨询"],
        "strengths": "自然野趣、绿植与鲜切花搭配、性价比高",
        "keywords": "绿植,自然风,桌面盆栽,平价",
        "styles": [("S_NATURAL", 1), ("S_NORDIC", 2)],
        "scenes": [("SC_SELF", 1), ("SC_HOUSEWARMING", 2), ("SC_GETWELL", 2)],
    },
    {
        "shop_id": "S003",
        "name_hint": "都市花房",
        "brand_story": "定位高端花艺空间，主理人出身婚礼花艺，节日礼盒与商务花艺并重，服务品质与花材等级在商圈内有口皆碑。",
        "price_level": "高端",
        "packaging": "品牌定制礼盒与缎带，仪式感强，适合商务馈赠。",
        "services": ["商务订花", "节日礼盒", "同城速递"],
        "strengths": "高端花材、商务花艺成熟、礼盒仪式感强",
        "keywords": "高端,商务,礼盒,都市,节日",
        "styles": [("S_VINTAGE", 1), ("S_JAPANESE", 2)],
        "scenes": [("SC_ANNIVERSARY", 1), ("SC_WEDDING", 2), ("SC_MOTHER", 2)],
    },
    {
        "shop_id": "S004",
        "name_hint": "巷陌花集",
        "brand_story": "街角平价花铺，主打日常随手一束的小确幸，用不高的预算治愈每一天，附近上班族午休常来带一束。",
        "price_level": "经济",
        "packaging": "简洁牛皮纸手包，回归花材本身。",
        "services": ["同城速递", "散花零售"],
        "strengths": "平价亲民、日常花束、街角可达",
        "keywords": "平价,日常,街角,小清新,满天星",
        "styles": [("S_NATURAL", 1), ("S_INS", 2)],
        "scenes": [("SC_SELF", 1), ("SC_GETWELL", 2), ("SC_APOLOGY", 2)],
    },
    {
        "shop_id": "S005",
        "name_hint": "兰庭花礼",
        "brand_story": "中高端花礼定制店，坚持选用名品花材（进口郁金香、重瓣牡丹），雅致包装与花艺功力兼备，重要礼赠场合的老牌选择。",
        "price_level": "高端",
        "packaging": "雅致花纸与缎带，色系统一克制，凸显名品花材。",
        "services": ["花礼定制", "同城速递", "企业团购"],
        "strengths": "名品花材、花礼定制经验丰富、雅致耐看",
        "keywords": "名品,郁金香,牡丹,雅致,定制",
        "styles": [("S_JAPANESE", 1), ("S_NORDIC", 2)],
        "scenes": [("SC_CONFESS", 1), ("SC_BIRTHDAY", 2), ("SC_ANNIVERSARY", 2)],
    },
    {
        "shop_id": "S006",
        "name_hint": "玫瑰花园",
        "brand_story": "玫瑰主题花店，专注全品类玫瑰与法式礼盒，从肯尼亚玫瑰到国产多头玫瑰一应俱全，浪漫场合的人气选择。",
        "price_level": "中端",
        "packaging": "法式礼盒与丝绒缎带，浓郁浪漫。",
        "services": ["同城速递", "节日定制", "花束加急"],
        "strengths": "全品类玫瑰、法式礼盒、告白氛围感强",
        "keywords": "玫瑰,法式,礼盒,告白,浪漫",
        "styles": [("S_VINTAGE", 1), ("S_KOREAN", 2)],
        "scenes": [("SC_VALENTINE", 1), ("SC_ANNIVERSARY", 1), ("SC_CONFESS", 2)],
    },
    {
        "shop_id": "S007",
        "name_hint": "山茶花集",
        "brand_story": "南山街角的小众花店，偏爱少见花材与清新手作，花艺师每周上新不重样，是花艺爱好者的淘货地。",
        "price_level": "经济",
        "packaging": "手作感包装，随花材气质变化，常有惊喜。",
        "services": ["散花零售", "花艺小课"],
        "strengths": "小众花材、手作感、上新快",
        "keywords": "小众,绣球,手作,清新,南山",
        "styles": [("S_NATURAL", 1), ("S_NORDIC", 2)],
        "scenes": [("SC_SELF", 1), ("SC_BIRTHDAY", 2), ("SC_GETWELL", 2)],
    },
    {
        "shop_id": "S008",
        "name_hint": "花间小筑",
        "brand_story": "高端花艺定制工作室，主攻宴会布置与定制花篮，承接过多场高端宴会与开业典礼，作品大气华丽。",
        "price_level": "高端",
        "packaging": "定制级包装与花器，整体造型完整华丽。",
        "services": ["宴会布置", "开业花篮", "花艺定制"],
        "strengths": "宴会布置经验丰富、定制花篮、作品大气",
        "keywords": "宴会,花篮,开业,乔迁,高端定制",
        "styles": [("S_VINTAGE", 1), ("S_JAPANESE", 2)],
        "scenes": [("SC_WEDDING", 1), ("SC_HOUSEWARMING", 2), ("SC_NEWYEAR", 2)],
    },
    {
        "shop_id": "S009",
        "name_hint": "花语花集",
        "brand_story": "福田 CBD 商圈里的韩式花店，主打温柔克制的告白与生日花束，写字楼白领的浪漫补给站。",
        "price_level": "中端",
        "packaging": "雾面韩素纸 + 雪纺带，低饱和配色，ins 感十足。",
        "services": ["同城速递", "节日定制", "写字楼配送"],
        "strengths": "韩式温柔风、商圈配送快、告白花束人气高",
        "keywords": "CBD,韩式,香槟玫瑰,告白,生日",
        "styles": [("S_KOREAN", 1), ("S_INS", 2)],
        "scenes": [("SC_CONFESS", 1), ("SC_BIRTHDAY", 1), ("SC_VALENTINE", 2)],
    },
    {
        "shop_id": "S010",
        "name_hint": "半夏花房",
        "brand_story": "日式禅意花房，坚持极简留白与竹器插花，把茶室与书房的清雅带进日常，适合偏爱克制美学的顾客。",
        "price_level": "中高端",
        "packaging": "竹器、陶器与素色和纸，去繁就简。",
        "services": ["插花课程", "茶室花艺", "同城速递"],
        "strengths": "日式禅意、竹器插花、极简留白",
        "keywords": "日式,禅意,插花,极简,留白",
        "styles": [("S_JAPANESE", 1), ("S_NORDIC", 2)],
        "scenes": [("SC_ANNIVERSARY", 1), ("SC_HOUSEWARMING", 2), ("SC_SELF", 2)],
    },
    {
        "shop_id": "S011",
        "name_hint": "暮色花园",
        "brand_story": "复古法式花艺工作室，主理人师从欧洲花艺学校，擅用浓郁色系与丝绒质感，婚礼与宴会布置是绝对强项。",
        "price_level": "高端",
        "packaging": "丝绒缎带与复古花纸，浓郁华美。",
        "services": ["婚礼布置", "宴会花艺", "高端花礼定制"],
        "strengths": "法式复古、婚礼宴会布置、花材等级高",
        "keywords": "复古,法式,婚礼,宴会,丝绒",
        "styles": [("S_VINTAGE", 1), ("S_NATURAL", 2)],
        "scenes": [("SC_WEDDING", 1), ("SC_VALENTINE", 2), ("SC_ANNIVERSARY", 2)],
    },
    {
        "shop_id": "S012",
        "name_hint": "拾野花铺",
        "brand_story": "街角野趣花铺，像从田野里采撷来的小花束，清新治愈又不贵，是年轻人随手悦己的首选。",
        "price_level": "经济",
        "packaging": "牛皮纸松散包裹，露出枝干线条。",
        "services": ["散花零售", "同城速递"],
        "strengths": "野趣自然、价格亲民、治愈感强",
        "keywords": "野趣,雏菊,平价,治愈,自然",
        "styles": [("S_NATURAL", 1), ("S_NORDIC", 2)],
        "scenes": [("SC_SELF", 1), ("SC_GETWELL", 2), ("SC_APOLOGY", 2)],
    },
    {
        "shop_id": "S013",
        "name_hint": "白昼花研所",
        "brand_story": "明亮 ins 风花店，色彩活泼拍照出片，毕业季与圣诞节的节日花束是店里最忙的时候。",
        "price_level": "中端",
        "packaging": "亮色包装纸与可爱贴纸，ins 打卡感强。",
        "services": ["节日定制", "拍照打卡布置", "同城速递"],
        "strengths": "ins 风出片、毕业季圣诞节点人气、色彩活泼",
        "keywords": "ins,明亮,毕业,圣诞,打卡",
        "styles": [("S_INS", 1), ("S_NORDIC", 2)],
        "scenes": [("SC_GRADUATION", 1), ("SC_CHRISTMAS", 1), ("SC_BIRTHDAY", 2)],
    },
    {
        "shop_id": "S014",
        "name_hint": "云上花礼",
        "brand_story": "高端商务花礼定制商，服务多家企业的年度礼赠与年会花艺，讲究排面与交付准时。",
        "price_level": "高端",
        "packaging": "品牌礼盒与烫金缎带，商务仪式感拉满。",
        "services": ["企业订花", "年会花艺", "节日礼赠"],
        "strengths": "企业客户成熟、礼赠体面、交付准时",
        "keywords": "商务,企业,礼赠,高端,牡丹",
        "styles": [("S_JAPANESE", 1), ("S_VINTAGE", 2)],
        "scenes": [("SC_NEWYEAR", 1), ("SC_TEACHER", 1), ("SC_HOUSEWARMING", 2)],
    },
    {
        "shop_id": "S015",
        "name_hint": "南巷花事",
        "brand_story": "社区平价花店，就在南巷口，买菜路过的功夫就能带一束回家，探病、道歉、日常都需要它。",
        "price_level": "经济",
        "packaging": "简素花纸快包，快速不将就。",
        "services": ["同城速递", "散花零售"],
        "strengths": "社区可达、平价、日常需求全覆盖",
        "keywords": "社区,平价,日常,探病,随手",
        "styles": [("S_NATURAL", 1), ("S_INS", 2)],
        "scenes": [("SC_SELF", 1), ("SC_GETWELL", 2), ("SC_BIRTHDAY", 2)],
    },
    {
        "shop_id": "S016",
        "name_hint": "半亩花园",
        "brand_story": "北欧自然风花园店，绿植与居家花艺的搭配尤其擅长，搬家乔迁与家居软装是主场景。",
        "price_level": "中端",
        "packaging": "素色牛皮纸与玻璃花器，突出材质与线条。",
        "services": ["绿植配送", "家居花艺", "乔迁布置"],
        "strengths": "北欧风、绿植花艺搭配、乔迁场景专业",
        "keywords": "北欧,绿植,居家,乔迁,自然",
        "styles": [("S_NORDIC", 1), ("S_NATURAL", 2)],
        "scenes": [("SC_HOUSEWARMING", 1), ("SC_SELF", 2), ("SC_MOTHER", 2)],
    },
]


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
            # 评分/已售：种子演示值（确定性，正式上线由订单统计，可清空重灌）
            rating = p.get("rating", round(4.5 + (abs(hash(p["plan_id"])) % 5) * 0.1, 1))
            sold = p.get("sold", 120 + (abs(hash(p["plan_id"])) % 600))
            # 推荐理由：优先方案自带文案，否则由 desc 确定性生成后落库（详情页 aiReason 唯一来源）
            reason = p.get("ai_reason") or f"根据你的需求，这束「{p['name']}」{p.get('desc', '')}"
            conn.execute(
                """INSERT OR IGNORE INTO plans
                   (id, name, price, desc, effect_image_url, merchant_name, tags, style, category_id, rating, sold, ai_reason, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p["plan_id"], p["name"], p["price"], p["desc"], p["effect_image_url"],
                    p["merchant_name"], json.dumps(p["tags"], ensure_ascii=False),
                    p["style"], p["category_id"], rating, sold, reason, _now(),
                ),
            )
        for s in _SHOPS:
            # 经营信息：种子演示值（确定性推导后落库；上线前可清空重灌真实数据）
            m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(s.get("price_range", "")))
            lo = float(m.group(1)) if m else None
            _d = float(s.get("distance_km") or 1.0)
            min_delivery = (int(lo) // 10 * 10) if lo else 30
            delivery_fee = 3 if _d <= 1 else 5 if _d <= 2.5 else 8
            zone = "盐田"
            z = re.search(r"\((.+?)店\)", str(s.get("name", "")))
            if z:
                zone = z.group(1)
            addr_no = 8 + (abs(hash(s.get("shop_id", ""))) % 88)
            delivery_time = f"约{int(10 + _d * 4)}分钟"  # 配送时长：按距离确定性推导后落库（商家后台可改）
            conn.execute(
                """INSERT OR IGNORE INTO shops
                   (id, name, rating, distance_km, price_range, lat, lng, status, intro,
                    sales, min_delivery, delivery_fee, hours, delivery_time, address, notice, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    s["shop_id"], s["name"], s["rating"], s["distance_km"], s["price_range"],
                    s["lat"], s["lng"], "营业中", s["intro"],
                    200 + (abs(hash(s.get("shop_id", ""))) % 800),  # 月售（演示）
                    min_delivery, delivery_fee, "09:00 - 21:00", delivery_time,
                    f"深圳市{zone}区海景路 {addr_no} 号（示例地址）",
                    s.get("intro", "专注鲜花定制与同城速递，包装精致、准时送达。"),
                    _now(),
                ),
            )
            for pid in s["plan_ids"]:
                conn.execute(
                    "INSERT OR IGNORE INTO shop_plans(shop_id, plan_id) VALUES (?,?)",
                    (s["shop_id"], pid),
                )
        # 回填旧库新增列：INSERT OR IGNORE 不会更新既有行；演示值仅在缺省时写入，
        # 不影响商家后台已维护的真实字段（上线前清空重灌即可换真实数据）。
        for p in _PLANS:
            rating = p.get("rating", round(4.5 + (abs(hash(p["plan_id"])) % 5) * 0.1, 1))
            sold = p.get("sold", 120 + (abs(hash(p["plan_id"])) % 600))
            reason = p.get("ai_reason") or f"根据你的需求，这束「{p['name']}」{p.get('desc', '')}"
            conn.execute(
                "UPDATE plans SET rating=?, sold=? WHERE id=? AND (sold IS NULL OR sold=0)",
                (rating, sold, p["plan_id"]),
            )
            conn.execute(
                "UPDATE plans SET ai_reason=? WHERE id=? AND (ai_reason IS NULL OR ai_reason='')",
                (reason, p["plan_id"]),
            )
        for s in _SHOPS:
            m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(s.get("price_range", "")))
            lo = float(m.group(1)) if m else None
            _d = float(s.get("distance_km") or 1.0)
            min_delivery = (int(lo) // 10 * 10) if lo else 30
            delivery_fee = 3 if _d <= 1 else 5 if _d <= 2.5 else 8
            zone = "盐田"
            z = re.search(r"\((.+?)店\)", str(s.get("name", "")))
            if z:
                zone = z.group(1)
            addr_no = 8 + (abs(hash(s.get("shop_id", ""))) % 88)
            conn.execute(
                """UPDATE shops SET sales=?, min_delivery=?, delivery_fee=?, hours=?, address=?, notice=?
                   WHERE id=? AND (sales IS NULL OR sales=0)""",
                (
                    200 + (abs(hash(s.get("shop_id", ""))) % 800),
                    min_delivery, delivery_fee, "09:00 - 21:00",
                    f"深圳市{zone}区海景路 {addr_no} 号（示例地址）",
                    s.get("intro", "专注鲜花定制与同城速递，包装精致、准时送达。"),
                    s["shop_id"],
                ),
            )
            # 配送时长：新列回填（按距离推导，仅缺省/默认值时写入；
            # 商家后台暂未提供该字段编辑入口，覆盖默认值安全）
            conn.execute(
                "UPDATE shops SET delivery_time=? WHERE id=? AND (delivery_time IS NULL OR delivery_time='' OR delivery_time='30分钟')",
                (f"约{int(10 + _d * 4)}分钟", s["shop_id"]),
            )
        # 商家智库档案（shop_profiles + shop_styles + shop_scenes）
        for p in _SHOP_PROFILES:
            conn.execute(
                """INSERT OR IGNORE INTO shop_profiles
                   (shop_id, brand_story, price_level, packaging, services, strengths, keywords, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    p["shop_id"], p["brand_story"], p["price_level"], p["packaging"],
                    json.dumps(p["services"], ensure_ascii=False), p["strengths"],
                    p["keywords"], _now(), _now(),
                ),
            )
            for style_id, level in p["styles"]:
                conn.execute(
                    "INSERT OR IGNORE INTO shop_styles(shop_id, style_id, level) VALUES (?,?,?)",
                    (p["shop_id"], style_id, level),
                )
            for scene_id, level in p["scenes"]:
                conn.execute(
                    "INSERT OR IGNORE INTO shop_scenes(shop_id, scene_id, level) VALUES (?,?,?)",
                    (p["shop_id"], scene_id, level),
                )
    # 生成占位效果图（dev/演示用，不依赖真实生图）
    for pid in _PLACEHOLDER_PLANS:
        try:
            tasks._write_mock_placeholder(f"plan_{pid}")
        except Exception:  # pragma: no cover
            logger.warning("占位图生成失败: %s", pid)
    logger.info("目录种子数据已灌入：%d 方案 / %d 店铺 / %d 商家智库档案",
                len(_PLANS), len(_SHOPS), len(_SHOP_PROFILES))


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
        "SELECT plan_id FROM shop_plans WHERE shop_id=? AND status='on'", (shop_id,)
    ).fetchall()
    return [r["plan_id"] for r in rows]


def _row_to_shop(row: Any, plan_ids: list[str]) -> dict[str, Any]:
    d = dict(row)
    d["shop_id"] = d.pop("id")
    d["plan_ids"] = plan_ids
    # 美团式经营信息推导（演示值，与 api._shop_card 同规则）：起送价 / 配送费。
    # 真实上线后由商家后台维护，此处保证 search_shops（Agent 推荐卡片）等
    # 非 HTTP 直连数据源同样携带完整字段，避免前端「起送 ¥—」。
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(d.get("price_range", "")))
    lo = float(m.group(1)) if m else None
    dist = float(d.get("distance_km") or 1.0)
    d.setdefault("min_delivery", (int(lo) // 10 * 10) if lo else 30)
    d.setdefault("delivery_fee", 3 if dist <= 1 else 5 if dist <= 2.5 else 8)
    # menu 聚合（红线1：任何读取店铺详情的路径都能拿到「分类+在售商品」，
    # 避免进店无商品的空壳——分类分组按 categories.sort，未分类归「其他」）
    d["menu"] = _shop_menu_from(plan_ids)
    return d


def _shop_menu_from(plan_ids: list[str]) -> list[dict[str, Any]]:
    """按分类分组聚合在售方案，返回 [{id,name,items:[...]}]（menu 契约 1.4/1.5）。"""
    if not plan_ids:
        return []
    conn = get_conn()
    ph = ",".join("?" * len(plan_ids))
    rows = conn.execute(
        f"""SELECT id, name, price, desc, tags, category_id, effect_image_url, rating, sold
            FROM plans WHERE id IN ({ph})""",
        plan_ids,
    ).fetchall()
    cats = conn.execute("SELECT id, name FROM categories ORDER BY sort, id").fetchall()
    cat_map = {c["id"]: c["name"] for c in cats}
    items_by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        it = dict(r)
        it["plan_id"] = it.pop("id")
        it["image"] = it.pop("effect_image_url") or ""
        it["sales"] = it.pop("sold")
        try:
            it["tags"] = json.loads(it["tags"]) if it.get("tags") else []
        except (json.JSONDecodeError, TypeError):
            it["tags"] = []
        items_by_cat.setdefault(it.get("category_id") or "", []).append(it)
    menu = []
    for cid, items in items_by_cat.items():
        if items:
            menu.append({"id": cid, "name": cat_map.get(cid, "其他"), "items": items})
    return menu


# --------------------------------------------------------------------------- #
# 商家智库档案读取（shop_profiles / shop_styles / shop_scenes）
# --------------------------------------------------------------------------- #


def _resolve_style_names() -> dict[str, str]:
    """从 knowledge/styles.json 读取 style_id -> 名称 映射（含子风格）。"""
    try:
        from knowledge import store as kstore

        styles: dict[str, str] = {}
        for entry in kstore._load("style"):
            styles[entry["id"]] = entry["name"]
            for sub in entry.get("substyles", []):
                styles[sub["id"]] = sub["name"]
        return styles
    except Exception:  # pragma: no cover
        return {}


def _resolve_scene_names() -> dict[str, str]:
    """从 knowledge/scenes.json 读取 scene_id -> 名称 映射。"""
    try:
        from knowledge import store as kstore

        return {e["id"]: e["name"] for e in kstore._load("scene") if e.get("id")}
    except Exception:  # pragma: no cover
        return {}


def _row_to_profile(row: Any) -> dict[str, Any]:
    """行 -> 智库档案 dict（services 反序列化；styles/scenes 由调用方补充）。"""
    d = dict(row)
    try:
        d["services"] = json.loads(d["services"]) if d.get("services") else []
    except (json.JSONDecodeError, TypeError):
        d["services"] = []
    return d


def get_shop_profile(shop_id: str) -> dict[str, Any] | None:
    """按 shop_id 取商家智库档案（含 styles/scenes 关联与名称映射），无档案返回 None。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM shop_profiles WHERE shop_id=?", (shop_id,)
    ).fetchone()
    if not row:
        return None
    profile = _row_to_profile(row)
    style_names = _resolve_style_names()
    scene_names = _resolve_scene_names()
    profile["styles"] = [
        {"style_id": r["style_id"], "name": style_names.get(r["style_id"], r["style_id"]), "level": r["level"]}
        for r in conn.execute(
            "SELECT style_id, level FROM shop_styles WHERE shop_id=? ORDER BY level ASC, style_id",
            (shop_id,),
        )
    ]
    profile["scenes"] = [
        {"scene_id": r["scene_id"], "name": scene_names.get(r["scene_id"], r["scene_id"]), "level": r["level"]}
        for r in conn.execute(
            "SELECT scene_id, level FROM shop_scenes WHERE shop_id=? ORDER BY level ASC, scene_id",
            (shop_id,),
        )
    ]
    return profile


def list_shop_profiles() -> list[dict[str, Any]]:
    """全部商家智库档案（按 shop_id 排序）。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM shop_profiles ORDER BY shop_id").fetchall()
    return [_row_to_profile(r) for r in rows]


def list_shop_profiles_full() -> list[dict[str, Any]]:
    """全部商家智库档案（含 styles/scenes 名称映射，供知识库向量检索）。"""
    profiles = list_shop_profiles()
    out: list[dict[str, Any]] = []
    for p in profiles:
        full = get_shop_profile(p["shop_id"])
        if full:
            out.append(full)
    return out


def search_shops_by_profile(keyword: str) -> list[dict[str, Any]]:
    """按智库档案文本检索商家：匹配品牌故事/卖点/包装/服务/关键词/风格名/场景名。

    返回店铺基础信息 + 档案（供 AI 工具与店铺详情页使用），按命中度粗略排序。
    """
    kw = (keyword or "").strip().lower()
    style_names = _resolve_style_names()
    scene_names = _resolve_scene_names()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM shop_profiles").fetchall()
    hits: list[tuple[dict[str, Any], int]] = []
    for row in rows:
        profile = _row_to_profile(row)
        blob = " ".join(
            [
                profile.get("brand_story", ""),
                profile.get("packaging", ""),
                profile.get("strengths", ""),
                profile.get("keywords", ""),
                " ".join(profile.get("services", [])),
            ]
        ).lower()
        if kw and kw not in blob:
            style_rows = conn.execute(
                "SELECT style_id FROM shop_styles WHERE shop_id=?", (row["shop_id"],)
            ).fetchall()
            scene_rows = conn.execute(
                "SELECT scene_id FROM shop_scenes WHERE shop_id=?", (row["shop_id"],)
            ).fetchall()
            names = [style_names.get(r["style_id"], "") for r in style_rows] + [
                scene_names.get(r["scene_id"], "") for r in scene_rows
            ]
            if not any(kw in n.lower() for n in names if n):
                continue
        shop = DBCatalogRepository().get_shop(row["shop_id"])
        hits.append(({**shop, "profile": get_shop_profile(row["shop_id"])}, len(blob)))
    hits.sort(key=lambda x: len(x[0]["profile"].get("styles", [])) + len(x[0]["profile"].get("scenes", [])), reverse=True)
    return [h[0] for h in hits]


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


# --------------------------------------------------------------------------- #
# 商家端：店铺商品管理（归属 = shop_plans 关联；status 控制店铺内上下架）
# --------------------------------------------------------------------------- #


def merchant_shop_plans(shop_id: str) -> list[dict[str, Any]]:
    """商家视角：某店铺关联的全部方案（含在售/下架状态 shop_status）。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT sp.status AS shop_status, p.* FROM shop_plans sp
           JOIN plans p ON p.id = sp.plan_id
           WHERE sp.shop_id=? ORDER BY sp.rowid DESC""",
        (shop_id,),
    ).fetchall()
    return [_row_to_plan(r) for r in rows]


def merchant_create_plan(shop_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """商家新建方案并挂到自家店铺（默认在售）。"""
    plan = create_plan(data)
    with transaction() as c:
        c.execute(
            "INSERT OR IGNORE INTO shop_plans(shop_id, plan_id, status) VALUES (?,?,'on')",
            (shop_id, plan["plan_id"]),
        )
    plan["shop_status"] = "on"
    return plan


def merchant_update_plan(
    plan_id: str, shop_id: str, data: dict[str, Any]
) -> dict[str, Any] | None:
    """商家更新自家店铺关联的方案（未关联该店返回 None）。"""
    conn = get_conn()
    if not conn.execute(
        "SELECT 1 FROM shop_plans WHERE shop_id=? AND plan_id=?", (shop_id, plan_id)
    ).fetchone():
        return None
    plan = update_plan(plan_id, data)
    if plan:
        plan["shop_status"] = "on"
    return plan


def merchant_toggle_plan(plan_id: str, shop_id: str) -> dict[str, Any] | None:
    """上下架切换：翻转该店铺内的 shop_plans.status。未关联该店返回 None。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT status FROM shop_plans WHERE shop_id=? AND plan_id=?", (shop_id, plan_id)
    ).fetchone()
    if not row:
        return None
    new_status = "off" if row["status"] == "on" else "on"
    with transaction() as c:
        c.execute(
            "UPDATE shop_plans SET status=? WHERE shop_id=? AND plan_id=?",
            (new_status, shop_id, plan_id),
        )
    p = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    d = _row_to_plan(p)
    d["shop_status"] = new_status
    return d


def merchant_batch_toggle_plans(shop_id: str, plan_ids: list[str], on: bool) -> int:
    """批量上下架：把该店铺内指定方案的 shop_plans.status 统一设为 on/off。"""
    if not plan_ids:
        return 0
    status = "on" if on else "off"
    ph = ",".join("?" * len(plan_ids))
    with transaction() as c:
        cur = c.execute(
            f"UPDATE shop_plans SET status=? WHERE shop_id=? AND plan_id IN ({ph})",
            [status, shop_id, *plan_ids],
        )
    return cur.rowcount


def merchant_delete_plan(plan_id: str, shop_id: str) -> bool:
    """商家下掉商品：解除与该店关联；若再无其他店关联则连方案一并删除。"""
    conn = get_conn()
    if not conn.execute(
        "SELECT 1 FROM shop_plans WHERE shop_id=? AND plan_id=?", (shop_id, plan_id)
    ).fetchone():
        return False
    with transaction() as c:
        c.execute("DELETE FROM shop_plans WHERE shop_id=? AND plan_id=?", (shop_id, plan_id))
        left = c.execute(
            "SELECT COUNT(*) FROM shop_plans WHERE plan_id=?", (plan_id,)
        ).fetchone()[0]
        if left == 0:
            c.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    return True


# --------------------------------------------------------------------------- #
# 商品分类管理（商家端：分类列表/新增/改名/删除；plans.category_id 关联）
# --------------------------------------------------------------------------- #


def create_category(name: str) -> dict[str, Any] | None:
    """新增分类，返回完整对象；重名返回 None。"""
    import uuid as _uuid

    name = (name or "").strip()
    if not name:
        return None
    conn = get_conn()
    if conn.execute("SELECT 1 FROM categories WHERE name=?", (name,)).fetchone():
        return None
    cat_id = f"cat_{_uuid.uuid4().hex[:8]}"
    nxt = conn.execute("SELECT COALESCE(MAX(sort),0)+1 FROM categories").fetchone()[0]
    with transaction() as c:
        c.execute(
            "INSERT INTO categories(id, name, sort, created_at) VALUES (?,?,?,?)",
            (cat_id, name[:20], nxt, _now()),
        )
    row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    return dict(row) if row else None


def rename_category(cat_id: str, name: str) -> dict[str, Any] | None:
    """改分类名；重名或不存在返回 None。"""
    name = (name or "").strip()
    conn = get_conn()
    if not name or not conn.execute("SELECT 1 FROM categories WHERE id=?", (cat_id,)).fetchone():
        return None
    if conn.execute(
        "SELECT 1 FROM categories WHERE name=? AND id<>?", (name, cat_id)
    ).fetchone():
        return None
    with transaction() as c:
        c.execute("UPDATE categories SET name=? WHERE id=?", (name[:20], cat_id))
    row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    return dict(row) if row else None


def delete_category(cat_id: str) -> bool:
    """删除分类（挂靠商品自动回落到默认分类 cat_daily）。返回是否删到。"""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM categories WHERE id=?", (cat_id,)).fetchone():
        return False
    with transaction() as c:
        c.execute("UPDATE plans SET category_id='cat_daily' WHERE category_id=?", (cat_id,))
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
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
    if "image" in data:
        sets.append("image=?")
        vals.append((data["image"] or "")[:200])
    if "cover" in data:
        sets.append("cover=?")
        vals.append((data["cover"] or "")[:200])
    if "logo" in data:
        sets.append("logo=?")
        vals.append((data["logo"] or "")[:200])
    if "hours" in data:
        sets.append("hours=?")
        vals.append((data["hours"] or "09:00 - 21:00")[:30])
    if "address" in data:
        sets.append("address=?")
        vals.append((data["address"] or "")[:120])
    if "notice" in data:
        sets.append("notice=?")
        vals.append((data["notice"] or "")[:200])
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


# --------------------------------------------------------------------------- #
# 商家-店铺绑定（按店隔离：商家只能管理/查看绑定店铺的数据；admin 不受限）
# --------------------------------------------------------------------------- #


def merchant_shop_ids(user_id: str) -> list[str]:
    """该商家绑定的店铺 id 列表。"""
    rows = get_conn().execute(
        "SELECT shop_id FROM merchant_shops WHERE user_id=? ORDER BY created_at", (user_id,)
    ).fetchall()
    return [r["shop_id"] for r in rows]


def merchant_shops(user_id: str) -> list[dict[str, Any]]:
    """该商家绑定的店铺（id+name），供 stats.shops 返回与前端店铺切换。"""
    rows = get_conn().execute(
        """SELECT s.id, s.name FROM merchant_shops ms
           JOIN shops s ON s.id = ms.shop_id
           WHERE ms.user_id=? ORDER BY ms.created_at""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def merchant_bind(user_id: str, shop_id: str) -> bool:
    """绑定商家到店铺（幂等）。店铺不存在返回 False。"""
    conn = get_conn()
    if not conn.execute("SELECT id FROM shops WHERE id=?", (shop_id,)).fetchone():
        return False
    with transaction() as c:
        c.execute(
            "INSERT OR IGNORE INTO merchant_shops(user_id, shop_id, created_at) VALUES (?,?,?)",
            (user_id, shop_id, _now()),
        )
    return True


def merchant_unbind(user_id: str, shop_id: str) -> bool:
    """解除商家与店铺的绑定。存在绑定且删除成功返回 True。"""
    with transaction() as c:
        cur = c.execute(
            "DELETE FROM merchant_shops WHERE user_id=? AND shop_id=?", (user_id, shop_id)
        )
    return cur.rowcount > 0


def list_plans() -> list[dict[str, Any]]:
    """后台管理用：返回全字段方案列表（含 style / category_id）。"""
    rows = get_conn().execute("SELECT * FROM plans ORDER BY created_at").fetchall()
    return [_row_to_plan(r) for r in rows]


def list_categories() -> list[dict[str, Any]]:
    """全部分类（按 sort 升序，含挂靠商品数 plan_count），
    供店铺详情页的分类菜单 / 管理后台 / 商家端分类管理使用。"""
    rows = get_conn().execute(
        """SELECT c.id, c.name, c.sort,
                  (SELECT COUNT(*) FROM plans p WHERE p.category_id=c.id) AS plan_count
           FROM categories c ORDER BY c.sort ASC, c.id ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def plan_shop_id(plan_id: str) -> str | None:
    """返回承载该方案的首个店铺 id（shop_plans 关联），用于商品卡跳转对应店家。"""
    row = get_conn().execute(
        "SELECT shop_id FROM shop_plans WHERE plan_id=? ORDER BY rowid LIMIT 1", (plan_id,)
    ).fetchone()
    return row["shop_id"] if row else None


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间球面距离（km），供接口层按真实定位计算展示距离。"""
    return _haversine(lat1, lng1, lat2, lng2)


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
        self, keyword: str, requirement: Any | None = None,
        location: dict[str, float] | None = None, max_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        """搜索商家预设方案。

        location 非空时限定「配送范围内（≤max_km）店铺承载的方案」：
        先按用户真实定位过滤店铺，再取这些店关联的方案检索，保证推给用户的
        花束都来自能配送到用户当前位置的店铺（用户无定位时回退全量）。
        """
        conn = get_conn()
        kw = (keyword or "").lower()
        in_range: list[str] = []
        if location and location.get("lat") is not None and location.get("lng") is not None:
            shops = conn.execute("SELECT * FROM shops").fetchall()
            in_range = [
                s["id"] for s in shops
                if s["lat"] is not None
                and _haversine(location["lat"], location["lng"], s["lat"], s["lng"]) <= max_km
            ]
            if not in_range:
                return []  # 配送范围内无店铺 → 无方案可推
            scope = (
                " AND id IN (SELECT plan_id FROM shop_plans WHERE shop_id IN ("
                + ",".join("?" * len(in_range)) + "))"
            )
        else:
            scope = ""
        if not kw:
            rows = (
                conn.execute(
                    f"SELECT * FROM plans WHERE 1=1{scope}", in_range
                ).fetchall()
                if in_range
                else conn.execute("SELECT * FROM plans").fetchall()
            )
        else:
            rows = conn.execute(
                f"SELECT * FROM plans WHERE (lower(name) LIKE ? OR lower(desc) LIKE ?){scope}",
                [f"%{kw}%", f"%{kw}%"] + (in_range if in_range else []),
            ).fetchall()
            # 标签命中（轻量，覆盖关键词在标签而非名称的情况）
            tagged = conn.execute(
                f"SELECT * FROM plans WHERE tags LIKE ?{scope}",
                [f"%{kw}%"] + (in_range if in_range else []),
            ).fetchall()
            seen = {r["id"] for r in rows}
            rows = list(rows) + [r for r in tagged if r["id"] not in seen]
        plans = [_row_to_plan(r) for r in rows]
        # 附上承载店铺 id（首个关联店），供前端商品卡「进店」与下单兜底
        for p in plans:
            p.setdefault("shop_id", plan_shop_id(p["plan_id"]))
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
