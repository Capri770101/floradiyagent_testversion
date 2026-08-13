"""DIY 结构化设计能力测试。"""

import json

import tools


def test_design_mother_contains_strong_signal_flower() -> None:
    p = tools.design_diy_plan("想给妈妈买束花，预算200，温柔一点")
    mains = [m["name"] for m in p["design"]["main_flowers"]]
    assert mains  # 主花非空
    # 对象强信号：母亲 → 康乃馨（母爱）或 玫瑰
    assert any(n in mains for n in ("康乃馨", "玫瑰"))


def test_design_has_meaning_and_prompt() -> None:
    p = tools.design_diy_plan("送恋人生日花束 粉紫 300")
    assert p["design"]["meaning"]
    assert "风格" in p["effect_prompt"]
    assert p["estimated_price"]


def test_design_extracts_budget() -> None:
    p = tools.design_diy_plan("预算350元左右的商务花")
    assert "350" in p["estimated_price"]


def test_design_stores_latest_plan_for_image() -> None:
    tools.design_diy_plan("探病祝福 清淡")
    assert tools._latest_diy_plan is not None
    assert "effect_prompt" in tools._latest_diy_plan


def test_generate_diy_plan_tool_returns_json() -> None:
    out = tools.generate_diy_plan("自己悦己 北欧自然风 100")
    data = json.loads(out)
    assert data["plan_id"].startswith("DIY_")
    assert data["diy"] is True
    assert data["design"]["main_flowers"]


def test_design_has_landing_fields() -> None:
    """方案应含落地化字段：插花步骤 / 养护 / 贺卡 / 预算明细。"""
    p = tools.design_diy_plan("母亲节给妈妈买束花，预算200")
    assert isinstance(p["diy_steps"], list) and len(p["diy_steps"]) >= 4
    assert p["care_tips"]
    assert p["card_message"]
    assert p["budget_breakdown"]["items"]
    assert p["budget_breakdown"]["total_estimate"] > 0


def test_oral_budget_parsed() -> None:
    """口语预算「两三百」应解析为 ~250 并落到 T2 档。"""
    p = tools.design_diy_plan("送朋友生日花束 两三百")
    assert p["budget_num"] == 250
    assert p["budget_tier"] == "精致 / 送礼"


def test_recipient_alias_expands() -> None:
    """对象别名（男朋友/同事/领导）应能被识别且不影响主流程。"""
    for text, expected in (("送男朋友生日花", "恋人"), ("送同事乔迁", "朋友"), ("送领导感谢", "长辈")):
        dims = tools._extract(text)
        assert dims.get("recipient") == expected
