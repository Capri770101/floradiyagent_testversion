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


def test_design_stores_plan_in_session() -> None:
    """方案写入当前会话（latest_diy_plan / selected_plan），不再依赖进程级全局（并发安全）。"""
    from storage import memory as mem
    from storage.db import init_db

    init_db()
    sid = mem.get_or_create_session("u_diy_store")
    ctx = {"user_id": "u_diy_store", "session_id": sid, "location": None}
    data = json.loads(tools.generate_diy_plan("探病祝福 清淡", ctx))
    assert "effect_prompt" in data
    stored = mem.get_session_json("u_diy_store", sid, "latest_diy_plan")
    assert stored is not None
    assert stored["plan_id"] == data["plan_id"]
    selected = mem.get_session_json("u_diy_store", sid, "selected_plan")
    assert selected is not None and selected["plan_id"] == data["plan_id"]
    # 无会话上下文（如 cli 直调）不应写库，也不报错
    assert json.loads(tools.generate_diy_plan("自己悦己 100"))["diy"] is True


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


def test_design_has_card_enrich_fields() -> None:
    """模块二：规则引擎产出的方案必须带卡片扩充字段（难度/耗时/保鲜期/人群/禁忌/情绪）。"""
    p = tools.design_diy_plan("送妈妈生日花束 预算200")
    d = p["design"]
    assert d["difficulty"] in ("入门", "进阶", "高手")
    assert isinstance(d["est_time"], int) and d["est_time"] > 0
    assert "天" in d["shelf_life"]
    assert d["suitable_for"]  # 非空
    assert "换水" in d["caution"]  # 养护类提醒兜底
    assert d["mood_tags"]  # 非空


def test_merge_keeps_llm_new_fields() -> None:
    """模块二：LLM 输出的扩充字段经 _merge_plan 合入最终方案（不回退到规则兜底值）。"""
    baseline = tools.design_diy_plan("送妈妈生日花束 预算200")
    llm = {
        "design": {
            "main_flowers": baseline["design"]["main_flowers"],
            "fillers": baseline["design"]["fillers"],
            "foliage": baseline["design"]["foliage"],
            "color_scheme": ["奶油白"],
            "packaging": "礼盒",
            "meaning": "母爱",
            "difficulty": "高手",
            "est_time": 60,
            "shelf_life": "约 3-5 天",
            "suitable_for": ["母亲"],
            "caution": "花粉过敏者请谨慎接触",
            "mood_tags": ["治愈", "感恩"],
        }
    }
    merged = tools._merge_plan(baseline, llm)
    d = merged["design"]
    assert d["difficulty"] == "高手"
    assert d["est_time"] == 60
    assert d["shelf_life"] == "约 3-5 天"
    assert d["suitable_for"] == ["母亲"]
    assert d["caution"] == "花粉过敏者请谨慎接触"
    assert d["mood_tags"] == ["治愈", "感恩"]
