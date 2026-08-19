"""Mock 检索诚实化 + 需求驱动的过滤/排序测试。

针对 review 指出的两个真实 gap：
1. search_plans 搜不到时曾兜底返全量（生产危险）→ 现在返回空。
2. search_shops 曾把 location 传成 None，距离排序永不触发 → 现在 location 透传并真实生效。
"""

from requirements import FlowerRequirement
from storage.repository import MockRepository


def _repo() -> MockRepository:
    return MockRepository()


def test_empty_keyword_returns_all() -> None:
    # 留空 = 浏览全部（Mock 与目录种子同步为 13 例）
    assert len(_repo().search_plans("")) == 13


def test_no_match_returns_empty_not_all() -> None:
    # 关键诚实化：搜不到不能兜底返全量
    assert _repo().search_plans("龙虾大餐") == []


def test_keyword_match_count() -> None:
    assert len(_repo().search_plans("康乃馨")) == 1


def test_requirement_budget_soft_filters() -> None:
    req = FlowerRequirement(budget_min=250, budget_max=300)
    plans = _repo().search_plans("", requirement=req)
    # P002 299 在带内居首；P023 299 同价（软过滤对超带价剔除后同价位按插入序）
    assert plans[0]["plan_id"] == "P002"


def test_location_changes_shop_order() -> None:
    r = _repo()
    # 不传位置：按静态距离，S001(盐田店)最近排前
    no_loc = [s["shop_id"] for s in r.list_shops(None, None)]
    assert no_loc[0] == "S001"
    # 传位置贴近 S003：S003 应排到最前（距离排序真正生效）
    near_s3 = {"lat": 22.548, "lng": 114.255}
    with_loc = [s["shop_id"] for s in r.list_shops(None, near_s3)]
    assert with_loc[0] == "S003"


def test_budget_requirement_penalizes_out_of_range_shop() -> None:
    r = _repo()
    near_s3 = {"lat": 22.548, "lng": 114.255}
    # 无预算需求：位置贴近 S003 → S003 第一
    assert [s["shop_id"] for s in r.list_shops(None, near_s3)][0] == "S003"
    # 有预算需求(80-90 元)：S003 价位 150-400 超出 → 降到末位
    req = FlowerRequirement(budget_min=80, budget_max=90)
    ordered = [s["shop_id"] for s in r.list_shops(None, near_s3, requirement=req)]
    assert ordered[-1] == "S003"
    assert ordered[0] != "S003"
