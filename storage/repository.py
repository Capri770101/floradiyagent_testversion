"""数据仓库层：抽象接口 + Mock 实现。

后续接入真实数据库时，只需实现 BaseRepository 并在启动处替换注册即可，
上层智能体 / 工具代码零改动（见 requirement: 数据层 Mock 先行，真实接入预留）。
"""
import logging
from dataclasses import asdict, dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Plan:
    id: str
    name: str
    price: float
    desc: str
    effect_image_url: str
    merchant_id: str
    tags: List[str] = field(default_factory=list)


@dataclass
class Shop:
    id: str
    name: str
    address: str
    distance_km: float
    price_range: str
    rating: float


@dataclass
class User:
    user_id: str
    role: str = "user"


class BaseRepository:
    """数据仓库抽象接口（Mock / 真实数据库实现共用同一契约）。"""

    def search_plans(self, keyword: str) -> List[Plan]: ...

    def get_plan(self, plan_id: str) -> Optional[Plan]: ...

    def get_shop(self, shop_id: str) -> Optional[Shop]: ...

    def list_shops(self) -> List[Shop]: ...

    def get_user(self, user_id: str) -> Optional[User]: ...

    def save_user(self, user: User) -> None: ...


class MockRepository(BaseRepository):
    """Mock 数据实现：内置示例花店与商家预设方案，效果图为占位 URL。"""

    def __init__(self) -> None:
        self._plans: dict[str, Plan] = {
            p.id: p
            for p in [
                Plan("p1", "康乃馨温情花束", 158.0,
                     "粉色康乃馨 11 枝，配满天星与尤加利叶，适合送给母亲表达感恩。",
                     "https://mock.flower/prod/p1.png", "s1", ["康乃馨", "母亲", "长辈", "感恩"]),
                Plan("p2", "玫瑰心动礼盒", 199.0,
                     "红玫瑰 19 枝礼盒装，附贺卡与丝带，适合表白与纪念日。",
                     "https://mock.flower/prod/p2.png", "s2", ["玫瑰", "恋人", "告白", "纪念日"]),
                Plan("p3", "向日葵元气花束", 89.0,
                     "向日葵 6 枝搭配黄玫瑰，明亮治愈，适合送朋友或乔迁。",
                     "https://mock.flower/prod/p3.png", "s3", ["向日葵", "朋友", "生日", "阳光"]),
                Plan("p4", "混搭田园花篮", 128.0,
                     "当季混搭花材编织花篮，自然清新，适合家居装饰与探望。",
                     "https://mock.flower/prod/p4.png", "s1", ["混搭", "家居", "探望"]),
                Plan("p5", "百合祝福花束", 168.0,
                     "白百合 5 枝配翠菊与绿植，寓意祝福，适合探病与乔迁。",
                     "https://mock.flower/prod/p5.png", "s2", ["百合", "祝福", "探病"]),
            ]
        }
        self._shops: dict[str, Shop] = {
            s.id: s
            for s in [
                Shop("s1", "花语鲜花（人民广场店）", "人民广场地铁站 3 号口旁",
                     1.2, "30-200 元", 4.8),
                Shop("s2", "澜庭花艺（中山公园店）", "中山公园地铁站 2 号口步行 300 米",
                     3.5, "50-500 元", 4.6),
                Shop("s3", "小草花房（大学城店）", "大学城商业街 12 号",
                     2.1, "20-150 元", 4.9),
            ]
        }

    # ---------- 抽象接口实现 ----------
    def search_plans(self, keyword: str = "") -> List[Plan]:
        kw = (keyword or "").strip().lower()
        if not kw:
            return list(self._plans.values())
        hits = [p for p in self._plans.values()
                if kw in p.name.lower()
                or kw in p.desc.lower()
                or any(kw in t.lower() for t in p.tags)]
        return hits or list(self._plans.values())

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self._plans.get(plan_id)

    def get_shop(self, shop_id: str) -> Optional[Shop]:
        return self._shops.get(shop_id)

    def list_shops(self) -> List[Shop]:
        return sorted(self._shops.values(), key=lambda s: (-s.rating, s.distance_km))

    def get_user(self, user_id: str) -> Optional[User]:
        return None  # 用户落库由 memory 层管理，此处留待真实数据库接入

    def save_user(self, user: User) -> None:
        pass  # Mock 实现为空（真实实现写用户表/关联微信 openid）

    # ---------- DIY 方案生成（当前为规则版 mock，可替换为模板/生成式实现） ----------
    def generate_diy_plan(self, requirements: str) -> dict:
        import uuid
        kw = requirements or ""
        flavor_map = [
            ("康乃馨", "母亲", 10), ("玫瑰", "爱人", 12), ("郁金香", "朋友", 9),
            ("向日葵", "生日", 6), ("百合", "探望", 5), ("满天星", "搭配", 1),
        ]
        matched = [w for w, cat, _ in flavor_map if any(c in kw for c in (cat, w.split("、")[0]))]
        if not matched:
            matched = ["康乃馨"]
        flowers = [
            {"name": f, "quantity": 8 * (i + 1) if isinstance(f, str) else 6,
             "role": "主花" if i == 0 else "配花"}
            for i, f in enumerate(matched)
        ]
        return {
            "plan_id": f"diy-{uuid.uuid4().hex[:8]}",
            "name": "DIY 定制花束",
            "plan_type": "diy",
            "flowers": flowers,
            "style": "温馨自然",
            "price_estimate": round(88 + 20 * len(flowers), 2),
            "notes": "根据需求生成的参考方案，确认后可调用生成效果图。",
        }

    def to_dict(self, obj) -> dict:
        return asdict(obj)