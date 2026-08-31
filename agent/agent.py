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
from collections.abc import Callable
from typing import Any

from agent.engine.llm import call_llm
from agent.engine.state import SessionStage
from agent.engine.ui_protocol import ChatResponse, ToolCallRecord, UIType
from agent.tools import execute_tool, extract_requirement, generate_tool_manual, to_openai_tools
from backend.config import settings, setup_logging
from backend.storage import memory as mem_store

# 导入增强工具（搜索、天气、节日、价格查询等）
import agent.tools_enhanced  # noqa: F401 - 触发工具注册

_CHITCHAT_WORDS = ('你好', '您好', '在吗', '在么', '嗨', '哈喽', '谢谢', '感谢', '再见', '拜拜', '哈哈', '辛苦了', '赞', '呵呵')
_BUY_INTENT = ('买', '送', '下单', '购买', '付款', '支付', '选一束', '挑一束', '想要', '需要', '来一束', '订一束')

def _clean_reply(text: str) -> str:
    """清理智能体回复里的 markdown 噪声，让前端纯文本渲染更整洁。

    前端不渲染 markdown，因此 ``**加粗**`` 会原样显示成 ``**``；这里统一去除
    ``**`` 与行首 ``#`` 标题符，并把连续空行折叠为单空行，保留有序列表等可读结构。
    """
    if not text:
        return text
    text = text.replace('**', '')
    text = re.sub('(?m)^#{1,6}\\s*', '', text)
    text = re.sub('\\n{3,}', '\n\n', text)
    return text.strip()

def _is_chitchat(text: str) -> bool:
    """判断消息是否与花卉导购无关（纯寒暄/感谢）。用于 DONE 后判断是否开启新会话。"""
    t = text.strip().lower()
    if not t:
        return True
    if any(k in t for k in ('买', '送', '花', '束', '预算', '方案', 'diy', '自己', '店铺', '下单', '订单', '确认', '选', '要', '想要', '需要', '推荐', '生图', '效果', '图')):
        return False
    return any(w in t for w in _CHITCHAT_WORDS)
logger = logging.getLogger('agent')
_AFFIRMATIVE = ('好', '可以', '确认', '同意', '生成', '要', '行', '是', '看看')
_NEGATIVE = ('不用', '不要', '不需要', '不必', '算了', '跳过', '无需', '别', '放弃')

def is_affirmative(text: str) -> bool:
    """判断用户消息是否为明确肯定意图（用于生图确认等关卡）。"""
    t = (text or '').strip()
    if not t:
        return False
    if any(k in t for k in _NEGATIVE):
        return False
    return any(k in t for k in _AFFIRMATIVE)
_ROLE_ACTIONS: dict[str, set[str]] = {'user': {'chat', 'reset', 'tasks'}, 'merchant': set(), 'admin': set()}

def is_allowed(role: str, action: str) -> bool:
    """权限钩子：判断某角色是否可执行某动作。本期仅 user 放行。"""
    return action in _ROLE_ACTIONS.get(role, set())

