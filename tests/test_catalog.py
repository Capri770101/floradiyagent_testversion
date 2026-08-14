"""DB 商品目录仓储（DBCatalogRepository）测试：种子 + 检索契约。

不依赖 LLM；init_db 会顺带 seed_catalog 灌入示例数据。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import init_db  # noqa: E402
from storage import catalog  # noqa: E402
from requirements import FlowerRequirement  # noqa: E402


def setup_module(module):
    # 初始化临时 DB（conftest 已设 DB_PATH 到临时文件），并灌入种子数据
    init_db()


def test_seed_catalog_idempotent():
    assert catalog.catalog_ready() is True
    # 再次 seed 不应报错或重复插入
    catalog.seed_catalog()
    plans = catalog.DBCatalogRepository().search_plans("")
    assert len(plans) == 3


def test_search_plans_keyword():
    repo = catalog.DBCatalogRepository()
    # 空关键词 = 全部
    assert len(repo.search_plans("")) == 3
    # 关键词命中（名称）
    hit = repo.search_plans("康乃馨")
    assert len(hit) == 1 and hit[0]["plan_id"] == "P001"
    # 无命中 = 返回空（诚实）
    assert repo.search_plans("不存在的花") == []


def test_get_plan_shape():
    repo = catalog.DBCatalogRepository()
    p = repo.get_plan("P001")
    assert p["plan_id"] == "P001"
    assert isinstance(p["tags"], list) and "母亲节" in p["tags"]
    assert p["merchant_name"] == "花漾工坊"
    assert repo.get_plan("NOPE") is None


def test_list_shops_sorted_and_plan_ids():
    repo = catalog.DBCatalogRepository()
    shops = repo.list_shops(None)
    assert len(shops) == 3
    s1 = repo.get_shop("S001")
    assert set(s1["plan_ids"]) == {"P001", "P002"}
    # 真实定位下，含目标方案的店铺应优先且按距离排序
    located = repo.list_shops({"plan_id": "P003"}, {"lat": 22.572, "lng": 114.230})
    assert located[0]["shop_id"] == "S002"


def test_requirement_soft_filter():
    repo = catalog.DBCatalogRepository()
    req = FlowerRequirement(budget_min=150, budget_max=250)
    out = repo.search_plans("", req)
    # 软过滤：预算 199/159/299 中 299 超限 1.5 倍被剔除，但若全不中则回退不过滤
    ids = {p["plan_id"] for p in out}
    assert "P001" in ids  # 199 在 [150,250] 内
