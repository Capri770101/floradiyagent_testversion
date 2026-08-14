"""agent.py —— 智能体主类：ReAct 主循环 + 会话状态机驱动。

核心职责：
1. 载入短期记忆（历史消息）+ 长期记忆（用户偏好），拼成 system prompt。
2. 进入「思考-行动-观察」循环：call_llm → 解析工具调用 → 执行 → 回填 → 再思考，
   直到模型给出最终回复或达到 max_iterations。
3. 根据本轮工具产出推导 UI 焦点（focus，仅前端高亮）并产出结构化 UI（plan_card / shop_card / pay_jump ...）。
   流程不再由状态机硬锁，用户可随时调用任一 skill（设计/改设计/生图/看店/下单）。
4. 最终根据本轮工具产出结构化 UI（plan_card / shop_card / pay_jump ...）。

说明：
- call_llm 为 OpenAI 兼容真实接口（live-only），必须配置 LLM_API_KEY，已弃用 Mock 引擎。
- 同步存储操作通过 asyncio.to_thread 调用，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import skills  # noqa: F401  —— 触发技能自动注册（create_order 等），仅副作用，名字不直接引用
from config import settings, setup_logging
from engine.llm import call_llm
from engine.state import SessionStage
from engine.ui_protocol import ChatResponse, ToolCallRecord, UIType
from storage import memory as mem_store
from tools import execute_tool, extract_requirement, generate_tool_manual, to_openai_tools

#: 闲聊/寒暄短句词（与花卉导购无关）
_CHITCHAT_WORDS = (
    "你好", "您好", "在吗", "在么", "嗨", "哈喽", "谢谢", "感谢",
    "再见", "拜拜", "哈哈", "辛苦了", "赞", "呵呵",
)


def _clean_reply(text: str) -> str:
    """清理智能体回复里的 markdown 噪声，让前端纯文本渲染更整洁。

    前端不渲染 markdown，因此 ``**加粗**`` 会原样显示成 ``**``；这里统一去除
    ``**`` 与行首 ``#`` 标题符，并把连续空行折叠为单空行，保留有序列表等可读结构。
    """
    if not text:
        return text
    text = text.replace("**", "")          # 去掉加粗符号
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)  # 去标题符
    text = re.sub(r"\n{3,}", "\n\n", text)      # 折叠多余空行
    return text.strip()


def _is_chitchat(text: str) -> bool:
    """判断消息是否与花卉导购无关（纯寒暄/感谢）。用于 DONE 后判断是否开启新会话。"""
    t = text.strip().lower()
    if not t:
        return True
    if any(k in t for k in (
        "买", "送", "花", "束", "预算", "方案", "diy", "自己", "店铺",
        "下单", "订单", "确认", "选", "要", "想要", "需要", "推荐",
        "生图", "效果", "图",
    )):
        return False
    return any(w in t for w in _CHITCHAT_WORDS)

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
        # 透传前端/上轮给定的会话 ID；为空则 memory 层新建一个会话
        sid = mem_store.get_or_create_session(user_id, session_id)
        stage = SessionStage(mem_store.get_stage(sid))
        # 上一单已完成（DONE）且本轮是新的购买需求 → 开启全新会话（旧会话保留在
        # 历史列表里，实现「多轮对话 / 多个对话」），避免旧历史工具调用污染新上下文。
        if stage == SessionStage.DONE and not _is_chitchat(message):
            sid = mem_store.create_conversation(user_id, title=message[:20])
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
        history = mem_store.load_history(sid, settings.history_limit)

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
                # 中间轮（带工具调用）只作模型上下文，不向用户展示：存库时清空 content，
                # 最终展示文本由收尾的 respond_to_user 消息（ui/data）承载，避免重复文本。
                new_msgs.append({**assistant_msg, "content": ""})
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

        # 阶段推进：不再盲信 LLM 在 respond_to_user 填的 stage（live 下 DeepSeek 几乎不填/乱填，
        # 导致 stage 失真、UI 与 stage 严重脱节）。统一改用「用户意图推导 + 工具产出校正」，
        # 与 else/mock 分支逻辑完全一致，保证 live/mock 行为统一、UI 与 stage 始终对齐。
        # LLM 填的 stage 字段在此被忽略（仅 ui/data/reply 仍取自 respond_args）。
        if respond_args is not None:
            new_stage = self._derive_focus(tool_log, incoming, message)
            # DONE 一致性校正：仅当 create_order 真实产出后才允许到达 DONE，
            # 避免用户一句「确认」但店铺还没推荐过时直接结束流程。
            if new_stage == SessionStage.DONE:
                ordered = [tc.name for tc in tool_log if tc.status == "ok"]
                if "create_order" not in ordered:
                    new_stage = SessionStage.SHOP_RECOMMEND if "search_shops" in ordered else incoming
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
            # 仅当 LLM 完全未提供结构化数据（data 为空）时，才用 _derive_ui 依据工具成果
            # 推导的卡片/按钮覆盖：解决「按钮不下发」与「空 dialog_options 无按钮」；若 LLM 已带
            # 有效 data（哪怕 ui=text），则尊重 LLM，不强行覆盖成其它 ui。
            if not data:
                if inferred_ui in _card_types and inferred_data:
                    ui = inferred_ui
                    data = inferred_data
            # plan_card 加固：LLM 常把方案平铺成残缺对象（缺 meaning / packaging /
            # diy_steps / care_tips / budget_breakdown 等字段），而工具（generate_diy_plan）
            # 返回的方案结构完整（design / 花语 / 步骤 / 预算明细齐全）——方案卡片一律
            # 以工具成果为准，保证卡片内容完整，不被 LLM 平铺数据覆盖。
            elif ui == UIType.PLAN_CARD and inferred_ui == UIType.PLAN_CARD and inferred_data:
                ui = inferred_ui
                data = inferred_data
            # 生图结果兜底：本轮若 generate_effect_image 真实成功（工具已返回 task_id），
            # 强制下发任务信息，避免 LLM 在 respond_to_user 漏填 data.task_id，
            # 导致前端收不到 task_id、不发起 /tasks 轮询、图片永不渲染。
            # 同步 provider 已 done 且带 result_url → image_task 卡片直渲；
            # 异步 pending（仅 task_id）→ text + task_id 提示，由前端轮询。
            if inferred_data.get("task_id"):
                if inferred_data.get("result_url"):
                    ui = UIType.IMAGE_TASK
                    data = {
                        "task_id": inferred_data["task_id"],
                        "poll": inferred_data.get("poll"),
                        "result_url": inferred_data["result_url"],
                    }
                else:
                    ui = UIType.TEXT
                    data = {"task_id": inferred_data["task_id"], "poll": inferred_data.get("poll")}
            final_reply = str(respond_args.get("reply", final_reply) or final_reply)
            # 空回复兜底：LLM 偶尔调 respond_to_user 时 reply 为空字符串，导致前端
            # 看似没有回复。有工具成果 → 引导查看卡片；否则给出通用的收到提示。
            if not final_reply:
                if tool_log:
                    final_reply = "我已经为你整理好相关结果啦，请查看下方卡片～"
                else:
                    final_reply = "好的，收到你的想法啦，请稍等～"
            # options 契约归一化：LLM 常把选项直接写成字符串数组，而前端 Pill 期望
            # {label, value} 对象——统一转成对象，避免空按钮 / 点击无效。
            if ui == UIType.DIALOG_OPTIONS and isinstance(data.get("options"), list):
                data["options"] = [
                    o if isinstance(o, dict) and o.get("label")
                    else {"label": str(o), "value": str(o)}
                    for o in data["options"]
                ]
            # 生图 ui 加固：image_task 的 task_id 必须以工具真实产出为准——LLM 常在生图
            # 工具被拦 / 未调用时，幻觉编造 task_id（如 "DIY_xxx_effect"）谎报成功，
            # 前端轮询会 404 卡 pending。有真实 task_id → 保留（done 带 result_url 直渲，
            # 否则前端轮询）；本轮没有真实生图 → 降级纯文本，绝不透传幻觉数据。
            if ui == UIType.IMAGE_TASK:
                if inferred_data.get("task_id"):
                    data = {
                        "task_id": inferred_data["task_id"],
                        "poll": inferred_data.get("poll"),
                    }
                    if inferred_data.get("result_url"):
                        data["result_url"] = inferred_data["result_url"]
                else:
                    ui = UIType.TEXT
                    data = {}
        else:
            # 仅依据「本轮用户消息意图 + 当前阶段」推导，不在循环内随工具跳变，
            # 避免同一轮里 Mock 误把 VIEW_PLAN 当成已确认而去调 search_shops。
            new_stage = self._derive_focus(tool_log, incoming, message)
            # 一致性校正：阶段推进与实际工具产出对齐，杜绝「环节错乱」——
            # - DONE 只能在 create_order 真实产出后到达（用户刚说「确认」但店铺还没推荐过时，
            #   本轮产出的是 shop_card，阶段应停在 SHOP_RECOMMEND 而不是直接结束）；
            # - 同理 SHOP_RECOMMEND 的确认消息若本轮只产出了方案/生图结果，也不得跳过店铺推荐。
            if new_stage == SessionStage.DONE:
                ordered = [tc.name for tc in tool_log if tc.status == "ok"]
                if "create_order" not in ordered:
                    new_stage = SessionStage.SHOP_RECOMMEND if "search_shops" in ordered else incoming
            ui, data = self._derive_ui(tool_log, new_stage, final_reply)

        # 生图确认关卡（两条路径）：
        # 1) 阶段推进到 IMAGE_GEN（工具成功产出效果图任务 / stage 迁移）——进入即置位；
        # 2) 用户消息直接表达生图意图（含「效果图 / 生图 / 生成」）——即使本轮
        #    generate_effect_image 被闸门拦截（无 ok 产出、阶段不推进），也视为已确认。
        #    live 已复现：用户说「确认方案，生成效果图吧」，LLM 先调生图工具被拦，
        #    若只依赖工具产出推导（_derive_focus 只认 ok），image_confirmed 永不置位，
        #    LLM 转而谎报「正在生成」，图永远出不来。
        _img_intent = any(w in message for w in ("效果图", "生图", "生成"))
        if new_stage == SessionStage.IMAGE_GEN and new_stage != incoming:
            mem_store.clear_session_flags(user_id, sid, prefix="image_")
            mem_store.set_session_flag(user_id, sid, "image_confirmed", "1")
        elif (
            _img_intent
            and incoming in (SessionStage.DIY_DESIGN, SessionStage.IMAGE_GEN)
            and mem_store.get_session_flag(user_id, sid, "image_confirmed") != "1"
        ):
            mem_store.set_session_flag(user_id, sid, "image_confirmed", "1")
        # 生图强制收敛（live 兜底）：用户已确认生图（image_confirmed 置位），但至今未真正调用
        # generate_effect_image（live 下 LLM 常只用文字"正在生成"而不调工具，或说"生成吧"后直接
        # 跳去店铺推荐），则在此补调一次，保证前端能拿到 task_id 轮询渲染。
        # 闸门从「必须停留在 IMAGE_GEN」放宽到「已确认 + 至今未生成 + 未到终态」，以覆盖
        # "用户说生成吧后 LLM 直接推进到 shop_recommend" 的 live 场景——否则图会再次丢。
        # 工具内部 image_submitted 标记防重复生图；一旦成功产出 eff_done=True 即不再补调。
        eff_confirmed = mem_store.get_session_flag(user_id, sid, "image_confirmed") == "1"
        eff_done = any(tc.name == "generate_effect_image" and tc.status == "ok" for tc in tool_log)
        if eff_confirmed and not eff_done and new_stage not in (
            SessionStage.DONE, SessionStage.ORDER_CONFIRM
        ):
            try:
                from tools import generate_effect_image as _gei
                # 生图工具内置安全闸门会校验「当前阶段==IMAGE_GEN 且已确认」，而本兜底补调
                # 发生在最终 update_stage 之前，DB 阶段仍是旧值（如 diy_design），会触发闸门报错、
                # 导致 task_id 拿不到。故调用前先把阶段临时置为 IMAGE_GEN 放行，
                # 末尾的 update_stage(new_stage) 仍会把阶段修正回真实值（如 shop_recommend）。
                mem_store.update_stage(sid, SessionStage.IMAGE_GEN.value)
                raw = _gei("latest_diy", {"user_id": user_id, "session_id": sid, "location": location})
                eff = json.loads(raw)
                if "task_id" in eff:
                    ui = UIType.TEXT
                    data = {"task_id": eff["task_id"], "poll": eff.get("poll", True)}
                    final_reply = "正在为您生成效果图预览，请稍候～ 🎨"
                    tool_log.append(ToolCallRecord(
                        name="generate_effect_image",
                        arguments={"plan": "latest_diy"},
                        result=raw, status="ok",
                    ))
                    new_msgs.append({"role": "tool", "content": raw, "tool_call_id": "forced_effect_image"})
                    logger.info("[agent] 生图补调成功 task_id=%s", eff["task_id"])
            except Exception:  # noqa: BLE001
                logger.exception("[agent] 生图补调失败")

        # 持久化本轮新增消息 + 最新阶段
        # 追加一条「展示用」助手消息（携带 ui/data），供前端会话回放直接渲染结构化卡片
        # 回复文本统一清理 markdown 噪声（去除 ** / #，折叠空行），保证纯文本渲染整洁。
        final_reply = _clean_reply(final_reply)
        new_msgs.append({"role": "assistant", "content": final_reply, "ui": ui.value, "data": data})
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
        """构造 system prompt：身份 + skill 编排说明 + 记忆 + 工具说明。

        skill 编排模式：不限制流程顺序，用户可随时调用任一 skill（设计/改设计/生图/
        看店/下单），包括中途返回修改方案。stage 参数仅保留兼容，不再注入 prompt。
        """
        parts = [
            "你是「花卉 DIY 设计智能体」，帮助用户设计花艺方案、生成效果图、推荐店铺并下单。用简洁中文回复。",
            "## 你的能力（skill，顺序不限、可重复、可中途返回修改）",
            "- generate_diy_plan：根据需求设计一版花艺方案（花材/配比/色彩/寓意/包装/预算）。",
            "- revise_diy_plan：在已有方案基础上修改（换花材、调预算、改风格等）。",
            "- generate_effect_image：基于已设计方案生成效果图（需先有方案）。",
            "- search_shops / search_plans：检索店铺或现有方案。",
            "- create_order：选定店铺与方案后生成订单与支付跳转。",
            "- respond_to_user：当无需再调工具、直接回复用户时调用，并给出 ui/data（卡片/按钮）。",
            "## 原则",
            "1. 用户随时可打断、改需求、回退；不要强推固定流程。",
            "2. 生图前必须已有方案；无方案时先引导用户设计。",
            "3. 下单前必须已推荐店铺且用户已选定。",
        ]
        if long_term:
            mem = "；".join(f"{k}={v}" for k, v in long_term.items())
            parts.append("## 用户长期偏好（来自记忆，回复时参考）：" + mem)
        parts.append(
            "## 回复格式要求\n"
            "- 回复要简短：方案、店铺、订单等结构化内容会以卡片形式展示给用户，"
            "文字里只给结论 + 一句行动建议，不要重复罗列卡片已有的细节"
            "（花材明细、寓意、包装、养护、步骤、价格清单等）。\n"
            "- 设计完方案后：一句『方案已设计好，点击卡片可查看详情』即可，花材寓意等交给卡片。\n"
            "- 生成效果图后：一句『效果图已生成，展开方案卡片即可查看』即可，不要描述画面细节。\n"
            "- 不要使用 ** 这种 markdown 加粗符号，也不要用 # 标题符。\n"
            "- 术语准确、语气亲切，像一位专业花艺师在简短讲解，而不是罗列参数。"
        )
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
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            tid = getattr(tc, "id", "")
            calls.append({"id": tid, "name": name, "arguments": args})
        return calls

    @staticmethod
    def _derive_focus(
        tool_log: list[ToolCallRecord], incoming: SessionStage, message: str
    ) -> SessionStage:
        """基于本轮工具产出推导 UI 焦点（focus），不再做状态机拦截。

        skill 编排模式下，focus 仅用于前端高亮「用户当前在做什么」，不限制流程：
        - 有订单 → done；有店铺 → shop_recommend；有生图 → image_gen；
        - 有方案（generate_diy_plan / search_plans）→ diy_design；
        - 否则保持进入时的焦点（incoming），避免无工具轮次焦点乱跳。
        """
        ordered = [tc.name for tc in tool_log if tc.status == "ok"]
        if "create_order" in ordered:
            return SessionStage.DONE
        if "search_shops" in ordered:
            return SessionStage.SHOP_RECOMMEND
        if "generate_effect_image" in ordered:
            return SessionStage.IMAGE_GEN
        if "generate_diy_plan" in ordered or "search_plans" in ordered:
            return SessionStage.DIY_DESIGN
        return incoming

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
            data: dict[str, Any] = {
                "task_id": r.get("task_id"),
                "poll": r.get("poll"),
            }
            if r.get("result_url"):
                data["result_url"] = r["result_url"]
            return UIType.IMAGE_TASK, data
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
