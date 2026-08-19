"""storage/repository.py —— 数据仓库抽象 + Mock / Remote 双实现。

设计要点：
- 上层（tools / agent）只依赖 Repository 抽象接口，不直接碰数据来源。
- 提供两种实现，由 build_repository() 按 DATA_SOURCE 配置选择，上层零改动：
  - MockRepository：内置示例花店、方案、效果图占位 URL，零配置可跑通全链路；
  - RemoteRepository：通过 httpx 调真实后端（REMOTE_API_BASE + 端点路径可配），
    按 config.py 中 remote_*_path 约定的契约返回与 MockRepository 同形状的 JSON，「改 .env 即接入」。
- 检索接口支持传入结构化需求（FlowerRequirement）：Mock 做软过滤 + 排序，
  Remote 透传到真实后端，使「按需求检索」从接口层就成立。
- 这是「Mock/真实双轨」的核心：业务 / 状态机 / UI 协议层完全不感知数据来源切换。
"""

from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from config import settings
from storage import tasks

logger = logging.getLogger("repository")


# --------------------------------------------------------------------------- #
# 检索辅助
# --------------------------------------------------------------------------- #


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间距离（km），用于按真实坐标排序店铺。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _parse_price_range(s: str | None) -> tuple[float | None, float | None]:
    """解析 '100-300' 形式的价位区间，失败返回 (None, None)。"""
    if not s:
        return None, None
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(s))
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _filter_plans_by_requirement(
    plans: list[dict[str, Any]], requirement: Any | None
) -> list[dict[str, Any]]:
    """按结构化需求对方案做「软过滤」。

    说明：这里刻意做成软过滤（某条件全不中时回退到不过滤），
    避免演示时出现空结果；而「关键词搜不到 → 返回空」的诚实行为由
    search_plans 的关键词分支保证（见 MockRepository.search_plans）。
    """
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
# 抽象接口
# --------------------------------------------------------------------------- #


