"""维度抽取增强测试（_extract 覆盖度）。

验证 _extract 对对象别名、场合、风格别称、色系别称、氛围词、口语预算、货币变体的识别。
"""

from tools import _extract


def test_recipient_aliases() -> None:
    assert _extract("送男朋友")["recipient"] == "恋人"
    assert _extract("送女友")["recipient"] == "恋人"
    assert _extract("送同事")["recipient"] == "朋友"
    assert _extract("送领导")["recipient"] == "长辈"
    assert _extract("送宝宝")["recipient"] == "宝宝"


def test_occasion_aliases() -> None:
    assert _extract("婚礼布置")["occasion"] == "婚礼"
    assert _extract("刚领证")["occasion"] == "婚礼"
    assert _extract("升职祝贺")["occasion"] == "升职"
    assert _extract("探病祝福")["occasion"] == "探病"


def test_style_aliases() -> None:
    assert _extract("港风花束")["style"] == "S_VINTAGE"
    assert _extract("奶油风")["style"] == "S_INS"
    assert _extract("法式浪漫")["style"] == "S_INS"


def test_color_aliases() -> None:
    assert _extract("想要粉嫩的")["color"] == "粉"
    assert _extract("桃红喜庆")["color"] == "粉"
    assert _extract("酒红热烈")["color"] == "红"
    assert _extract("撞色活泼")["color"] == "多彩混合"


def test_mood_aliases() -> None:
    assert _extract("莫兰迪低调")["mood"] == "素雅"
    assert _extract("马卡龙甜美")["mood"] == "清新"
    assert _extract("轻奢高级感")["mood"] == "高级"


def test_oral_budget_parsing() -> None:
    assert _extract("两三百元")["budget"] == "250"
    assert _extract("小几百")["budget"] == "200"
    assert _extract("一两千预算")["budget"] == "1500"


def test_currency_variants() -> None:
    assert _extract("预算100块")["budget"] == "100"
    assert _extract("预算 350 块钱")["budget"] == "350"


def test_combined_expression() -> None:
    dims = _extract("送男朋友生日花束 韩式 红 浪漫 两三百")
    assert dims["recipient"] == "恋人"
    assert dims["occasion"] == "生日"
    assert dims["style"] == "S_KOREAN"
    assert dims["color"] == "红"
    assert dims["mood"] == "浪漫"
    assert dims["budget"] == "250"