class ReActAgent:
    """基于 ReAct + 状态机的导购智能体。"""

    async def arun(self, user_id: str, message: str, session_id: str | None=None, user_role: str='user', location: dict[str, float] | None=None) -> ChatResponse:
        """异步入口：做权限校验后，直接运行异步主循环。"""
        if not is_allowed(user_role, 'chat'):
            raise PermissionError(f'角色 {user_role} 无权执行 chat 动作')
        return await self.run(user_id, message, session_id, user_role, location)

    async def arun_stream(self, user_id: str, message: str, session_id: str | None=None, user_role: str='user', location: dict[str, float] | None=None):
        """流式异步入口：yield SSE 事件字典，供 /chat/stream 消费。

        事件类型：
        - {"event": "tool_call", "name": "...", "status": "ok/error"}
        - {"event": "text", "content": "..."}  — 逐句输出最终回复
        - {"event": "card", "ui": "...", "data": {...}}  — 结构化卡片
        - {"event": "done", "session_id": "..."}
        - {"event": "error", "message": "..."}
        """
        if not is_allowed(user_role, 'chat'):
            yield {'event': 'error', 'message': f'角色 {user_role} 无权执行 chat'}
            return
        try:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[dict | None] = asyncio.Queue()

            def _on_event(evt: dict) -> None:
                """run() 线程中调用，线程安全地把事件推入 async Queue。"""
                loop.call_soon_threadsafe(queue.put_nowait, evt)

            async def _run():
                result = await self.run(user_id, message, session_id, user_role, location, on_event=_on_event)
                await queue.put({'event': 'done', 'session_id': result.session_id})
                await queue.put(None)
            task = loop.create_task(_run())
            try:
                while True:
                    evt = await queue.get()
                    if evt is None:
                        break
                    yield evt
            except asyncio.CancelledError:
                task.cancel()
                raise
            finally:
                if not task.done():
                    task.cancel()
        except Exception as exc:
            logger.exception('[agent] arun_stream 异常')
            yield {'event': 'error', 'message': f'智能体执行失败: {type(exc).__name__}'}

    async def run(self, user_id: str, message: str, session_id: str | None, user_role: str, location: dict[str, float] | None, on_event: Callable[[dict], None] | None=None) -> ChatResponse:
        t0 = time.perf_counter()
        sid = await mem_store.get_or_create_session(user_id, session_id)
        stage = SessionStage(await mem_store.get_stage(sid))
        if stage == SessionStage.DONE and (not _is_chitchat(message)):
            sid = await mem_store.create_conversation(user_id, title=message[:20])
            stage = SessionStage.ANALYZE
        existing_req = await mem_store.get_requirement(sid)
        turn_req = extract_requirement(message)
        req = existing_req.merge(turn_req) if existing_req else turn_req
        if location and (not req.location):
            req.location = location
        await mem_store.set_requirement(sid, req)
        stage = SessionStage(await mem_store.get_stage(sid))
        incoming = stage
        if stage == SessionStage.IMAGE_GEN and is_affirmative(message):
            await mem_store.set_session_flag(user_id, sid, 'image_confirmed', '1')
        long_term = await mem_store.get_long_term(user_id)
        history = await mem_store.load_history(sid, settings.history_limit)
        system = self._build_system(stage, long_term)
        messages: list[dict[str, Any]] = [{'role': 'system', 'content': system}]
        messages += history
        messages.append({'role': 'user', 'content': message})
        tool_log: list[ToolCallRecord] = []
        respond_args: dict[str, Any] | None = None
        final_reply = ''
        new_msgs: list[dict[str, Any]] = [{'role': 'user', 'content': message}]
        for turn in range(1, settings.max_iterations + 1):
            logger.info('[agent] ReAct 第 %d/%d 轮 阶段=%s', turn, settings.max_iterations, stage.value)
            try:
                resp = call_llm(messages, tools=to_openai_tools())
            except Exception as exc:
                logger.exception('[agent] LLM 调用失败')
                final_reply = f'抱歉，模型调用出错：{exc}'
                break
            msg = resp.choices[0].message
            tool_calls = self._parse_tool_calls(msg)
            if tool_calls:
                assistant_msg = {'role': 'assistant', 'content': getattr(msg, 'content', '') or '', 'tool_calls': [{'id': tc['id'], 'type': 'function', 'function': {'name': tc['name'], 'arguments': json.dumps(tc['arguments'], ensure_ascii=False)}} for tc in tool_calls]}
                messages.append(assistant_msg)
                new_msgs.append({**assistant_msg, 'content': ''})
                for tc in tool_calls:
                    if tc['name'] == 'respond_to_user':
                        respond_args = tc['arguments']
                        obs = json.dumps(respond_args, ensure_ascii=False)
                        messages.append({'role': 'tool', 'content': obs, 'tool_call_id': tc.get('id', '')})
                        new_msgs.append({'role': 'tool', 'content': obs, 'tool_call_id': tc.get('id', '')})
                        continue
                    result, status = await execute_tool(tc['name'], tc['arguments'], {'user_id': user_id, 'session_id': sid, 'location': location, 'requirement': req})
                    record = ToolCallRecord(name=tc['name'], arguments=tc['arguments'], result=result, status=status)
                    tool_log.append(record)
                    if on_event:
                        on_event({'event': 'tool_call', 'name': tc['name'], 'status': status})
                    messages.append({'role': 'tool', 'content': result, 'tool_call_id': tc.get('id', '')})
                    new_msgs.append({'role': 'tool', 'content': result, 'tool_call_id': tc.get('id', '')})
                if respond_args is not None:
                    break
                continue
            else:
                final_reply = getattr(msg, 'content', '') or ''
                messages.append({'role': 'assistant', 'content': final_reply})
                break
        else:
            if any(tc.status == 'ok' for tc in tool_log):
                final_reply = final_reply or '我已经为你整理好相关结果啦，请查看下方卡片～'
            else:
                final_reply = final_reply or '抱歉，我思考得太久啦，请简化需求或分步骤再问我～'
        if respond_args is not None:
            new_stage = self._derive_focus(tool_log, incoming, message)
            if new_stage == SessionStage.DONE:
                ordered = [tc.name for tc in tool_log if tc.status == 'ok']
                if 'create_order' not in ordered:
                    new_stage = SessionStage.SHOP_RECOMMEND if 'search_shops' in ordered else incoming
            ui_arg = str(respond_args.get('ui', ''))
            try:
                ui = UIType(ui_arg)
            except ValueError:
                ui = UIType.TEXT
            data_arg = respond_args.get('data') or {}
            data = data_arg if isinstance(data_arg, dict) else {}
            if self._validate_respond_data(ui, data) is None:
                data = {}
            inferred_ui, inferred_data = self._derive_ui(tool_log, new_stage, final_reply)
            _card_types = {UIType.DIALOG_OPTIONS, UIType.PLAN_CARD, UIType.SHOP_CARD, UIType.ORDER_CARD, UIType.PAY_JUMP}
            _data_effective = bool(data) and (not (ui == UIType.IMAGE_TASK and (not (data.get('task_id') or data.get('result_url')))))
            if not _data_effective:
                if inferred_ui in _card_types and inferred_data:
                    ui = inferred_ui
                    data = inferred_data
            elif ui == UIType.PLAN_CARD and inferred_ui == UIType.PLAN_CARD and inferred_data:
                ui = inferred_ui
                data = inferred_data
            if inferred_ui in (UIType.ORDER_CARD, UIType.PAY_JUMP) and inferred_data.get('pay_jump'):
                ui = UIType.PAY_JUMP
                data = inferred_data
            if inferred_data.get('task_id'):
                if inferred_data.get('result_url'):
                    ui = UIType.IMAGE_TASK
                    data = {'task_id': inferred_data['task_id'], 'poll': inferred_data.get('poll'), 'result_url': inferred_data['result_url']}
                else:
                    ui = UIType.TEXT
                    data = {'task_id': inferred_data['task_id'], 'poll': inferred_data.get('poll')}
            final_reply = str(respond_args.get('reply', final_reply) or final_reply)
            if not final_reply.strip():
                if tool_log:
                    final_reply = '我已经为你整理好相关结果啦，请查看下方卡片～'
                else:
                    final_reply = '好的，收到你的想法啦，请稍等～'
            if ui == UIType.DIALOG_OPTIONS and isinstance(data.get('options'), list):
                data['options'] = [o if isinstance(o, dict) and o.get('label') else {'label': str(o), 'value': str(o)} for o in data['options']]
            if ui == UIType.IMAGE_TASK:
                if inferred_data.get('task_id'):
                    data = {'task_id': inferred_data['task_id'], 'poll': inferred_data.get('poll')}
                    if inferred_data.get('result_url'):
                        data['result_url'] = inferred_data['result_url']
                else:
                    ui = UIType.TEXT
                    data = {}
            if ui == UIType.SHOP_CARD:
                if inferred_ui == UIType.SHOP_CARD and inferred_data.get('shops'):
                    ui = inferred_ui
                    data = inferred_data
                else:
                    ui = UIType.TEXT
                    data = {}
        else:
            new_stage = self._derive_focus(tool_log, incoming, message)
            if new_stage == SessionStage.DONE:
                ordered = [tc.name for tc in tool_log if tc.status == 'ok']
                if 'create_order' not in ordered:
                    new_stage = SessionStage.SHOP_RECOMMEND if 'search_shops' in ordered else incoming
            ui, data = self._derive_ui(tool_log, new_stage, final_reply)
        llm_intent = ''
        if respond_args is not None:
            llm_intent = str(respond_args.get('intent', '') or '')
        _img_intent = any(w in message for w in ('效果图', '生图', '生成'))
        if new_stage == SessionStage.IMAGE_GEN and new_stage != incoming:
            await mem_store.clear_session_flags(user_id, sid, prefix='image_')
            await mem_store.set_session_flag(user_id, sid, 'image_confirmed', '1')
        elif _img_intent and incoming in (SessionStage.DIY_DESIGN, SessionStage.IMAGE_GEN) and (await mem_store.get_session_flag(user_id, sid, 'image_confirmed') != '1'):
            await mem_store.set_session_flag(user_id, sid, 'image_confirmed', '1')
        if any(w in message for w in ('确认方案', '确认这个方案', '就这个', '定这个', '就它', '这个方案', '方案可以')) or (is_affirmative(message) and '方案' in message):
            try:
                from backend.storage.diy import save_diy_plan
                _diy = await mem_store.get_session_json(user_id, sid, 'latest_diy_plan')
                if _diy and _diy.get('diy'):
                    if not (_diy.get('result_url') or _diy.get('effect_image_url')):
                        try:
                            from backend.storage.tasks import get_image_task
                            for _m in reversed(await mem_store.load_display_messages(sid)):
                                _d = _m.get('data') if isinstance(_m.get('data'), dict) else {}
                                if _d.get('task_id'):
                                    _t = await get_image_task(str(_d['task_id']))
                                    if _t.get('result_url'):
                                        _diy['result_url'] = _t['result_url']
                                    break
                        except Exception:
                            logger.exception('[agent] DIY 方案效果图回填失败')
                    _diy['requirement'] = message
                    _res = await save_diy_plan(_diy, user_id)
                    logger.info('[agent] DIY 方案入库 saved=%s duplicate=%s id=%s', _res['saved'], _res['duplicate'], _res['plan_id'])
            except Exception:
                logger.exception('[agent] DIY 方案入库失败')
        _had_card = ui in (UIType.PLAN_CARD, UIType.SHOP_CARD, UIType.ORDER_CARD, UIType.PAY_JUMP) or (ui == UIType.TEXT and bool(data.get('task_id')))
        _plan_pushed = await mem_store.get_session_flag(user_id, sid, 'plan_pushed') == '1'
        if any(w in message for w in ('再', '换', '别的', '预算', '有没有', '其他', '看看')):
            await mem_store.clear_session_flags(user_id, sid, prefix='plan_')
            _plan_pushed = False
        _req_dims = sum(bool(x) for x in (req.recipient, req.occasion, req.budget_num is not None, req.style, req.scene, bool(req.colors)))
        _buying = llm_intent in ('buying', 'design') or (not llm_intent and any(w in message for w in _BUY_INTENT))
        if not _had_card and (not _img_intent) and (not _is_chitchat(message)) and (not _plan_pushed) and _buying and (_req_dims >= 2) and (new_stage not in (SessionStage.DONE, SessionStage.ORDER_CONFIRM)) and (not any(w in message for w in ('店铺', '下单', '购买', '支付', '付款', '确认方案', 'diy', 'diy 定制', '定制', '专属', '自己设计', '独一无二', '特别', '重新设计'))):
            try:
                from agent.tools import search_plans as _sp
                raw = await _sp('', {'user_id': user_id, 'session_id': sid, 'location': location, 'requirement': req})
                forced_plans = json.loads(raw)
                if isinstance(forced_plans, list) and forced_plans:
                    ui = UIType.PLAN_CARD
                    data = {'plans': forced_plans}
                    tool_log.append(ToolCallRecord(name='search_plans', arguments={'keyword': ''}, result=raw, status='ok'))
                    new_msgs.append({'role': 'tool', 'content': raw, 'tool_call_id': 'forced_search_plans'})
                    new_stage = SessionStage.DIY_DESIGN
                    await mem_store.set_session_flag(user_id, sid, 'plan_pushed', '1')
                    if not final_reply.strip():
                        final_reply = '我为你挑了几款配送范围内符合需求的现有花束，可以直接选，也可以让我为你 DIY 定制～'
                    logger.info('[agent] 现有方案兜底推送 %d 款', len(forced_plans))
            except Exception:
                logger.exception('[agent] 现有方案兜底推送失败')
        if llm_intent:
            _qa_intent = llm_intent == 'qa'
        else:
            _qa_intent = bool(re.search('什么|怎么|为什么|多久|花期|养护|寓意|百科|介绍|季节', message)) and (not any(w in message for w in ('买', '送', '预算', '下单', 'diy', '方案', '推荐', '想要', '需要', '束')))
        if _qa_intent and ui == UIType.PLAN_CARD and (not any(tc.name in ('generate_diy_plan', 'revise_diy_plan', 'generate_effect_image', 'search_shops', 'create_order') and tc.status == 'ok' for tc in tool_log)):
            ui = UIType.TEXT
            data = {}
            logger.info('[agent] 知识问答轮次，丢弃 LLM 擅自推送的方案卡')
        diy_done = any(tc.name in ('generate_diy_plan', 'revise_diy_plan') and tc.status == 'ok' for tc in tool_log)
        eff_done = any(tc.name == 'generate_effect_image' and tc.status == 'ok' for tc in tool_log)
        if diy_done and (not eff_done) and (ui == UIType.PLAN_CARD) and (new_stage not in (SessionStage.DONE, SessionStage.ORDER_CONFIRM)):
            try:
                from agent.tools import generate_effect_image as _gei
                await mem_store.set_session_flag(user_id, sid, 'image_confirmed', '1')
                raw = await _gei('latest_diy', {'user_id': user_id, 'session_id': sid, 'location': location})
                eff = json.loads(raw)
                if 'task_id' in eff:
                    data = {**data, 'task_id': eff['task_id'], 'poll': eff.get('poll', True)}
                    if eff.get('result_url'):
                        data['result_url'] = eff['result_url']
                    tool_log.append(ToolCallRecord(name='generate_effect_image', arguments={'plan': 'latest_diy'}, result=raw, status='ok'))
                    logger.info('[agent] 方案即生图 task_id=%s', eff['task_id'])
            except Exception:
                logger.exception('[agent] 方案即生图失败')
        eff_confirmed = await mem_store.get_session_flag(user_id, sid, 'image_confirmed') == '1'
        eff_done = any(tc.name == 'generate_effect_image' and tc.status == 'ok' for tc in tool_log)
        if eff_confirmed and (not eff_done) and (ui != UIType.PLAN_CARD) and (new_stage not in (SessionStage.DONE, SessionStage.ORDER_CONFIRM)):
            try:
                from agent.tools import generate_effect_image as _gei
                await mem_store.update_stage(sid, SessionStage.IMAGE_GEN.value)
                raw = await _gei('latest_diy', {'user_id': user_id, 'session_id': sid, 'location': location})
                eff = json.loads(raw)
                if 'task_id' in eff:
                    ui = UIType.TEXT
                    data = {'task_id': eff['task_id'], 'poll': eff.get('poll', True)}
                    final_reply = '正在为您生成效果图预览，请稍候～ 🎨'
                    tool_log.append(ToolCallRecord(name='generate_effect_image', arguments={'plan': 'latest_diy'}, result=raw, status='ok'))
                    new_msgs.append({'role': 'tool', 'content': raw, 'tool_call_id': 'forced_effect_image'})
                    logger.info('[agent] 生图补调成功 task_id=%s', eff['task_id'])
            except Exception:
                logger.exception('[agent] 生图补调失败')
        final_reply = _clean_reply(final_reply)
        if ui in (UIType.ORDER_CARD, UIType.PAY_JUMP):
            final_reply = re.sub('[，,]?共\\s*\\d+[\\d.]*\\s*元', '', final_reply)
            final_reply = re.sub('[，,]?\\d+[\\d.]*\\s*元[。.?]', '', final_reply)
            final_reply = final_reply.strip() or '订单已生成，请确认信息后去支付～'
        if ui.value != UIType.TEXT and (not final_reply or final_reply == '好的，收到你的想法啦，请稍等～'):
            final_reply = ''
        elif not final_reply:
            final_reply = '我已经为你整理好相关结果啦，请查看下方卡片～' if tool_log else '好的，收到你的想法啦，请稍等～'
        new_msgs.append({'role': 'assistant', 'content': final_reply, 'ui': ui.value, 'data': data})
        await mem_store.save_messages(sid, new_msgs)
        await mem_store.update_stage(sid, new_stage.value)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info('[agent] 完成 阶段=%s ui=%s 耗时=%.0fms', new_stage.value, ui.value, elapsed)
        if on_event:
            import re as _re
            parts = _re.split('([。！？\\n])', final_reply or '')
            buf = ''
            for seg in parts:
                buf += seg
                if seg in ('。', '！', '？', '\n') or len(buf) > 20:
                    on_event({'event': 'text', 'content': buf})
                    buf = ''
                    await asyncio.sleep(0.03)
            if buf:
                on_event({'event': 'text', 'content': buf})
            if ui and ui.value != 'text':
                on_event({'event': 'card', 'ui': ui.value, 'data': data})
        return ChatResponse(user_id=user_id, reply=final_reply, ui=ui, data=data, tool_calls=tool_log, session_id=sid, stage=new_stage.value)

    def _build_system(self, stage: SessionStage, long_term: dict[str, str]) -> str:
        """构造 system prompt：身份 + 能力边界 + 工具规则 + 专业技能 + 记忆 + 格式要求。

        参考 OpenCode 的分层结构：角色 → 能力 → 工具规则 → 专业技能 → 输出格式。
        """
        parts = [
            # ---- 角色定义 ----
            '你是「花语小筑」的首席花艺顾问，拥有 10 年花艺设计经验。你亲切、专业、懂花，'
            '能根据用户需求设计花艺方案、推荐店铺并引导下单。用简洁中文回复，语气像专业花艺师在简短讲解。',
            
            # ---- 能力边界 ----
            '## 你的能力',
            '- 花卉知识：花期、花语、养护方法、搭配原则、送礼禁忌',
            '- 方案设计：根据需求设计花艺方案（花材/配比/色彩/寓意/包装/预算）',
            '- 店铺推荐：匹配配送范围内的花店',
            '- 下单支付：引导用户完成购买',
            '- 效果图生成：为设计方案自动生成效果图',
            '- 天气查询：获取天气信息，推荐适合的花卉',
            '- 节日查询：查询近期节日，推荐送礼场景',
            '- 价格查询：查询花卉价格，用于预算推荐',
            
            # ---- 工具使用规则 ----
            '## 工具使用规则',
            '1. 用户问花卉知识（花期、花语、养护、搭配建议）→ 不调工具，直接回答',
            '2. 用户要买花（有购买词+送礼对象）→ 先 search_plans，再 search_shops',
            '3. 用户要定制（DIY意图）→ 先 search_diy_plans 检索模板，再 generate_diy_plan',
            '4. 用户问天气/季节 → 调 get_weather，推荐适合的花材',
            '5. 用户问近期节日 → 调 get_nearby_holidays，推荐送礼场景',
            '6. 用户问价格/预算 → 调 get_flower_prices，给出预算建议',
            '7. 无需调工具时 → 调 respond_to_user 直接回复',
            
            # ---- 专业技能（花材搭配）----
            '## 花材搭配专业技能',
            '### 色彩搭配',
            '- 同色系：粉+白+浅紫（温柔）、白+绿（清新）',
            '- 对比色：红+绿（经典）、黄+紫（高贵）、橙+蓝（热情）',
            '- 避免：超过3种主色，颜色过于杂乱',
            '',
            '### 花语搭配',
            '- 爱情：红玫瑰+满天星+勿忘我',
            '- 友谊：向日葵+雏菊+黄莺',
            '- 祝福：百合+康乃馨+洋桔梗',
            '- 感恩：康乃馨+满天星',
            '',
            '### 场景搭配',
            '- 婚礼：白玫瑰+满天星+尤加利叶（圣洁浪漫）',
            '- 生日：向日葵+玫瑰+绣球（阳光活力）',
            '- 探病：百合+康乃馨+绿萝（祝福康复）',
            '- 母亲节：康乃馨+满天星（经典母爱）',
            '',
            '### 预算搭配',
            '- 100元以内：3-5枝主花+配草+简约包装',
            '- 100-300元：7-11枝主花+配花+精美包装',
            '- 300元以上：11枝以上+配花+包装+贺卡',
            
            # ---- 主流程 ----
            '## 主流程（按需走，不强推，用户可随时打断）',
            '1. 用户问花卉知识 → 直接回答，不调工具，不推方案',
            '2. 用户表达购买意图 → 先回答需求，再调 search_plans 推荐',
            '3. 用户要定制 → 先 search_diy_plans 检索模板，再 generate_diy_plan',
            '4. 方案设计完成 → 展示方案卡，等用户确认后再推店铺',
            '5. 用户选定店铺 → 调 create_order 下单',
            
            # ---- 原则 ----
            '## 原则',
            '1. 用户随时可打断、改需求、回退；不要强推固定流程',
            '2. 咨询 ≠ 要买：用户问知识时只回答问题，不推方案',
            '3. 方案设计完成后效果图自动生成，不要询问用户',
            '4. 下单前必须已推荐店铺且用户已选定',
            '5. 不要使用 markdown 加粗符号，不要用 # 标题符',
        ]
        
        if long_term:
            mem = '；'.join((f'{k}={v}' for k, v in long_term.items()))
            parts.append('## 用户长期偏好（来自记忆，回复时参考）：' + mem)
        
        parts.append(
            '## 回复格式要求\n'
            '- 回复要简短：方案、店铺、订单等结构化内容会以卡片形式展示给用户，文字里只给结论 + 一句行动建议\n'
            '- 设计完方案后：简短说「方案已设计好，点击卡片可查看详情」，然后问「方案满意吗？」\n'
            '- 不要重复罗列卡片已有的细节（花材明细、寓意、包装、养护、价格清单等）\n'
            '- 术语准确、语气亲切，像一位专业花艺师在简短讲解\n'
            '- 每次调用 respond_to_user 时务必填对 intent：\n'
            '  - buying=要买/挑选\n'
            '  - qa=问知识/咨询\n'
            '  - chitchat=闲聊\n'
            '  - design=要DIY定制\n'
            '  - other=其他'
        )
        
        parts.append('## 工具说明书\n' + generate_tool_manual())
        return '\n\n'.join(parts)

    @staticmethod
    def _parse_tool_calls(msg: Any) -> list[dict[str, Any]]:
        """兼容 OpenAI（msg.tool_calls[i].function）与 Mock（_MockToolCall）。"""
        raw = getattr(msg, 'tool_calls', None)
        if not raw:
            return []
        calls: list[dict[str, Any]] = []
        for tc in raw:
            name = tc.function.name
            args = json.loads(tc.function.arguments or '{}')
            tid = getattr(tc, 'id', '')
            calls.append({'id': tid, 'name': name, 'arguments': args})
        return calls

    @staticmethod
    def _derive_focus(tool_log: list[ToolCallRecord], incoming: SessionStage, message: str) -> SessionStage:
        """基于本轮工具产出推导 UI 焦点（focus），不再做状态机拦截。

        skill 编排模式下，focus 仅用于前端高亮「用户当前在做什么」，不限制流程：
        - 有订单 → done；有店铺 → shop_recommend；有生图 → image_gen；
        - 有方案（generate_diy_plan / search_plans）→ diy_design；
        - 否则保持进入时的焦点（incoming），避免无工具轮次焦点乱跳。
        """
        ordered = [tc.name for tc in tool_log if tc.status == 'ok']
        if 'create_order' in ordered:
            return SessionStage.DONE
        if 'search_shops' in ordered:
            return SessionStage.SHOP_RECOMMEND
        if 'generate_effect_image' in ordered:
            return SessionStage.IMAGE_GEN
        if 'generate_diy_plan' in ordered or 'search_plans' in ordered:
            return SessionStage.DIY_DESIGN
        return incoming

    @staticmethod
    def _validate_respond_data(ui: UIType, data: dict) -> dict | None:
        """按 ui 契约校验 respond_to_user 携带的 data 形状；无效返回 None。

        卡片类 ui 必须有核心字段，否则视为 LLM 幻觉（如 plan_card 无 plans、
        pay_jump 无 order_id、dialog_options 无 options），调用方据此把 data 置空，
        交给 _derive_ui 依据真实工具成果重建卡片。
        """
        if ui == UIType.TEXT:
            return data
        if ui == UIType.DIALOG_OPTIONS:
            return data if isinstance(data.get('options'), list) and data['options'] else None
        if ui == UIType.PLAN_CARD:
            return data if isinstance(data.get('plans'), list) and data['plans'] else None
        if ui == UIType.SHOP_CARD:
            return data if isinstance(data.get('shops'), list) and data['shops'] else None
        if ui in (UIType.ORDER_CARD, UIType.PAY_JUMP):
            return data if data.get('order_id') or data.get('page_path') else None
        if ui == UIType.IMAGE_TASK:
            return data if data.get('task_id') or data.get('result_url') else None
        return data

    def _derive_ui(self, tool_log: list[ToolCallRecord], stage: SessionStage, reply: str) -> tuple[UIType, dict[str, Any]]:
        """根据本轮工具产出决定 ui 类型与 data。

        注意：不能只看「最后一个成功工具」——live LLM 常在设计/生图之后追加
        save_memory / retrieve_knowledge 落库偏好，若只取 last 会漏掉方案卡/生图卡/
        店铺卡（已复现：generate_diy_plan > save_memory 时 ui 退化为 text）。
        这里从最近一次成功工具回溯，跳过不产出卡片的辅助工具，命中即返回。
        """
        renderers: dict[str, Callable[[dict[str, Any]], tuple[UIType, dict[str, Any]]]] = {'search_plans': lambda r: (UIType.PLAN_CARD, {'plans': r}), 'get_plan_detail': lambda r: (UIType.PLAN_CARD, {'plans': [r] if isinstance(r, dict) else r}), 'generate_diy_plan': lambda r: (UIType.PLAN_CARD, {'plans': [r]}), 'revise_diy_plan': lambda r: (UIType.PLAN_CARD, {'plans': [r]}), 'search_shops': lambda r: (UIType.SHOP_CARD, {'shops': r}), 'generate_effect_image': lambda r: (UIType.IMAGE_TASK, {'task_id': r.get('task_id'), 'poll': r.get('poll'), **({'result_url': r['result_url']} if r.get('result_url') else {})}), 'create_order': lambda r: (UIType.ORDER_CARD, r)}
        for tc in reversed(tool_log):
            if tc.status != 'ok':
                continue
            render = renderers.get(tc.name)
            if not render:
                continue
            try:
                result = json.loads(tc.result) if isinstance(tc.result, str) else tc.result or {}
            except (json.JSONDecodeError, TypeError):
                result = {}
            if isinstance(result, list) and (not result):
                continue
            return render(result)
        if stage == SessionStage.SELECT_MODE:
            return (UIType.DIALOG_OPTIONS, {'options': [{'label': '商家现有方案', 'value': 'existing'}, {'label': '自己 DIY 设计', 'value': 'diy'}]})
        return (UIType.TEXT, {})
if __name__ == '__main__':
    setup_logging()
    from backend.storage.db import init_db
    init_db()
    agent = ReActAgent()
    user_msg = '想给母亲买一束花，预算 200 元左右'
    result = agent.run('cli_user', user_msg)
    print(result.model_dump_json(indent=2))
