"""respond_to_user 契约校验测试（LLM 输出可靠性）：无效 data 形状被识别。"""
from agent.agent import ReActAgent
from agent.engine.ui_protocol import UIType

_V = ReActAgent._validate_respond_data


def test_text_accepts_any():
    assert _V(UIType.TEXT, {}) == {}
    assert _V(UIType.TEXT, {"a": 1}) == {"a": 1}


def test_plan_card_requires_plans_list():
    assert _V(UIType.PLAN_CARD, {"plans": [{"id": "P001"}]}) is not None
    assert _V(UIType.PLAN_CARD, {}) is None          # 空 data → 幻觉
    assert _V(UIType.PLAN_CARD, {"plans": []}) is None  # 空列表 → 幻觉
    assert _V(UIType.PLAN_CARD, {"plans": "P001"}) is None  # 非列表 → 幻觉


def test_shop_card_requires_shops_list():
    assert _V(UIType.SHOP_CARD, {"shops": [{"id": "S001"}]}) is not None
    assert _V(UIType.SHOP_CARD, {}) is None


def test_dialog_options_requires_options():
    assert _V(UIType.DIALOG_OPTIONS, {"options": [{"label": "a", "value": "a"}]}) is not None
    assert _V(UIType.DIALOG_OPTIONS, {"options": "a"}) is None
    assert _V(UIType.DIALOG_OPTIONS, {}) is None


def test_pay_jump_requires_order_id_or_page_path():
    assert _V(UIType.PAY_JUMP, {"order_id": "O_1"}) is not None
    assert _V(UIType.PAY_JUMP, {"page_path": "/pages/x"}) is not None
    assert _V(UIType.PAY_JUMP, {}) is None


def test_image_task_requires_task_id_or_result():
    assert _V(UIType.IMAGE_TASK, {"task_id": "t1"}) is not None
    assert _V(UIType.IMAGE_TASK, {"result_url": "/g/1.jpg"}) is not None
    assert _V(UIType.IMAGE_TASK, {"task_id": None}) is None  # LLM 幻觉 task_id=null
    assert _V(UIType.IMAGE_TASK, {}) is None
