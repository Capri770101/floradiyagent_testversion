"""状态机流转规则测试。"""
import pytest

from engine.state import (
    SessionStage, can_transition, from_str, allowed_targets,
)


def test_allowed_transitions():
    assert can_transition(SessionStage.ANALYZE, SessionStage.SELECT_MODE)
    # 最终确认前允许现有方案与 DIY 来回切换
    assert can_transition(SessionStage.PLAN_CONFIRM, SessionStage.VIEW_PLAN)
    assert can_transition(SessionStage.PLAN_CONFIRM, SessionStage.DIY_DESIGN)
    assert can_transition(SessionStage.VIEW_PLAN, SessionStage.DIY_DESIGN)
    assert can_transition(SessionStage.DIY_DESIGN, SessionStage.VIEW_PLAN)
    # 确认后进入店铺推荐，不可回退方案选择
    assert can_transition(SessionStage.PLAN_CONFIRM, SessionStage.SHOP_RECOMMEND)
    assert can_transition(SessionStage.SHOP_RECOMMEND, SessionStage.ORDER_CONFIRM)
    assert can_transition(SessionStage.ORDER_CONFIRM, SessionStage.DONE)
    # 新对话
    assert can_transition(SessionStage.DONE, SessionStage.ANALYZE)


def test_forbidden_transitions():
    # 方案确认后不能直接回到方案选择弹窗
    assert not can_transition(SessionStage.SHOP_RECOMMEND, SessionStage.SELECT_MODE)
    # 终态不能原地打转
    assert not can_transition(SessionStage.DONE, SessionStage.DONE)
    # 未确认方案不能直接下单
    assert not can_transition(SessionStage.SELECT_MODE, SessionStage.ORDER_CONFIRM)
    assert not can_transition(SessionStage.DIY_DESIGN, SessionStage.ORDER_CONFIRM)


def test_from_str_and_targets():
    assert from_str("PLAN_CONFIRM") == SessionStage.PLAN_CONFIRM
    with pytest.raises(ValueError):
        from_str("NOT_A_STAGE")
    targets = allowed_targets(SessionStage.PLAN_CONFIRM)
    assert "SHOP_RECOMMEND" in targets and "DONE" in targets