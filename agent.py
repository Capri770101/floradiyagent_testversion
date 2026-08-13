"""智能体主类：ReAct 主循环（思考-行动-观察）驱动状态机。

单次 /chat 请求内完成：
  system + 历史 + 用户消息 -> LLM -> 解析工具调用 -> 执行工具 -> 结果回填 -> 循环
直到模型调用 respond_to_user（最终回复）或达到 max_iterations 上限。
"""
import json
import logging
from typing import List, Optional

from config import Config
from engine.llm import LLMClient, LLMError, LLMResult
from engine.state import SessionStage, allowed_targets, can_transition, from_str
from engine.ui_protocol import (
    ALL_UI, ChatResponse, ToolCallRecord, UI_PLAN_CARD, UI_TEXT,
)
from runtime import Runtime, get_runtime
from storage.memory import Memory
from storage.repository import BaseRepository
from tools import execute_tool, tool_body_text, tool_descriptions

logger = logging.getLogger(__name__)

# 生图确认关卡的意图识别（后端判定，不依赖模型自觉）：
# 进入 IMAGE_GEN 阶段后，只有用户明确肯定才写入 image_confirmed 标记，
# generate_effect_image 工具据此放行。否定词优先于肯定词。
_AFFIRMATIVE = ("好", "可以", "确认", "同意", "生成", "要", "行", "是", "看看")
_NEGATIVE = ("不用", "不要", "不需要", "不必", "算了", "跳过", "无需", "别", "放弃")


