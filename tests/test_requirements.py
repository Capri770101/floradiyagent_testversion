"""FlowerRequirement 结构化需求状态 + 共享抽取器测试。

验证 review 点名的关键缺口已补上：需求从散落 LLM context 收敛为一等公民对象，
且抽取结果与旧 _extract 的遗留形态逐字段对齐（保证 DIY 管线零改动）。
"""

from requirements import FlowerRequirement
from tools import _extract, extract_requirement


def test_extract_requirement_fields() -> None:
    req = extract_requirement("送男朋友生日花束 韩式 红 浪漫 两三百 深圳南山区")
    assert req.recipient == "恋人"
    assert req.occasion == "生日"
    assert req.style == "S_KOREAN"
    assert req.colors == ["红"]
    assert req.mood == "浪漫"
    assert req.budget_num == 250
    assert req.budget_min == 200
    assert req.budget_max == 300
    assert req.relationship == "情侣"


def test_legacy_dict_matches_old_extract() -> None:
    """共享抽取器产出的遗留 dict 必须与旧 _extract 完全一致。"""
    text = "送男朋友生日花束 韩式 红 浪漫 两三百"
    assert extract_requirement(text).to_legacy_dict() == _extract(text)


def test_longest_match_color_alias() -> None:
    # 「桃红」应优先于单字「红」，最终归到粉
    req = extract_requirement("想要桃红色系")
    assert req.colors == ["粉"]


def test_merge_accumulates_across_turns() -> None:
    a = extract_requirement("预算200元")
    b = extract_requirement("送给妈妈")
    merged = a.merge(b)
    assert merged.recipient == "母亲"
    assert merged.budget_num == 200
    assert merged.relationship == "亲子"


def test_from_to_dict_roundtrip() -> None:
    req = extract_requirement("母亲节送妈妈康乃馨 粉色 150元")
    again = FlowerRequirement.from_dict(req.to_dict())
    assert again == req


def test_location_carried_by_merge() -> None:
    a = FlowerRequirement()
    b = FlowerRequirement(location={"lat": 22.5, "lng": 114.1})
    assert a.merge(b).location == {"lat": 22.5, "lng": 114.1}
