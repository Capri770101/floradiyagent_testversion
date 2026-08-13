"""会话状态机：业务阶段定义与流转规则。

业务流（详见 README）：
需求分析 ANALYZE → 弹窗询问 SELECT_MODE → [现有方案 VIEW_PLAN ⇄ DIY DIY_DESIGN]
→ 效果图 IMAGE_GEN → 方案确认 PLAN_CONFIRM → 店铺推荐 SHOP_RECOMMEND
→ 下单确认 ORDER_CONFIRM → DONE。
关键规则：最终确认（PLAN_CONFIRM 确认）之前，允许在现有方案与 DIY 之间来回切换。
"""
from enum import Enum


class SessionStage(str, Enum):
    ANALYZE = "ANALYZE"                # 需求分析
    SELECT_MODE = "SELECT_MODE"        # 弹窗询问：现有方案 or DIY
    VIEW_PLAN = "VIEW_PLAN"            # 展示现有（商家预设）方案
    DIY_DESIGN = "DIY_DESIGN"          # DIY 方案设计
    IMAGE_GEN = "IMAGE_GEN"            # 生成效果图（异步，客户端轮询）
    PLAN_CONFIRM = "PLAN_CONFIRM"      # 方案确认（确认前可来回切换）
    SHOP_RECOMMEND = "SHOP_RECOMMEND"  # 店铺推荐
    ORDER_CONFIRM = "ORDER_CONFIRM"    # 下单确认
    DONE = "DONE"                      # 已引导至支付，新一轮对话从 ANALYZE 重新开始


_STAGES = list(SessionStage)

# 合法流转表：source -> 允许的 targets
# 对话性阶段允许"自我循环"（如同一阶段内再次确认/再次询问）；
# 终态 DONE 不提供自我循环，新一轮对话从 ANALYZE 重新开始。
_TRANSITIONS: dict[SessionStage, set[SessionStage]] = {
    SessionStage.ANALYZE: {SessionStage.ANALYZE, SessionStage.SELECT_MODE, SessionStage.DONE},
    SessionStage.SELECT_MODE: {
        SessionStage.SELECT_MODE, SessionStage.VIEW_PLAN, SessionStage.DIY_DESIGN,
        SessionStage.PLAN_CONFIRM, SessionStage.ANALYZE, SessionStage.DONE,
    },
    SessionStage.VIEW_PLAN: {
        SessionStage.VIEW_PLAN, SessionStage.DIY_DESIGN, SessionStage.PLAN_CONFIRM,
        SessionStage.IMAGE_GEN, SessionStage.ANALYZE, SessionStage.DONE,
    },
    SessionStage.DIY_DESIGN: {
        SessionStage.DIY_DESIGN, SessionStage.VIEW_PLAN, SessionStage.PLAN_CONFIRM,
        SessionStage.IMAGE_GEN, SessionStage.ANALYZE, SessionStage.DONE,
    },
    SessionStage.IMAGE_GEN: {
        SessionStage.IMAGE_GEN, SessionStage.DIY_DESIGN, SessionStage.VIEW_PLAN,
        SessionStage.PLAN_CONFIRM, SessionStage.ANALYZE, SessionStage.DONE,
    },
    SessionStage.PLAN_CONFIRM: {
        SessionStage.PLAN_CONFIRM, SessionStage.SHOP_RECOMMEND, SessionStage.VIEW_PLAN,
        SessionStage.DIY_DESIGN, SessionStage.ANALYZE, SessionStage.DONE,
    },
    SessionStage.SHOP_RECOMMEND: {
        SessionStage.SHOP_RECOMMEND, SessionStage.ORDER_CONFIRM,
        SessionStage.ANALYZE, SessionStage.DONE,
    },
    SessionStage.ORDER_CONFIRM: {
        SessionStage.ORDER_CONFIRM, SessionStage.DONE,
        SessionStage.SHOP_RECOMMEND, SessionStage.ANALYZE,
    },
    SessionStage.DONE: {SessionStage.ANALYZE},
}

# 可来回切换的阶段对（用于系统提示词说明）
SWITCHABLE_STAGES = (SessionStage.VIEW_PLAN, SessionStage.DIY_DESIGN)


def can_transition(current: SessionStage, target: SessionStage) -> bool:
    """校验 current -> target 是否为合法流转。"""
    return target in _TRANSITIONS.get(current, set())


def allowed_targets(current: SessionStage):
    """返回当前阶段允许进入的下一阶段（注入提示词，约束模型输出 stage）。"""
    return sorted(target.value for target in _TRANSITIONS.get(current, set()))


def from_str(value: str) -> SessionStage:
    for s in _STAGES:
        if s.value == value:
            return s
    raise ValueError(f"未知阶段: {value}")