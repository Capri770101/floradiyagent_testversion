"""DB 商品目录仓储（DBCatalogRepository）测试：种子 + 检索契约。

不依赖 LLM；init_db 会顺带 seed_catalog 灌入示例数据。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.requirements import FlowerRequirement
from backend.storage import catalog
from backend.storage.db import init_db


def setup_module(module):
    init_db()

def test_seed_catalog_idempotent():
    assert asyncio.run(catalog.catalog_ready()) is True
    asyncio.run(catalog.seed_catalog())
    plans = asyncio.run(catalog.DBCatalogRepository().search_plans(''))
    assert len(plans) == 26

def test_search_plans_keyword():
    repo = catalog.DBCatalogRepository()
    assert len(asyncio.run(repo.search_plans(''))) == 26
    hit = asyncio.run(repo.search_plans('康乃馨'))
    assert len(hit) == 2 and hit[0]['plan_id'] == 'P001'
    assert asyncio.run(repo.search_plans('不存在的花')) == []

def test_get_plan_shape():
    repo = catalog.DBCatalogRepository()
    p = asyncio.run(repo.get_plan('P001'))
    assert p['plan_id'] == 'P001'
    assert isinstance(p['tags'], list) and '母亲节' in p['tags']
    assert p['merchant_name'] == '花漾工坊'
    assert asyncio.run(repo.get_plan('NOPE')) is None

def test_list_shops_sorted_and_plan_ids():
    repo = catalog.DBCatalogRepository()
    shops = asyncio.run(repo.list_shops(None))
    assert len(shops) == 16
    s1 = asyncio.run(repo.get_shop('S001'))
    assert set(s1['plan_ids']) == {'P001', 'P002', 'P010', 'P020'}
    located = asyncio.run(repo.list_shops({'plan_id': 'P003'}, {'lat': 22.572, 'lng': 114.23}))
    assert located[0]['shop_id'] == 'S002'

def test_requirement_soft_filter():
    repo = catalog.DBCatalogRepository()
    req = FlowerRequirement(budget_min=150, budget_max=250)
    out = asyncio.run(repo.search_plans('', req))
    ids = {p['plan_id'] for p in out}
    assert 'P001' in ids
