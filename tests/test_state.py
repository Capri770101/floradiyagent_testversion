"""状态机流转矩阵测试：允许 / 禁止 / 放弃回退。"""

from engine.state import SessionStage, can_transition


def test_allowed_forward_transitions() -> None:
    assert can_transition(SessionStage.ANALYZE, SessionStage.SELECT_MODE)
    assert can_transition(SessionStage.SELECT_MODE, SessionStage.VIEW_PLAN)
    assert can_transition(SessionStage.SELECT_MODE, SessionStage.DIY_DESIGN)
    assert can_transition(SessionStage.VIEW_PLAN, SessionStage.PLAN_CONFIRM)
    assert can_transition(SessionStage.PLAN_CONFIRM, SessionStage.SHOP_RECOMMEND)
    assert can_transition(SessionStage.SHOP_RECOMMEND, SessionStage.ORDER_CONFIRM)
    assert can_transition(SessionStage.ORDER_CONFIRM, SessionStage.DONE)


def test_mode_switch_before_confirm() -> None:
    """确认前，现有方案 VIEW_PLAN 与 DIY 设计 DIY_DESIGN 可来回切换。"""
    assert can_transition(SessionStage.VIEW_PLAN, SessionStage.DIY_DESIGN)
    assert can_transition(SessionStage.DIY_DESIGN, SessionStage.VIEW_PLAN)
    assert can_transition(SessionStage.DIY_DESIGN, SessionStage.IMAGE_GEN)


def test_forbidden_jumps() -> None:
    """禁止跳步与确认后回退。"""
    assert not can_transition(SessionStage.ANALYZE, SessionStage.SHOP_RECOMMEND)   # 跳步
    assert not can_transition(SessionStage.PLAN_CONFIRM, SessionStage.VIEW_PLAN)  # 确认后不可回退浏览
    assert not can_transition(SessionStage.SELECT_MODE, SessionStage.DONE)         # 跳到终点


def test_abandon_falls_back_to_select_mode() -> None:
    """用户明确放弃时，可从后续阶段回退到模式选择。"""
    assert can_transition(SessionStage.SHOP_RECOMMEND, SessionStage.SELECT_MODE)
    assert can_transition(SessionStage.ORDER_CONFIRM, SessionStage.SELECT_MODE)
    assert can_transition(SessionStage.VIEW_PLAN, SessionStage.SELECT_MODE)
