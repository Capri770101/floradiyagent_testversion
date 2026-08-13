"""DIY 设计：场景感知 + 细分风格 + 用户反馈迭代测试。

验证 design_diy_plan 能据场景/节日套用模板与细分风格，
以及 revise_diy_plan 基于反馈生成可追溯的新版本（版本递增、可移除花材、可改色/预算）。
"""

import json

from tools import design_diy_plan, revise_diy_plan


def _design(text: str) -> dict:
    return design_diy_plan(text)


def test_mothers_day_picks_carnation_and_korean_luxe() -> None:
    """母亲节 → 场景命中、子风格韩式高级、主花含康乃馨。"""
    p = _design("母亲节给妈妈买束花")
    assert p["scene"] == "母亲节"
    assert p.get("substyle_id") == "S_KOREAN_LUXE"
    assert any(m["name"] == "康乃馨" for m in p["design"]["main_flowers"])


def test_birthday_picks_ins_pop() -> None:
    """朋友生日活泼 → 子风格明亮打卡。"""
    p = _design("朋友生日想要活泼一点的")
    assert p.get("substyle_id") == "S_INS_POP"


def test_christmas_picks_vintage_hk() -> None:
    """圣诞 → 复古港风子风格、红绿主色。"""
    p = _design("圣诞红火一点")
    assert p.get("substyle_id") == "S_VINTAGE_HK"
    assert "红" in p["design"]["color_scheme"]


def test_revision_cheaper_lowers_budget() -> None:
    """反馈「便宜点」→ 版本+1、parent 指向旧版、预算降为入门档。"""
    base = _design("母亲节给妈妈买束花")
    r = json.loads(revise_diy_plan(json.dumps(base), "便宜点"))
    assert r["version"] == base["version"] + 1
    assert r["parent_id"] == base["plan_id"]
    assert "入门" in r["budget_tier"]


def test_revision_removes_flower() -> None:
    """反馈「不要康乃馨」→ 新版主花不含康乃馨。"""
    base = _design("母亲节给妈妈买束花")
    r = json.loads(revise_diy_plan(json.dumps(base), "不要康乃馨"))
    assert not any(m["name"] == "康乃馨" for m in r["design"]["main_flowers"])


def test_revision_color_override() -> None:
    """反馈「换成红色调」→ 色系以红打头。"""
    base = _design("母亲节给妈妈买束花")
    r = json.loads(revise_diy_plan(json.dumps(base), "换成红色调"))
    assert r["design"]["color_scheme"][0] == "红"


def test_revision_keeps_main_when_no_exclude() -> None:
    """无移除反馈时，迭代默认沿用上一版主花（连续不跳变）。"""
    base = _design("母亲节给妈妈买束花")
    r = json.loads(revise_diy_plan(json.dumps(base), "预算加到500"))
    base_mains = {m["name"] for m in base["design"]["main_flowers"]}
    new_mains = {m["name"] for m in r["design"]["main_flowers"]}
    assert base_mains & new_mains  # 至少保留一支主花
