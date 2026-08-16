"""商家智库（shop 域）知识检索测试：档案数据来自 DB 的 shop_profiles。

验证 query_knowledge("shop", ...) 的混合检索：
- 关键词召回（风格名/场景名/卖点文本命中）
- 长自然语句的向量语义召回（如「能做婚礼布置的高端花艺工作室」）
- 枚举与 get_by_id
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge import get_by_id, query_knowledge  # noqa: E402
from storage.db import init_db  # noqa: E402


def setup_module(module):
    init_db()  # 灌入商家智库种子数据


def test_shop_domain_enumeration() -> None:
    r = query_knowledge("shop", "")
    assert r["count"] == 16
    assert all(x["_domain"] == "shop" for x in r["results"])
    assert all(x.get("name") for x in r["results"])  # 每家都有商家名


def test_shop_keyword_style() -> None:
    # 风格名关键词 → 主打该风格的商家
    r = query_knowledge("shop", "韩式")
    ids = {x["id"] for x in r["results"]}
    assert "S009" in ids  # 花语花集（韩式主打）
    assert "S001" in ids  # 花漾工坊（韩式主打）


def test_shop_keyword_scene() -> None:
    # 场景名关键词 → 擅长该场景的商家
    r = query_knowledge("shop", "婚礼")
    ids = {x["id"] for x in r["results"]}
    assert "S011" in ids  # 暮色花园（婚礼布置强项）
    assert "S008" in ids  # 花间小筑（宴会布置）


def test_shop_vector_natural_language() -> None:
    # 长自然语句 → 向量语义召回，最相关的商家排第一
    r = query_knowledge("shop", "想找一家能做婚礼布置的高端花艺工作室")
    assert r["count"] >= 1
    top = r["results"][0]
    assert top["id"] == "S011"  # 暮色花园
    assert top["_score"] >= 0.2


def test_shop_get_by_id() -> None:
    s = get_by_id("shop", "S009")
    assert s is not None
    assert s["name"] == "花语花集(福田CBD店)"
    assert s["price_level"] == "中端"
    assert {x["style_id"] for x in s["styles"]} == {"S_KOREAN", "S_INS"}
    assert get_by_id("shop", "NOPE") is None