"""agent.py —— 智能体主类：ReAct 主循环 + 会话状态机驱动。

核心职责：
1. 载入短期记忆（历史消息）+ 长期记忆（用户偏好），拼成 system prompt。
2. 进入「思考-行动-观察」循环：call_llm → 解析工具调用 → 执行 → 回填 → 再思考，
   直到模型给出最终回复或达到 max_iterations。
3. 根据「调用的工具」结合状态机推进会话阶段（VIEW_PLAN / DIY_DESIGN / ... / DONE）。
4. 最终根据本轮工具产出结构化 UI（plan_card / shop_card / pay_jump ...）。

说明：
- call_llm 兼容 OpenAI / Mock 双轨；未配置密钥时自动走 Mock，保证零配置可跑通。
- 同步存储操作通过 asyncio.to_thread 调用，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import skills  # noqa: F401  —— 触发技能自动注册（create_order 等），仅副作用，名字不直接引用
from config import settings, setup_logging
from engine.llm import _is_chitchat, call_llm
from engine.state import STAGE_GUIDANCE, SessionStage, can_transition
from engine.ui_protocol import ChatResponse, ToolCallRecord, UIType
from storage import memory as mem_store
from tools import execute_tool, extract_requirement, generate_tool_manual, to_openai_tools

logger = logging.getLogger("agent")

# 生图确认关卡的意图识别（后端判定，不依赖模型自觉）—— 融合自 111：
# 进入 IMAGE_GEN 阶段后，只有用户明确肯定才写入 image_confirmed 标记，
# generate_effect_image 工具据此放行。否定词优先于肯定词。
_AFFIRMATIVE = ("好", "可以", "确认", "同意", "生成", "要", "行", "是", "看看")
_NEGATIVE = ("不用", "不要", "不需要", "不必", "算了", "跳过", "无需", "别", "放弃")


def is_affirmative(text: str) -> bool:
    """判断用户消息是否为明确肯定意图（用于生图确认等关卡）。"""
    t = (text or "").strip()
    if not t:
        return False
    if any(k in t for k in _NEGATIVE):
        return False
    return any(k in t for k in _AFFIRMATIVE)


#: 允许的角色-动作矩阵（本期只放行 user）
_ROLE_ACTIONS: dict[str, set[str]] = {
    "user": {"chat", "reset", "tasks"},
    "merchant": set(),
    "admin": set(),
}


def is_allowed(role: str, action: str) -> bool:
    """权限钩子：判断某角色是否可执行某动作。本期仅 user 放行。"""
    return action in _ROLE_ACTIONS.get(role, set())


class ReActAgent:
    """基于 ReAct + 状态机的导购智能体。"""

    async def arun(
        self,
        user_id: str,
        message: str,
        session_id: str | None = None,
        user_role: str = "user",
        location: dict[str, float] | None = None,
    ) -> ChatResponse:
        """异步入口：做权限校验后，用线程池跑同步主循环。"""
        if not is_allowed(user_role, "chat"):
            raise PermissionError(f"角色 {user_role} 无权执行 chat 动作")
        return await asyncio.to_thread(
            self.run, user_id, message, session_id, user_role, location
        )

    # ------------------------------------------------------------------ #
    # 主循环（同步，运行在 to_thread 中）
    # ------------------------------------------------------------------ #

    def run(
        self,
        user_id: str,
        message: str,
        session_id: str | None,
        user_role: str,
        location: dict[str, float] | None,
    ) -> ChatResponse:
        t0 = time.perf_counter()
        sid = mem_store.get_or_create_session(user_id)
        stage = SessionStage(mem_store.get_stage(sid))
        # 上一单已完成（DONE）且本轮是新的购买需求 → 自动开启全新会话。
        # 会话是 user 1:1 复用：不清空的话用户会永远卡在「感谢您的选购」出不来，
        # 且旧历史的工具调用会污染 Mock/LLM 上下文（环节错乱的一大来源）。
        if stage == SessionStage.DONE and not _is_chitchat(message):
            mem_store.reset_session(user_id)
            sid = mem_store.get_or_create_session(user_id)
            stage = SessionStage.ANALYZE
        # 结构化需求状态：每轮从用户消息抽取并与历史累加，持久化到会话记忆，
        # 再注入工具上下文，供 search_plans / list_shops 按需求检索。
        existing_req = mem_store.get_requirement(sid)
        turn_req = extract_requirement(message)
        req = existing_req.merge(turn_req) if existing_req else turn_req
        if location and not req.location:
            req.location = location
        mem_store.set_requirement(sid, req)
        stage = SessionStage(mem_store.get_stage(sid))
        incoming = stage  # 本轮进入时的阶段，循环内保持稳定
        # 生图确认关卡：进入 IMAGE_GEN 阶段后，用户明确肯定才写入 image_confirmed（融合自 111）
        if stage == SessionStage.IMAGE_GEN and is_affirmative(message):
            mem_store.set_session_flag(user_id, sid, "image_confirmed", "1")
        long_term = mem_store.get_long_term(user_id)
        history = mem_store.load_history(user_id, settings.history_limit)

        system = self._build_system(stage, long_term)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages += history
        messages.append({"role": "user", "content": message})

        tool_log: list[ToolCallRecord] = []
        respond_args: dict[str, Any] | None = None  # 终结工具 respond_to_user 携带的参数
        final_reply = ""
        new_msgs: list[dict[str, Any]] = [{"role": "user", "content": message}]

        for turn in range(1, settings.max_iterations + 1):
            logger.info("[agent] ReAct 第 %d/%d 轮 阶段=%s", turn, settings.max_iterations, stage.value)
            try:
                resp = call_llm(messages, tools=to_openai_tools())
            except Exception as exc:  # noqa: BLE001
                logger.exception("[agent] LLM 调用失败")
                final_reply = f"抱歉，模型调用出错：{exc}"
                break

            msg = resp.choices[0].message
            tool_calls = self._parse_tool_calls(msg)
            if tool_calls:
                # 回注给 LLM 的 assistant 消息必须遵循 OpenAI 规范：
                # 每条 tool_call 需含 type="function"，且 function.arguments 为 JSON 字符串。
                # Mock 不校验格式，但真实 DeepSeek/OpenAI 接口会 400 报 missing field 'type'。
                assistant_msg = {
                    "role": "assistant",
                    "content": getattr(msg, "content", "") or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                messages.append(assistant_msg)
                new_msgs.append(assistant_msg)
                for tc in tool_calls:
                    if tc["name"] == "respond_to_user":
                        # 终结信号：记录参数，回填一条 tool 观测（OpenAI 协议要求），随后跳出 ReAct 循环
                        respond_args = tc["arguments"]
                        obs = json.dumps(respond_args, ensure_ascii=False)
                        messages.append({"role": "tool", "content": obs, "tool_call_id": tc.get("id", "")})
                        new_msgs.append({"role": "tool", "content": obs, "tool_call_id": tc.get("id", "")})
                        continue
                    result, status = execute_tool(
                        tc["name"], tc["arguments"],
                        {"user_id": user_id, "session_id": sid, "location": location, "requirement": req},
                    )
                    record = ToolCallRecord(
                        name=tc["name"], arguments=tc["arguments"], result=result, status=status
                    )
                    tool_log.append(record)
                    # 回填 observation
                    messages.append({"role": "tool", "content": result, "tool_call_id": tc.get("id", "")})
                    new_msgs.append({"role": "tool", "content": result, "tool_call_id": tc.get("id", "")})
                if respond_args is not None:
                    break  # 终结工具触发，不再让模型继续思考
                # 带着 observation 再思考一轮（让模型产出最终回复 / 下一步）
                continue
            else:
                final_reply = getattr(msg, "content", "") or ""
                messages.append({"role": "assistant", "content": final_reply})
                new_msgs.append({"role": "assistant", "content": final_reply})
                break
        else:
            # 超出 max_iterations：强制收尾，避免无限循环。
            # 若本轮工具已产生有效成果（方案/店铺/订单），则保留成果、用中性文案收尾，
            # 由下方 _derive_ui 渲染对应卡片，不再武断回「思考太久」——用户实际已拿到方案，
            # 只是 LLM 没自觉调用 respond_to_user 收尾。仅当全程无任何成功工具调用（纯空转）才回退超时提示。
            if any(tc.status == "ok" for tc in tool_log):
                final_reply = final_reply or "我已经为你整理好相关结果啦，请查看下方卡片～"
            else:
                final_reply = final_reply or "抱歉，我思考得太久啦，请简化需求或分步骤再问我～"

        # 阶段推进：respond_to_user 携带的 stage 优先（经状态机校验），否则按意图推导
        if respond_args is not None:
            target_stage_str = str(respond_args.get("stage", incoming.value))
            try:
                target = SessionStage(target_stage_str)
            except ValueError:
                target = incoming
            if not can_transition(incoming, target):
                target = incoming
            new_stage = target
            ui_arg = str(respond_args.get("ui", ""))
            try:
                ui = UIType(ui_arg)
            except ValueError:
                ui = UIType.TEXT
            data_arg = respond_args.get("data") or {}
            data = data_arg if isinstance(data_arg, dict) else {}

            # 工具推导的卡片/按钮 ui（依据本轮工具成果或当前阶段）
            inferred_ui, inferred_data = self._derive_ui(tool_log, new_stage, final_reply)
            # 关键修复：LLM 在 respond_to_user 中常只填 ui=text + 空 data，导致 _derive_ui
            # 本应产出的卡片/按钮（模式选择 / 确认方案 / 选店铺 / 去支付）被整体丢弃，
            # 前端按钮分支形同死代码。当 LLM 未给出有效卡片（非卡片类 ui 或 data 为空），
            # 但工具已有可渲染成果时，强制采用 _derive_ui 的结构化卡片，保证 UI 契约落地。
            # 若 LLM 已正确填了卡片类 ui 且 data 非空，则尊重 LLM（不覆盖）。
            _card_types = {
                UIType.DIALOG_OPTIONS, UIType.PLAN_CARD,
                UIType.SHOP_CARD, UIType.ORDER_CARD, UIType.PAY_JUMP,
            }
            if ui not in _card_types or not data:
                if inferred_ui in _card_types and inferred_data:
                    ui = inferred_ui
                    data = inferred_data
            # 生图结果兜底：本轮若 generate_effect_image 真实成功（工具已返回 task_id），
            # 强制走 text 分支并注入 task_id，避免 LLM 在 respond_to_user 漏填 data.task_id，
            # 导致前端收不到 task_id、不发起 /tasks 轮询、图片永不渲染。
            if inferred_data.get("task_id"):
                ui = UIType.TEXT
                data = {"task_id": inferred_data["task_id"], "poll": inferred_data.get("poll")}
            final_reply = str(respond_args.get("reply", final_reply) or final_reply)
        else:
            # 仅依据「本轮用户消息意图 + 当前阶段」推导，不在循环内随工具跳变，
            # 避免同一轮里 Mock 误把 VIEW_PLAN 当成已确认而去调 search_shops。
            new_stage = self._derive_next_stage(incoming, message)
            if not can_transition(incoming, new_stage):
                new_stage = incoming
            # 一致性校正：阶段推进与实际工具产出对齐，杜绝「环节错乱」——
            # - DONE 只能在 create_order 真实产出后到达（用户刚说「确认」但店铺还没推荐过时，
            #   本轮产出的是 shop_card，阶段应停在 SHOP_RECOMMEND 而不是直接结束）；
            # - 同理 SHOP_RECOMMEND 的确认消息若本轮只产出了方案/生图结果，也不得跳过店铺推荐。
            if new_stage == SessionStage.DONE:
                ordered = [tc.name for tc in tool_log if tc.status == "ok"]
                if "create_order" not in ordered:
                    new_stage = SessionStage.SHOP_RECOMMEND if "search_shops" in ordered else incoming
            ui, data = self._derive_ui(tool_log, new_stage, final_reply)

        # 进入生图确认阶段：每次进入须重新征求确认，清除历史 image_* 标记（融合自 111）。
        # 若用户本轮消息本身就是明确生图请求（如「生成效果图看看」），直接视为已确认，
        # 避免「明明说了生成、还要再确认一次」的体验断裂。
        if new_stage == SessionStage.IMAGE_GEN and new_stage != incoming:
            mem_store.clear_session_flags(user_id, sid, prefix="image_")
            if is_affirmative(message):
                mem_store.set_session_flag(user_id, sid, "image_confirmed", "1")

        # 持久化本轮新增消息 + 最新阶段
        mem_store.save_messages(sid, new_msgs)
        mem_store.update_stage(sid, new_stage.value)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("[agent] 完成 阶段=%s ui=%s 耗时=%.0fms", new_stage.value, ui.value, elapsed)
        return ChatResponse(
            user_id=user_id,
            reply=final_reply,
            ui=ui,
            data=data,
            tool_calls=tool_log,
            session_id=sid,
            stage=new_stage.value,
        )

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    def _build_system(self, stage: SessionStage, long_term: dict[str, str]) -> str:
        """构造 system prompt：身份 + 当前阶段指引 + 状态机约束 + 记忆 + 工具说明。"""
        parts = [
            "你是「花卉导购智能体」，帮助用户在微信小程序里买花或送花。用简洁中文回复。",
            f"## 当前会话阶段：{stage.value}",
            "本阶段指引：" + STAGE_GUIDANCE.get(stage, ""),
            "## 状态机约束：PLAN_CONFIRM 之前可在「现有方案」与「DIY」间切换；"
            "确认方案后才进入店铺推荐，不得跳步；用户明确放弃可回退到模式选择。",
        ]
        if long_term:
            mem = "；".join(f"{k}={v}" for k, v in long_term.items())
            parts.append("## 用户长期偏好（来自记忆，回复时参考）：" + mem)
        parts.append("## 工具说明书\n" + generate_tool_manual())
        return "\n\n".join(parts)

    @staticmethod
    def _parse_tool_calls(msg: Any) -> list[dict[str, Any]]:
        """兼容 OpenAI（msg.tool_calls[i].function）与 Mock（_MockToolCall）。"""
        raw = getattr(msg, "tool_calls", None)
        if not raw:
            return []
        calls: list[dict[str, Any]] = []
        for tc in raw:
            if hasattr(tc, "function"):  # OpenAI 风格
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                tid = getattr(tc, "id", "")
            else:  # Mock 风格
                name = tc.name
                args = tc.arguments
                tid = ""
            calls.append({"id": tid, "name": name, "arguments": args})
        return calls

    @staticmethod
    def _derive_next_stage(current: SessionStage, message: str) -> SessionStage:
        """依据当前阶段 + 用户消息意图推导下一阶段（状态机业务骨架）。

        阶段推进只由「用户消息意图」驱动，与具体调用了哪个工具解耦：
        - 浏览/设计阶段只有「明确确认/选定」才前进，普通提问、描述、闲聊一律停留，
          避免用户问一句「这个多少钱」就被推进到店铺推荐（环节错乱）。
        - 生图意图把 DIY 设计引导到 IMAGE_GEN；生图确认后才进店铺推荐。
        - 店铺推荐阶段选定店铺才结束，未选定不跳步。
        """
        from engine.llm import _intent, _is_chitchat

        if _is_chitchat(message):
            return current  # 闲聊不推进
        intent = _intent(message)

        if current == SessionStage.ANALYZE:
            return SessionStage.SELECT_MODE
        if current == SessionStage.SELECT_MODE:
            return SessionStage.DIY_DESIGN if intent["diy"] else SessionStage.VIEW_PLAN
        if current == SessionStage.VIEW_PLAN:
            if intent["abandon"]:
                return SessionStage.SELECT_MODE
            if intent["diy"]:
                return SessionStage.DIY_DESIGN
            if intent["confirm"] or intent["pick_shop"]:
                return SessionStage.SHOP_RECOMMEND
            return current
        if current == SessionStage.DIY_DESIGN:
            if intent["abandon"]:
                return SessionStage.SELECT_MODE
            if intent["image"]:
                return SessionStage.IMAGE_GEN
            if intent["confirm"]:
                return SessionStage.SHOP_RECOMMEND
            return current
        if current == SessionStage.IMAGE_GEN:
            if intent["abandon"]:
                return SessionStage.SELECT_MODE
            if intent["confirm"]:
                return SessionStage.SHOP_RECOMMEND
            return current
        if current == SessionStage.SHOP_RECOMMEND:
            if intent["abandon"]:
                return SessionStage.SELECT_MODE
            if intent["confirm"] or intent["pick_shop"]:
                return SessionStage.DONE
            return current
        return current

    @staticmethod
    def _last_ok_result(tool_log: list[ToolCallRecord], name: str) -> dict[str, Any]:
        for tc in reversed(tool_log):
            if tc.name == name and tc.status == "ok":
                try:
                    return json.loads(tc.result)
                except (json.JSONDecodeError, TypeError):
                    return {}
        return {}

    def _derive_ui(
        self, tool_log: list[ToolCallRecord], stage: SessionStage, reply: str
    ) -> tuple[UIType, dict[str, Any]]:
        """根据本轮工具产出决定 ui 类型与 data。"""
        last = None
        for tc in reversed(tool_log):
            if tc.status == "ok":
                last = tc.name
                break

        if last in ("search_plans", "get_plan_detail"):
            return UIType.PLAN_CARD, {"plans": self._last_ok_result(tool_log, last)}
        if last == "generate_diy_plan":
            return UIType.PLAN_CARD, {"plans": [self._last_ok_result(tool_log, last)]}
        if last == "search_shops":
            return UIType.SHOP_CARD, {"shops": self._last_ok_result(tool_log, last)}
        if last == "generate_effect_image":
            r = self._last_ok_result(tool_log, last)
            return UIType.TEXT, {"task_id": r.get("task_id"), "poll": r.get("poll")}
        if last == "create_order":
            r = self._last_ok_result(tool_log, last)
            pay_jump = r.get("pay_jump", {})
            return UIType.PAY_JUMP, pay_jump

        # 无工具：按阶段给 UI
        if stage == SessionStage.SELECT_MODE:
            return UIType.DIALOG_OPTIONS, {
                "options": [
                    {"label": "商家现有方案", "value": "existing"},
                    {"label": "自己 DIY 设计", "value": "diy"},
                ]
            }
        return UIType.TEXT, {}


if __name__ == "__main__":
    setup_logging()
    from storage.db import init_db

    init_db()
    agent = ReActAgent()
    user_msg = "想给母亲买一束花，预算 200 元左右"
    result = agent.run("cli_user", user_msg)
    print(result.model_dump_json(indent=2))
