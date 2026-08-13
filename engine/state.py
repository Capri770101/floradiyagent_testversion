"""engine/state.py —— 会话状态机与流转校验。

状态机是导购业务的骨架：模型每一步只能按允许的规则推进，避免在「方案确认」
之前就跳去「店铺推荐」这类越界行为。所有流转规则集中在这里，便于测试和审计。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class SessionStage(StrEnum):
    """导购会话阶段。值为小写字符串，直接存库、也可作为前端进度标识。"""

    ANALYZE = "analyze"              # 理解需求，提取预算/对象/偏好
    SELECT_MODE = "select_mode"      # 弹出「现有方案 / DIY」二选一
    VIEW_PLAN = "view_plan"          # 浏览商家预设方案
    DIY_DESIGN = "diy_design"        # 设计 DIY 方案
    IMAGE_GEN = "image_gen"          # DIY 方案异步生图
    PLAN_CONFIRM = "plan_confirm"    # 用户确认方案
    SHOP_RECOMMEND = "shop_recommend"  # 推荐店铺
    ORDER_CONFIRM = "order_confirm"  # 组装订单
    DONE = "done"                    # 已生成支付跳转参数

    @classmethod
    def ordered(cls) -> list[SessionStage]:
        """业务正向推进的标准顺序，用于 stage 索引比较与提示词生成。"""
        return [
            cls.ANALYZE, cls.SELECT_MODE, cls.VIEW_PLAN, cls.DIY_DESIGN,
            cls.IMAGE_GEN, cls.PLAN_CONFIRM, cls.SHOP_RECOMMEND,
            cls.ORDER_CONFIRM, cls.DONE,
        ]


#: 正常前进路径的邻接表（包含「确认前 VIEW_PLAN ↔ DIY_DESIGN 互切」）。
_ALLOWED: Final[dict[SessionStage, set[SessionStage]]] = {
    SessionStage.ANALYZE: {SessionStage.SELECT_MODE},
    SessionStage.SELECT_MODE: {SessionStage.VIEW_PLAN, SessionStage.DIY_DESIGN},
    SessionStage.VIEW_PLAN: {
        SessionStage.DIY_DESIGN,      # 确认前切换到 DIY
        SessionStage.PLAN_CONFIRM,    # 确认当前方案
        SessionStage.SHOP_RECOMMEND,  # 确认即进店铺推荐（PLAN_CONFIRM 由「确认」隐含，不单列一步）
    },
    SessionStage.DIY_DESIGN: {
        SessionStage.VIEW_PLAN,       # 确认前切回现有方案
        SessionStage.IMAGE_GEN,       # 触发生图
        SessionStage.PLAN_CONFIRM,    # 确认当前 DIY 方案
        SessionStage.SHOP_RECOMMEND,  # 确认即进店铺推荐
    },
    SessionStage.IMAGE_GEN: {
        SessionStage.PLAN_CONFIRM,    # 生图完成后确认
        SessionStage.DIY_DESIGN,      # 回到设计微调
        SessionStage.SHOP_RECOMMEND,  # 确认即进店铺推荐
    },
    SessionStage.PLAN_CONFIRM: {SessionStage.SHOP_RECOMMEND},
    SessionStage.SHOP_RECOMMEND: {
        SessionStage.ORDER_CONFIRM,
        SessionStage.PLAN_CONFIRM,    # 换方案可回确认
        SessionStage.DONE,            # 下单后直达完成（ORDER_CONFIRM 由下单隐含）
    },
    SessionStage.ORDER_CONFIRM: {SessionStage.DONE},
    SessionStage.DONE: {SessionStage.ANALYZE},  # 新一轮对话重新开始
}


def can_transition(current: SessionStage, target: SessionStage) -> bool:
    """判断一次阶段流转是否被允许。

    规则：
    1. 保持原阶段永远允许。
    2. 在邻接表内允许（含确认前 VIEW_PLAN ↔ DIY_DESIGN 互切）。
    3. 「放弃订单」兜底：除 SELECT_MODE / DONE 外，任意阶段都可回退到 SELECT_MODE 重选。
    """
    if target == current:
        return True
    if target in _ALLOWED.get(current, set()):
        return True
    # 用户明确放弃 → 回到模式选择（重新来过）
    if target == SessionStage.SELECT_MODE and current not in (
        SessionStage.SELECT_MODE, SessionStage.DONE
    ):
        return True
    return False


def allowed_next(current: SessionStage) -> list[SessionStage]:
    """返回当前阶段的合法下一阶段列表（含放弃回退目标），供提示词/纠错使用。"""
    stages = set(_ALLOWED.get(current, set()))
    if current not in (SessionStage.SELECT_MODE, SessionStage.DONE):
        stages.add(SessionStage.SELECT_MODE)
    return sorted(stages, key=lambda s: SessionStage.ordered().index(s))


#: 每个阶段对模型的「行为指引」，由 agent 注入 system prompt，约束其不跳步。
STAGE_GUIDANCE: Final[dict[SessionStage, str]] = {
    SessionStage.ANALYZE: "先理解用户需求，提取预算、送花对象、偏好色系/花材等关键信息，再进入模式选择。",
    SessionStage.SELECT_MODE: "用 dialog_options 向用户提问：要『现有商家方案』还是『自己 DIY 设计』，二选一。",
    SessionStage.VIEW_PLAN: "调用 search_plans / get_plan_detail 展示商家方案卡片；可切换到 DIY，或让用户确认。",
    SessionStage.DIY_DESIGN: (
        "必须调用 generate_diy_plan（或按反馈调用 revise_diy_plan）产出结构化 DIY 方案——"
        "这是唯一的设计手段，方案会自动写入会话供生图使用。禁止在回复里自行罗列花材/配比/预算"
        "（那会绕过知识库，且生图会因缺少结构化方案而失败）；"
        "禁止编造『自动生成工具失败/有偏差』之类说法——你并没有独立的自动生成工具，"
        "方案不满意请用 revise_diy_plan 调整，不要假装工具出错。"
        "需求零散跨多轮时，先汇总成一句话需求再调用 generate_diy_plan。"
    ),
    SessionStage.IMAGE_GEN: "已提交生图任务，告知用户等待，并提示可通过 /tasks 轮询；完成后回到确认。",
    SessionStage.PLAN_CONFIRM: "向用户确认方案无误；确认后只能进入店铺推荐，不得跳步或回退到浏览。",
    SessionStage.SHOP_RECOMMEND: "调用 search_shops 按距离/价格/评价推荐店铺，给出 shop_card。",
    SessionStage.ORDER_CONFIRM: "调用下单技能组装订单，返回 order_card 与 pay_jump 参数。",
    SessionStage.DONE: (
        "已提供支付跳转参数，等待用户在小程序完成支付。"
        "DONE 是终态，新一轮咨询视为全新开始，不要承接上一轮的未决步骤，也不要主动提及之前的生图/确认环节。"
        "若用户想看或生成效果图，说明希望重新设计：引导其描述新需求开启新一轮对话"
        "（会自动回到方案设计阶段），或提示方案已下单、效果图将在小程序订单中展示；"
        "不要在当前 DONE 阶段调用 generate_effect_image。"
    ),
}