class Repository(ABC):
    """数据访问抽象。所有方法返回纯 dict / list[dict]，便于序列化为 UI data。"""

    @abstractmethod
    def search_plans(
        self,
        keyword: str,
        requirement: Any | None = None,
        location: dict[str, float] | None = None,
        max_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        """按关键词搜索商家预设方案；requirement 用于结构化软过滤，
        location 非空时限定「配送范围内（≤max_km）店铺承载」的方案。"""

    @abstractmethod
    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        """获取单个方案详情。"""

    @abstractmethod
    def list_shops(
        self,
        plan: dict[str, Any] | None,
        location: dict[str, float] | None = None,
        requirement: Any | None = None,
    ) -> list[dict[str, Any]]:
        """按距离 / 价格 / 评价综合排序推荐店铺；location 与 requirement 用于排序过滤。"""

    @abstractmethod
    def get_shop(self, shop_id: str) -> dict[str, Any] | None:
        """获取单个店铺详情。"""


# --------------------------------------------------------------------------- #
# Mock 实现（示例数据）
# --------------------------------------------------------------------------- #


class MockRepository(Repository):
    """内置示例数据，零依赖即可跑通导购全链路。"""

    def __init__(self) -> None:
        self._plans: list[dict[str, Any]] = [
            {
                "plan_id": "P001",
                "name": "康乃馨感恩花束",
                "price": 199.0,
                "desc": "11 支粉色康乃馨 + 满天星，适合送给母亲表达感恩。",
                "effect_image_url": "/generated/plan_P001.png",
                "merchant_name": "花漾工坊",
                "tags": ["母亲节", "康乃馨", "温馨"],
            },
            {
                "plan_id": "P002",
                "name": "玫瑰轻奢花盒",
                "price": 299.0,
                "desc": "19 朵红玫瑰礼盒装，高级感拉满，适合纪念日。",
                "effect_image_url": "/generated/plan_P002.png",
                "merchant_name": "花漾工坊",
                "tags": ["玫瑰", "礼盒", "高端"],
            },
            {
                "plan_id": "P003",
                "name": "向日葵花束",
                "price": 159.0,
                "desc": "阳光向日葵 + 尤加利叶，元气满满。",
                "effect_image_url": "/generated/plan_P003.png",
                "merchant_name": "绿野花艺",
                "tags": ["向日葵", "活力", "平价"],
            },
            {
                "plan_id": "P017",
                "name": "洋桔梗梦境花束",
                "price": 189.0,
                "desc": "粉紫洋桔梗配满天星，梦境般温柔，告白纪念日心意之选。",
                "effect_image_url": "/generated/plan_P017.png",
                "merchant_name": "兰庭花礼",
                "tags": ["洋桔梗", "告白", "温柔"],
            },
            {
                "plan_id": "P018",
                "name": "茉莉清香水培瓶",
                "price": 99.0,
                "desc": "白色茉莉水培玻璃瓶，满室清香，办公桌与床头治愈小景。",
                "effect_image_url": "/generated/plan_P018.png",
                "merchant_name": "巷陌花集",
                "tags": ["茉莉", "水培", "清新"],
            },
            {
                "plan_id": "P019",
                "name": "帝王花鎏金礼盒",
                "price": 459.0,
                "desc": "南非帝王花配鎏金礼盒，霸气华贵，商务馈赠与乔迁之喜。",
                "effect_image_url": "/generated/plan_P019.png",
                "merchant_name": "都市花房",
                "tags": ["帝王花", "礼盒", "高端"],
            },
            {
                "plan_id": "P020",
                "name": "马蹄莲极简花束",
                "price": 149.0,
                "desc": "白色马蹄莲单支竖线包装，极简高级，新居入伙与画廊风家居。",
                "effect_image_url": "/generated/plan_P020.png",
                "merchant_name": "花漾工坊",
                "tags": ["马蹄莲", "极简", "高级"],
            },
            {
                "plan_id": "P021",
                "name": "铃兰幸福花束",
                "price": 129.0,
                "desc": "白色铃兰配绿叶衬底，象征幸福归来，婚礼与新生祝福首选。",
                "effect_image_url": "/generated/plan_P021.png",
                "merchant_name": "拾野花铺",
                "tags": ["铃兰", "婚礼", "祝福"],
            },
            {
                "plan_id": "P022",
                "name": "洋牡丹奶油花束",
                "price": 259.0,
                "desc": "奶油色洋牡丹层层叠叠，甜而不腻，闺蜜下午茶与生日之选。",
                "effect_image_url": "/generated/plan_P022.png",
                "merchant_name": "玫瑰花园",
                "tags": ["洋牡丹", "奶油色", "生日"],
            },
            {
                "plan_id": "P023",
                "name": "山茶花中式插花",
                "price": 299.0,
                "desc": "红山茶配青瓷瓶，中式留白意境，书房茶室雅致之选。",
                "effect_image_url": "/generated/plan_P023.png",
                "merchant_name": "半夏花房",
                "tags": ["山茶花", "中式", "雅致"],
            },
            {
                "plan_id": "P024",
                "name": "大丽花复古花束",
                "price": 359.0,
                "desc": "暗红大丽花配复古包装纸，浓郁油画质感，宴会婚礼皆宜。",
                "effect_image_url": "/generated/plan_P024.png",
                "merchant_name": "暮色花园",
                "tags": ["大丽花", "复古", "油画"],
            },
            {
                "plan_id": "P025",
                "name": "多肉阳光组盆",
                "price": 49.0,
                "desc": "五款多肉组合陶盆，好养耐放，办公室与阳台的元气小景。",
                "effect_image_url": "/generated/plan_P025.png",
                "merchant_name": "绿野花艺",
                "tags": ["多肉", "绿植", "平价"],
            },
            {
                "plan_id": "P026",
                "name": "风信子清新水培",
                "price": 89.0,
                "desc": "紫色风信子球根水培，花色清雅，初春气息扑面而来。",
                "effect_image_url": "/generated/plan_P026.png",
                "merchant_name": "南巷花事",
                "tags": ["风信子", "水培", "春日"],
            },
        ]
        # 效果图为本地托管占位：生成真实可访问的 PNG 文件，替代 example.com 死链
        for p in self._plans:
            tasks._write_mock_placeholder(f"plan_{p['plan_id']}")
        # 店铺补充经纬度，使 location 透传后能按真实距离排序（而非静态 distance_km）
        self._shops: list[dict[str, Any]] = [
            {
                "shop_id": "S001",
                "name": "花漾工坊(盐田店)",
                "distance_km": 1.2,
                "price_range": "100-300",
                "rating": 4.8,
                "plan_ids": ["P001", "P002"],
                "lat": 22.560,
                "lng": 114.242,
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
            },
        ]

    def search_plans(
        self,
        keyword: str,
        requirement: Any | None = None,
        location: dict[str, float] | None = None,
        max_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        kw = (keyword or "").lower()
        # 空关键词 = 浏览全部；非空但无命中 = 返回空（诚实，不兜底返全量）
        if not kw:
            plans = self._plans
        else:
            plans = [
                p
                for p in self._plans
                if kw in p["name"].lower() or kw in p["desc"].lower() or any(kw in t for t in p["tags"])
            ]
        # 配送范围过滤：有定位时只保留范围内店铺承载的方案（与 DB 实现对齐）
        if location and location.get("lat") is not None and location.get("lng") is not None:
            in_range_names = {
                s["name"]
                for s in self._shops
                if s.get("lat") is not None
                and _haversine(location["lat"], location["lng"], s["lat"], s["lng"]) <= max_km
            }
            plans = [p for p in plans if p.get("merchant_name") in in_range_names]
        for p in plans:
            p.setdefault(
                "shop_id",
                next(
                    (s["shop_id"] for s in self._shops if s["name"] == p.get("merchant_name")),
                    None,
                ),
            )
        return _filter_plans_by_requirement(plans, requirement)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return next((p for p in self._plans if p["plan_id"] == plan_id), None)

    def list_shops(
        self,
        plan: dict[str, Any] | None,
        location: dict[str, float] | None = None,
        requirement: Any | None = None,
    ) -> list[dict[str, Any]]:
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
                    # 店铺价位与需求预算完全不重叠 → 降权（仍可见，但不优先）
                    if hi < rmin or lo > rmax * 1.5:
                        budget_penalty = 1
            return (has_plan, budget_penalty, dist(s), -s.get("rating", 0))

        return sorted(self._shops, key=sort_key)

    def get_shop(self, shop_id: str) -> dict[str, Any] | None:
        return next((s for s in self._shops if s["shop_id"] == shop_id), None)


# --------------------------------------------------------------------------- #
# Remote 实现（对接真实小程序后端）
# --------------------------------------------------------------------------- #
#
# 通过配置 REMOTE_API_BASE + 各端点路径，把对 Mock 的调用透明转成 HTTP 请求。
# 真实后端只需按 config.py 中 remote_*_path 约定的契约返回与 MockRepository 同形状的 JSON，即可「换配置即接入」，
# 上层 tools.py / skill_order.py 零改动。


class RemoteRepository(Repository):
    """对接真实后端的数据仓库：所有方法转成对远端 REST 接口的调用。"""

    def __init__(self) -> None:
        self.base = settings.remote_api_base.rstrip("/")
        self.timeout = settings.remote_timeout
        self.paths = {
            "plans": settings.remote_plans_path,
            "plan_detail": settings.remote_plan_detail_path,
            "shops": settings.remote_shops_path,
            "shop_detail": settings.remote_shop_detail_path,
        }
        self._client = httpx.Client(timeout=self.timeout)

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """发起 GET 并解析 JSON；网络/解析错误向上抛，由 tools.execute_tool 兜底成 error。"""
        url = f"{self.base}{path}"
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _requirement_params(self, requirement: Any | None) -> dict[str, Any]:
        """把结构化需求转成查询参数（真实后端按需取用，缺省忽略）。"""
        params: dict[str, Any] = {}
        if not requirement:
            return params
        if requirement.budget_min is not None:
            params["budget_min"] = requirement.budget_min
            params["budget_max"] = requirement.budget_max or requirement.budget_min
        if requirement.colors:
            params["colors"] = ",".join(requirement.colors)
        if requirement.style:
            params["style"] = requirement.style
        return params

    def search_plans(
        self,
        keyword: str,
        requirement: Any | None = None,
        location: dict[str, float] | None = None,
        max_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"keyword": keyword or ""}
        params.update(self._requirement_params(requirement))
        if location:
            params["lat"] = location.get("lat")
            params["lng"] = location.get("lng")
        data = self._get_json(self.paths["plans"], params=params)
        return data or []

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        try:
            path = self.paths["plan_detail"].format(id=plan_id)
        except (KeyError, IndexError):
            # 路径未含 {id} 占位符：退回 query 形式兜底
            return self._get_json(self.paths["plan_detail"], params={"plan_id": plan_id})
        return self._get_json(path)

    def list_shops(
        self,
        plan: dict[str, Any] | None,
        location: dict[str, float] | None = None,
        requirement: Any | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if plan:
            params["plan_id"] = plan.get("plan_id")
        if location:
            params["lat"] = location.get("lat")
            params["lng"] = location.get("lng")
        params.update(self._requirement_params(requirement))
        data = self._get_json(self.paths["shops"], params=params)
        return data or []

    def get_shop(self, shop_id: str) -> dict[str, Any] | None:
        try:
            path = self.paths["shop_detail"].format(id=shop_id)
        except (KeyError, IndexError):
            return self._get_json(self.paths["shop_detail"], params={"shop_id": shop_id})
        return self._get_json(path)


def build_repository() -> Repository:
    """按配置装配数据仓库。

    - DATA_SOURCE=remote 且配置了 REMOTE_API_BASE → RemoteRepository（对接真实后端）
    - DATA_SOURCE=remote 但缺 base → 告警并回退 Mock
    - 其余（含默认 mock）→ DBCatalogRepository（DB 为唯一来源，init 时已种子化）；
      仅在 DB 目录为空（种子未灌入）时回退 MockRepository，保证服务永远可启动。
    """
    # 确保表结构就绪（幂等），使模块级 repo 在 import 期即可安全判定目录是否已种子化
    from storage.db import init_db

    try:
        init_db()
    except Exception:  # pragma: no cover
        logger.warning("init_db 失败，将尝试回退 MockRepository", exc_info=True)

    if settings.data_source == "remote":
        if settings.remote_api_base:
            logger.info("数据仓库装配: RemoteRepository -> %s", settings.remote_api_base)
            return RemoteRepository()
        logger.warning("DATA_SOURCE=remote 但未配置 REMOTE_API_BASE，回退 MockRepository")
    # 默认：DB 目录（交付级唯一来源）
    from storage import catalog  # 延迟导入，避免与 db 循环依赖

    if catalog.catalog_ready():
        logger.info("数据仓库装配: DBCatalogRepository（SQLite 目录）")
        return catalog.DBCatalogRepository()
    logger.warning("DB 目录为空，回退 MockRepository（请确认 init_db 已执行 seed_catalog）")
    return MockRepository()


#: 进程级单例仓储（按 DATA_SOURCE 选择；接真实后端只需改 .env）
repo: Repository = build_repository()
