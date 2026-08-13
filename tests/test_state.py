"""状态机流转矩阵测试：允许 / 禁止 / 放弃回退。"""

from agent import ReActAgent
from engine.state import SessionStage, can_transition


def test_allowed_forward_transitions() -> None:
    assert can_transition(SessionStage.ANALYZE, SessionStage.SELECT_MODE)
    assert can_transition(SessionStage.SELECT_MODE, SessionStage.VIEW_PLAN)
    assert can_transition(SessionStage.SELECT_MODE, SessionStage.DIY_DESIGN)
    assert can_transition(SessionStage.VIEW_PLAN, SessionStage.PLAN_CONFIRM)
    assert can_transition(SessionStage.PLAN_CONFIRM, SessionStage.SHOP_RECOMMEND)
    assert can_transition(SessionStage.SHOP_RECOMMEND, SessionStage.ORDER_CONFIRM)
    assert can_transition(SessionStage.ORDER_CONFIRM, SessionStage.DONE)


def test_analyze_allows_direct_diy() -> None:
    """全新会话首句即带 DIY 意图（含「自己/diy」）时，可直接从 ANALYZE 进 DIY_DESIGN，

    无需绕一圈 SELECT_MODE。回归测试：曾因 _ALLOWED[ANALYZE] 只列 SELECT_MODE，
    导致 _derive_next_stage 返回 DIY_DESIGN 被 can_transition 拦回 ANALYZE。
    """
    assert can_transition(SessionStage.ANALYZE, SessionStage.DIY_DESIGN)


def test_derive_next_stage_analyze_respects_diy_intent() -> None:
    """_derive_next_stage 在 ANALYZE 阶段必须尊重 diy 意图：

    - 首句即 DIY（含「自己/diy」）→ DIY_DESIGN（修复点）；
    - 浏览/模糊需求 → SELECT_MODE。
    """
    assert (
        ReActAgent._derive_next_stage(SessionStage.ANALYZE, "自己DIY设计一束粉色康乃馨送给妈妈")
        == SessionStage.DIY_DESIGN
    )
    assert (
        ReActAgent._derive_next_stage(SessionStage.ANALYZE, "我想买花送妈妈生日")
        == SessionStage.SELECT_MODE
    )


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
