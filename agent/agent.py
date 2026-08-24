from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from agent import (
    skills,  # noqa: F401
)
from agent.engine.llm import call_llm
from agent.engine.state import SessionStage
from agent.engine.ui_protocol import ChatResponse, ToolCallRecord, UIType
from agent.tools import execute_tool, extract_requirement, generate_tool_manual, to_openai_tools
from backend.config import settings, setup_logging
from backend.storage import memory as mem_store

_CHITCHAT_WORDS = (
    "你好", "您好", "在吗", "在么", "嗨", "哈喽", "谢谢", "感谢",
    "再见", "拜拜", "哈哈", "辛苦了", "赞", "呵呵",
)

_BUY_INTENT = (
    "买", "送", "下单", "购买", "付款", "支付", "选一束", "挑一束",
    "想要", "需要", "来一束", "订一束",
)


def _clean_reply(text: str) -> str:
    if not text:
        return text
    text = text.replace("**", "")
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_chitchat(text: str) -> bool:
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

_AFFIRMATIVE = ("好", "可以", "确认", "同意", "生成", "要", "行", "是", "看看")
_NEGATIVE = ("不用", "不要", "不需要", "不必", "算了", "跳过", "无需", "别", "放弃")


def is_affirmative(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(k in t for k in _NEGATIVE):
        return False
    return any(k in t for k in _AFFIRMATIVE)


_ROLE_ACTIONS: dict[str, set[str]] = {
    "user": {"chat", "reset", "tasks"},
    "merchant": set(),
    "admin": set(),
}


def is_allowed(role: str, action: str) -> bool:
    return action in _ROLE_ACTIONS.get(role, set())


class ReActAgent:
    async def arun(
        self,
        user_id: str,
        message: str,
        session_id: str | None = None,
        user_role: str = "user",
        location: dict[str, float] | None = None,
    ) -> ChatResponse:
        if not is_allowed(user_role, "chat"):
            raise PermissionError(f"角色 {user_role} 无权执行 chat 动作")
        return await asyncio.to_thread(
            self.run, user_id, message, session_id, user_role, location
        )

    def run(
        self,
        user_id: str,
        message: str,
        session_id: str | None,
        user_role: str,
        location: dict[str, float] | None,
    ) -> ChatResponse:
        t0 = time.perf_counter()
        sid = mem_store.get_or_create_session(user_id, session_id)
        stage = SessionStage(mem_store.get_stage(sid))
        if stage == SessionStage.DONE and not _is_chitchat(message):
            sid = mem_store.create_conversation(user_id, title=message[:20])
            stage = SessionStage.ANALYZE
        existing_req = mem_store.get_requirement(sid)
        turn_req = extract_requirement(message)
        req = existing_req.merge(turn_req) if existing_req else turn_req
        if location and not req.location:
            req.location = location
        mem_store.set_requirement(sid, req)
        stage = SessionStage(mem_store.get_stage(sid))
        incoming = stage
        if stage == SessionStage.IMAGE_GEN and is_affirmative(message):
            mem_store.set_session_flag(user_id, sid, "image_confirmed", "1")
        long_term = mem_store.get_long_term(user_id)
        history = mem_store.load_history(sid, settings.history_limit)

        system = self._build_system(stage, long_term)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages += history
        messages.append({"role": "user", "content": message})

        tool_log: list[ToolCallRecord] = []
        respond_args: dict[str, Any] | None = None
        final_reply = ""
        new_msgs: list[dict[str, Any]] = [{"role": "user", "content": message}]

        for turn in range(1, settings.max_iterations + 1):
            logger.info("[agent] ReAct 第 %d/%d 轮 阶段=%s", turn, settings.max_iterations, stage.value)
            try:
                resp = call_llm(messages, tools=to_openai_tools())
            except Exception as exc:
                logger.exception("[agent] LLM 调用失败")
                final_reply = f"抱歉，模型调用出错：{exc}"
                break

            msg = resp.choices[0].message
            tool_calls = self._parse_tool_calls(msg)
            if tool_calls:
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
                new_msgs.append({**assistant_msg, "content": ""})
                for tc in tool_calls:
                    if tc["name"] == "respond_to_user":
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
                    messages.append({"role": "tool", "content": result, "tool_call_id": tc.get("id", "")})
                    new_msgs.append({"role": "tool", "content": result, "tool_call_id": tc.get("id", "")})
                if respond_args is not None:
                    break
                continue
            else:
                final_reply = getattr(msg, "content", "") or ""
                messages.append({"role": "assistant", "content": final_reply})
                break
        else:
            if any(tc.status == "ok" for tc in tool_log):
                final_reply = final_reply or "我已经为你整理好相关结果啦，请查看下方卡片～"
            else:
                final_reply = final_reply or "抱歉，我思考得太久啦，请简化需求或分步骤再问我～"

        if respond_args is not None:
            new_stage = self._derive_focus(tool_log, incoming, message)
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
            if self._validate_respond_data(ui, data) is None:
                data = {}

            inferred_ui, inferred_data = self._derive_ui(tool_log, new_stage, final_reply)
            _card_types = {
                UIType.DIALOG_OPTIONS, UIType.PLAN_CARD,
                UIType.SHOP_CARD, UIType.ORDER_CARD, UIType.PAY_JUMP,
            }
            _data_effective = bool(data) and not (
                ui == UIType.IMAGE_TASK
                and not (data.get("task_id") or data.get("result_url"))
            )
            if not _data_effective:
                if inferred_ui in _card_types and inferred_data:
                    ui = inferred_ui
                    data = inferred_data
            elif ui == UIType.PLAN_CARD and inferred_ui == UIType.PLAN_CARD and inferred_data:
                ui = inferred_ui
                data = inferred_data
            if inferred_ui in (UIType.ORDER_CARD, UIType.PAY_JUMP) and inferred_data.get("pay_jump"):
                ui = UIType.PAY_JUMP
                data = inferred_data
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
            if not final_reply.strip():
                if tool_log:
                    final_reply = "我已经为你整理好相关结果啦，请查看下方卡片～"
                else:
                    final_reply = "好的，收到你的想法啦，请稍等～"
            if ui == UIType.DIALOG_OPTIONS and isinstance(data.get("options"), list):
                data["options"] = [
                    o if isinstance(o, dict) and o.get("label")
                    else {"label": str(o), "value": str(o)}
                    for o in data["options"]
                ]
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
            if ui == UIType.SHOP_CARD:
                if inferred_ui == UIType.SHOP_CARD and inferred_data.get("shops"):
                    ui = inferred_ui
                    data = inferred_data
                else:
                    ui = UIType.TEXT
                    data = {}
        else:
            new_stage = self._derive_focus(tool_log, incoming, message)
            if new_stage == SessionStage.DONE:
                ordered = [tc.name for tc in tool_log if tc.status == "ok"]
                if "create_order" not in ordered:
                    new_stage = SessionStage.SHOP_RECOMMEND if "search_shops" in ordered else incoming
            ui, data = self._derive_ui(tool_log, new_stage, final_reply)

        llm_intent = ""
        if respond_args is not None:
            llm_intent = str(respond_args.get("intent", "") or "")

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
        if (
            any(w in message for w in (
                "确认方案", "确认这个方案", "就这个", "定这个", "就它", "这个方案", "方案可以",
            ))
            or (is_affirmative(message) and "方案" in message)
        ):
            try:
                from backend.storage.diy import save_diy_plan
                _diy = mem_store.get_session_json(user_id, sid, "latest_diy_plan")
                if _diy and _diy.get("diy"):
                    if not (_diy.get("result_url") or _diy.get("effect_image_url")):
                        try:
                            from backend.storage.tasks import get_image_task
                            for _m in reversed(mem_store.load_display_messages(sid)):
                                _d = _m.get("data") if isinstance(_m.get("data"), dict) else {}
                                if _d.get("task_id"):
                                    _t = get_image_task(str(_d["task_id"]))
                                    if _t.get("result_url"):
                                        _diy["result_url"] = _t["result_url"]
                                    break
                        except Exception:
                            logger.exception("[agent] DIY 方案效果图回填失败")
                    _diy["requirement"] = message
                    _res = save_diy_plan(_diy, user_id)
                    logger.info(
                        "[agent] DIY 方案入库 saved=%s duplicate=%s id=%s",
                        _res["saved"], _res["duplicate"], _res["plan_id"],
                    )
            except Exception:
                logger.exception("[agent] DIY 方案入库失败")
        _had_card = ui in (
            UIType.PLAN_CARD, UIType.SHOP_CARD, UIType.ORDER_CARD, UIType.PAY_JUMP
        ) or (ui == UIType.TEXT and bool(data.get("task_id")))
        _plan_pushed = mem_store.get_session_flag(user_id, sid, "plan_pushed") == "1"
        if any(w in message for w in ("再", "换", "别的", "预算", "有没有", "其他", "看看")):
            mem_store.clear_session_flags(user_id, sid, prefix="plan_")
            _plan_pushed = False
        _req_dims = sum(bool(x) for x in (
            req.recipient, req.occasion, req.budget_num is not None,
            req.style, req.scene, bool(req.colors),
        ))
        _buying = (
            llm_intent in ("buying", "design")
            or (not llm_intent and any(w in message for w in _BUY_INTENT))
        )
        if (
            not _had_card
            and not _img_intent
            and not _is_chitchat(message)
            and not _plan_pushed
            and _buying
            and _req_dims >= 2
            and new_stage not in (SessionStage.DONE, SessionStage.ORDER_CONFIRM)
            and not any(w in message for w in (
                "店铺", "下单", "购买", "支付", "付款", "确认方案", "diy", "diy 定制",
                "定制", "专属", "自己设计", "独一无二", "特别", "重新设计",
            ))
        ):
            try:
                from agent.tools import search_plans as _sp
                raw = _sp("", {"user_id": user_id, "session_id": sid, "location": location, "requirement": req})
                forced_plans = json.loads(raw)
                if isinstance(forced_plans, list) and forced_plans:
                    ui = UIType.PLAN_CARD
                    data = {"plans": forced_plans}
                    tool_log.append(ToolCallRecord(
                        name="search_plans", arguments={"keyword": ""}, result=raw, status="ok",
                    ))
                    new_msgs.append({"role": "tool", "content": raw, "tool_call_id": "forced_search_plans"})
                    new_stage = SessionStage.DIY_DESIGN
                    mem_store.set_session_flag(user_id, sid, "plan_pushed", "1")
                    if not final_reply.strip():
                        final_reply = (
                            "我为你挑了几款配送范围内符合需求的现有花束，"
                            "可以直接选，也可以让我为你 DIY 定制～"
                        )
                    logger.info("[agent] 现有方案兜底推送 %d 款", len(forced_plans))
            except Exception:
                logger.exception("[agent] 现有方案兜底推送失败")
        if llm_intent:
            _qa_intent = llm_intent == "qa"
        else:
            _qa_intent = bool(
                re.search(r"什么|怎么|为什么|多久|花期|养护|寓意|百科|介绍|季节", message)
            ) and not any(w in message for w in (
                "买", "送", "预算", "下单", "diy", "方案", "推荐", "想要", "需要", "束",
            ))
        if _qa_intent and ui == UIType.PLAN_CARD and not any(
            tc.name in (
                "generate_diy_plan", "revise_diy_plan", "generate_effect_image",
                "search_shops", "create_order",
            ) and tc.status == "ok"
            for tc in tool_log
        ):
            ui = UIType.TEXT
            data = {}
            logger.info("[agent] 知识问答轮次，丢弃 LLM 擅自推送的方案卡")
        diy_done = any(
            tc.name in ("generate_diy_plan", "revise_diy_plan") and tc.status == "ok"
            for tc in tool_log
        )
        eff_done = any(tc.name == "generate_effect_image" and tc.status == "ok" for tc in tool_log)
        if (
            diy_done and not eff_done
            and ui == UIType.PLAN_CARD
            and new_stage not in (SessionStage.DONE, SessionStage.ORDER_CONFIRM)
        ):
            try:
                from agent.tools import generate_effect_image as _gei
                mem_store.set_session_flag(user_id, sid, "image_confirmed", "1")
                raw = _gei("latest_diy", {"user_id": user_id, "session_id": sid, "location": location})
                eff = json.loads(raw)
                if "task_id" in eff:
                    data = {**data, "task_id": eff["task_id"], "poll": eff.get("poll", True)}
                    if eff.get("result_url"):
                        data["result_url"] = eff["result_url"]
                    tool_log.append(ToolCallRecord(
                        name="generate_effect_image",
                        arguments={"plan": "latest_diy"},
                        result=raw, status="ok",
                    ))
                    logger.info("[agent] 方案即生图 task_id=%s", eff["task_id"])
            except Exception:
                logger.exception("[agent] 方案即生图失败")

        eff_confirmed = mem_store.get_session_flag(user_id, sid, "image_confirmed") == "1"
        eff_done = any(tc.name == "generate_effect_image" and tc.status == "ok" for tc in tool_log)
        if (
            eff_confirmed and not eff_done
            and ui != UIType.PLAN_CARD
            and new_stage not in (SessionStage.DONE, SessionStage.ORDER_CONFIRM)
        ):
            try:
                from agent.tools import generate_effect_image as _gei
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
            except Exception:
                logger.exception("[agent] 生图补调失败")

        final_reply = _clean_reply(final_reply)
        if ui in (UIType.ORDER_CARD, UIType.PAY_JUMP):
            final_reply = re.sub(r"[，,]?共\s*\d+[\d.]*\s*元", "", final_reply)
            final_reply = re.sub(r"[，,]?\d+[\d.]*\s*元[。.?]", "", final_reply)
            final_reply = final_reply.strip() or "订单已生成，请确认信息后去支付～"
        if ui.value != UIType.TEXT and (not final_reply or final_reply == "好的，收到你的想法啦，请稍等～"):
            final_reply = ""
        elif not final_reply:
            final_reply = (
                "我已经为你整理好相关结果啦，请查看下方卡片～" if tool_log
                else "好的，收到你的想法啦，请稍等～"
            )
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