def is_affirmative(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(k in t for k in _NEGATIVE):
        return False
    return any(k in t for k in _AFFIRMATIVE)

# 终结工具：模型必须以调用它来结束本轮，携带结构化回复（reply/ui/data/stage）
RESPOND_TOOL = {
    "type": "function",
    "function": {
        "name": "respond_to_user",
        "description": "当你准备好向用户输出本轮最终回复时，必须调用该工具结束本轮对话。"
                       "携带：reply（自然语言回复）、ui（UI 动作类型）、data（按 ui 类型填充）、"
                       "stage（协商后的下一业务阶段，必须取自允许列表）。",
        "parameters": {
            "type": "object",
            "properties": {
                "reply": {"type": "string", "description": "给用户的自然语言回复"},
                "ui": {"type": "string", "enum": ALL_UI, "description": "小程序渲染的 UI 动作类型"},
                "data": {"type": "object", "description": "按 ui 类型约定的结构化数据"},
                "stage": {"type": "string", "description": "下一业务阶段"},
            },
            "required": ["reply", "ui", "data", "stage"],
        },
    },
}


class Agent:
    def __init__(self, config: Config, llm: LLMClient, memory: Memory,
                 repository: BaseRepository) -> None:
        self.config = config
        self.llm = llm
        self.memory = memory
        self.repository = repository

    # ------------------------------------------------------------------
    def chat(self, user_id: str, message: str, session_id: Optional[str] = None,
             user_role: str = "user", location: str = "") -> ChatResponse:
        """处理一条用户消息，返回结构化 UI 响应。"""
        rt = get_runtime()
        rt.user_id.set(user_id)
        rt.user_role.set(user_role)
        rt.location.set(location)

        # ---- 会话载入：指定 session_id 或取最近会话，否则新建 ----
        session = None
        if session_id:
            session = self.memory.load_session(user_id, session_id)
            if session is None:
                return ChatResponse(
                    user_id=user_id, session_id=session_id,
                    reply="会话不存在或已过期，请重新开始。", ui=UI_TEXT,
                )
        if session is None:
            session = self.memory.latest_session(user_id) or self.memory.new_session(user_id)
        rt.session_id.set(session["session_id"])

        current_stage = from_str(session["stage"])
        # DONE 表示上一单已引导至支付：新一轮对话自动从需求分析开始
        if current_stage == SessionStage.DONE:
            current_stage = SessionStage.ANALYZE

        # 生图确认关卡：用户明确肯定 -> 写入确认标记（工具守卫据此放行）
        if current_stage == SessionStage.IMAGE_GEN and is_affirmative(message):
            self.memory.set_session_flag(user_id, session["session_id"], "image_confirmed", "1")

        # ---- 组装 LLM 输入：系统提示词 + 历史 + 用户消息 ----
        self.memory.append_message(user_id, "user", json.dumps(
            {"role": "user", "content": message}, ensure_ascii=False))
        history = self.memory.get_history(user_id, self.config.history_limit)
        history = history[:-1]  # 去掉刚写入的当前消息，由下方显式追加
        msgs: List[dict] = [
            {"role": "system", "content": self._build_system_prompt(
                user_role, current_stage, user_id)},
        ]
        msgs.extend(history)
        msgs.append({"role": "user", "content": message})

        tools = tool_descriptions() + [RESPOND_TOOL]
        records: List[ToolCallRecord] = []

        # ---- ReAct 主循环 ----
        for iteration in range(self.config.max_iterations):
            try:
                result: LLMResult = self.llm.chat(msgs, tools)
            except LLMError as exc:
                logger.error("LLM 错误（第 %d 轮）: %s", iteration + 1, exc)
                return self._finalize(current_stage, session["session_id"], user_id,
                                      "服务暂时不可用，请稍后再试。", UI_TEXT, {},
                                      current_stage.value, records)

            if result.tool_calls:
                # ---- 行动：同一轮可能返回多个工具调用，须打包进「同一条」assistant 消息，
                #      再按序追加对应的 tool 观察消息（OpenAI 协议要求）。----
                batched_calls: List[dict] = []
                tool_messages: List[dict] = []
                respond_args: Optional[dict] = None
                for tc in result.tool_calls:
                    try:
                        name = tc["function"]["name"]
                        arguments = json.loads(tc["function"]["arguments"] or "{}")
                        if not isinstance(arguments, dict):
                            raise ValueError("工具参数不是 JSON 对象")
                    except (KeyError, json.JSONDecodeError, ValueError) as exc:
                        # 解析失败：仍生成 assistant/tool 占位消息把错误喂回给模型，便于其自我纠正
                        logger.warning("工具调用格式异常: %s", exc)
                        name = tc.get("function", {}).get("name", "<unknown>")
                        tool_id = tc.get("id") or f"call_{name}_{iteration}"
                        records.append(ToolCallRecord(name=name, result=f"参数解析失败: {exc}",
                                                      status="error"))
                        batched_calls.append({
                            "id": tool_id, "type": "function",
                            "function": {"name": name, "arguments": "{}"},
                        })
                        tool_messages.append({
                            "role": "tool", "tool_call_id": tool_id,
                            "content": json.dumps({"error": f"参数解析失败: {exc}"},
                                                  ensure_ascii=False),
                        })
                        continue

                    tool_id = tc.get("id") or f"call_{name}_{iteration}"
                    batched_calls.append({
                        "id": tool_id, "type": "function",
                        "function": {"name": name,
                                     "arguments": json.dumps(arguments, ensure_ascii=False)},
                    })

                    # respond_to_user：终结信号，等本批其余工具执行完再统一收尾
                    if name == "respond_to_user":
                        respond_args = arguments
                        continue

                    # ---- 观察：执行真实工具并回填 ----
                    output = execute_tool(name, arguments)
                    records.append(ToolCallRecord(name=name, arguments=arguments,
                                                  result=output[:2000], status="ok"))
                    logger.info("工具调用 %s(%s) -> %s", name, arguments, output[:120])
                    tool_messages.append({
                        "role": "tool", "tool_call_id": tool_id,
                        "content": output,
                    })

                if batched_calls:
                    msgs.append({"role": "assistant", "content": None,
                                 "tool_calls": batched_calls})
                    msgs.extend(tool_messages)

                if respond_args:
                    return self._finalize(current_stage, session["session_id"], user_id,
                                          str(respond_args.get("reply", "")),
                                          respond_args.get("ui", UI_TEXT),
                                          respond_args.get("data", {}),
                                          respond_args.get("stage", current_stage.value),
                                          records)
                if not batched_calls:
                    # 全部工具调用解析失败：给用户一个可理解的兜底回复
                    return self._finalize(current_stage, session["session_id"], user_id,
                                          "抱歉，我暂时没能正确处理您的请求，请换个说法再试一次。",
                                          UI_TEXT, {}, current_stage.value, records)
                continue

            # ---- 无工具调用：视为闲聊兜底，以文本结束 ----
            if result.content:
                return self._finalize(current_stage, session["session_id"], user_id,
                                      result.content, UI_TEXT, {}, current_stage.value, records)

            logger.warning("LLM 空响应（第 %d 轮）", iteration + 1)

        # ---- 达到迭代上限：安全收尾 ----
        logger.warning("达到最大迭代次数 %d，提前结束", self.config.max_iterations)
        return self._finalize(current_stage, session["session_id"], user_id,
                              "本轮处理步骤较多，请再发送一次您的需求，我会继续为您服务。",
                              UI_TEXT, {}, current_stage.value, records)

    # ------------------------------------------------------------------
    def _finalize(self, current_stage: SessionStage, session_id: str, user_id: str,
                  reply: str, ui: str, data: dict, stage: str,
                  records: List[ToolCallRecord]) -> ChatResponse:
        """统一收尾：校验状态流转 -> 持久化 -> 生成响应。"""
        try:
            target = from_str(stage) if stage else current_stage
        except ValueError:
            # 模型输出了未知阶段名：不崩溃，钳制回当前阶段
            logger.warning("未知阶段名 %r，钳制回 %s", stage, current_stage.value)
            target = current_stage
        if not isinstance(data, dict):
            data = {}
        if not can_transition(current_stage, target):
            logger.warning("非法状态流转 %s -> %s，已钳制回 %s",
                           current_stage.value, stage, current_stage.value)
            target = current_stage
            reply = f"{reply}（当前阶段保持：{current_stage.value}）"
        if ui not in ALL_UI:
            ui = UI_TEXT

        # 生图确认关卡：每次进入 IMAGE_GEN 必须重新征求确认（清除历史标记）
        if target == SessionStage.IMAGE_GEN and target != current_stage:
            self.memory.clear_session_flags(
                user_id, session_id, prefix="image_")
            logger.info("进入生图确认阶段，已清除 image_* 标记（需重新征求用户同意）")

        self.memory.save_stage(user_id, session_id, target)
        # 短期记忆：仅存放对话文本层（保证上下文；工具细节通过 tool_calls 字段返回前端）
        self.memory.append_message(user_id, "assistant", json.dumps(
            {"role": "assistant", "content": reply}, ensure_ascii=False))
        return ChatResponse(
            user_id=user_id, reply=reply, ui=ui, data=data or {},
            tool_calls=records, session_id=session_id,
        )

    # ------------------------------------------------------------------
    def _build_system_prompt(self, user_role: str, stage: SessionStage, user_id: str) -> str:
        """构造系统提示词：角色、业务流、状态机、UI 协议、工具说明书、长期记忆。"""
        mem = self.memory.get_memories(user_id)
        memory_text = "；".join(f"{k}={v}" for k, v in mem.items()) or "（暂无）"
        allowed = ", ".join(allowed_targets(stage))

        return f"""{self.config.system_persona}

【用户角色】{user_role}（当前为普通用户）

【业务流程】
1. 理解用户自然语言购花需求；2. 弹窗询问选择"商家预设方案"或"DIY 定制方案"；
3. 展示商家方案（含效果图 URL）并请用户确认；4. DIY 则在需求基础上设计方案；
5. 用户要求查看效果图时，进入"生图确认"阶段：必须先向用户询问是否生成效果图
（dialog_options），只有用户明确同意后才可调用 generate_effect_image（异步，客户端轮询），
用户拒绝则不生成；每次重新生成效果图都需重新征求确认；6. 方案最终确认前，
允许用户在现有方案与 DIY 之间来回切换；7. 方案确认后调用 search_shops 按距离、
价格、服务推荐店铺；8. 用户选定店铺后调用 create_order 下单，并引导跳转支付页。

【当前业务阶段】{stage.value}
【允许进入的下一阶段】{allowed} —— respond_to_user 的 stage 字段必须取自此列表。

【UI 协议】每次结束对话必须调用 respond_to_user 携带：
- reply: 给用户的自然语言回复；
- ui: text | dialog_options | plan_card | shop_card | order_card | pay_jump；
- data 按 ui 约定：
  * dialog_options = {{"question": str, "options": [{{"label", "value"}}]}}
  * plan_card = {{"plan_id", "name", "price", "desc", "effect_image_url", "merchant_name", "plan_type"}}
  * shop_card = {{"shops": [{{"shop_id","name","address","distance_km","price_range","rating"}}], "question"}}
  * order_card = {{"order_id","plan_type","plan_name","quantity","total_price","shop_id"}}
  * pay_jump = {{"order_id", "page_path", "params": {{"order_id"}}}}
  * text = {{}}

【工具使用规范】
{tool_body_text()}
- 需要查询/操作数据时先调用工具，拿到结果后再 respond_to_user；
- 生成效果图（generate_effect_image）前必须先向用户确认（dialog_options 询问"是否生成效果图"），
  得到明确同意后才可调用；用户拒绝则直接进入方案确认/店铺推荐；重新生成同样需重新确认；
- 下单必须走 create_order 工具，随后以 ui=pay_jump 引导跳转支付页；
- 用户明确表达偏好（预算、送花对象、颜色、场合）时调用 save_memory 记录。

【用户长期记忆】{memory_text} —— 决策时优先贴合；
【闲聊】与购花无关的日常对话（问候、闲聊等）可不调用工具直接文本回复，并保留上下文。"""