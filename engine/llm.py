"""大模型封装：call_llm 统一入口。

- openai 后端：基于 openai>=1.x 客户端，base_url / api_key / model 全部可配置
  （兼容通义千问等 OpenAI 兼容端点，见 config.py 注释）；支持流式/非流式；
- mock 后端：无密钥时自动启用，脚本化走通"需求→弹窗→方案→确认→店铺→下单→支付"
  全链路，便于离线开发与自动化测试。
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    content: Optional[str] = None
    # 归一化 tool call：[{"id", "type": "function", "function": {"name", "arguments"}}]
    tool_calls: Optional[List[dict]] = None


class LLMError(Exception):
    """LLM 调用失败（网络/密钥/超时等）。"""


class LLMClient:
    def __init__(self, config, stage_reader: Optional[Callable[[str], str]] = None) -> None:
        self.config = config
        backend = config.llm_backend
        if backend == "auto":
            backend = "mock" if not config.llm_api_key else "openai"
            logger.info("LLM 后端 auto 解析结果: %s", backend)
        self.backend = backend

        if backend == "openai":
            if not config.llm_api_key:
                raise LLMError("LLM_BACKEND=openai 但未配置 OPENAI_API_KEY，请检查 .env")
            self.client = OpenAI(
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
                timeout=config.llm_timeout,
                max_retries=config.llm_max_retries,
            )
        else:
            self.mock = MockLLM(stage_reader)

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None) -> LLMResult:
        """非流式调用。流式接入点见 stream()，后续小程序 SSE 需求可直接复用。"""
        if self.backend == "mock":
            return self.mock.chat(messages)
        try:
            resp = self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=messages,
                tools=tools or None,
                temperature=self.config.llm_temperature,
                max_tokens=self.config.llm_max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.exception("LLM 调用失败")
            raise LLMError(f"LLM 调用失败: {exc}") from exc

        choice = resp.choices[0].message if resp.choices else None
        if choice is None:
            raise LLMError("LLM 返回空响应")
        tool_calls = None
        if choice.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in choice.tool_calls
            ]
        return LLMResult(content=choice.content, tool_calls=tool_calls)

    # ---------- 流式预留：小程序后续可经 SSE / WS 接收流式回复 ----------
    def stream(self, messages: List[dict], tools: Optional[List[dict]] = None):
        if self.backend == "mock":
            result = self.mock.chat(messages)
            yield json.dumps({"content": result.content, "finish": True})
            return
        stream = self.client.chat.completions.create(
            model=self.config.llm_model, messages=messages, tools=tools or None,
            temperature=self.config.llm_temperature, max_tokens=self.config.llm_max_tokens,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def is_stream_supported(self) -> bool:
        return True


class MockLLM:
    """脚本化 mock 大模型：按会话阶段推进业务流程，离线也能端到端演示。"""

    DIY_KEYWORDS = ("diy", "定制", "自己", "自定义")
    EXISTING_KEYWORDS = ("现有", "方案", "商家", "预设", "成品")

    def __init__(self, stage_reader: Optional[Callable[[str], str]] = None) -> None:
        self._stage_reader = stage_reader or (lambda uid: "ANALYZE")
        self._pending_tool: dict[str, str] = {}  # user_id -> 上一轮发出的工具名

    # ---------- 工具 / 回复的构造 ----------
    @staticmethod
    def _tool_call(name: str, arguments: dict) -> List[dict]:
        return [{
            "id": f"call_{name}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
        }]

    @staticmethod
    def _respond(reply: str, ui: str, data: dict, stage: str):
        data = json.dumps({"reply": reply, "ui": ui, "data": data, "stage": stage},
                          ensure_ascii=False)
        return LLMResult(tool_calls=MockLLM._tool_call("respond_to_user", json.loads(data)))

    def _user_id(self, messages: List[dict]) -> str:
        for msg in reversed(messages):
            if msg["role"] == "user":
                return str(msg["content"])[:0] or "mock-user"
        return "mock-user"

    # ---------- 主入口 ----------
    def chat(self, messages: List[dict]) -> LLMResult:
        last = messages[-1] if messages else {}
        user_id = self._discover_user(messages)

        # 有工具返回的观察消息：按上轮发出的工具名处理
        if last.get("role") == "tool":
            name = self._pending_tool.pop(user_id, "")
            return self._on_tool_result(user_id, name, last.get("content", ""))

        text = next((m["content"] for m in reversed(messages)
                     if m["role"] == "user"), "").strip().lower()
        stage = self._stage_reader(user_id).upper()
        return self._on_user_message(user_id, text, stage)

    @staticmethod
    def _discover_user(messages: List[dict]) -> str:
        """mock 无 user_id 入参：

        优先取真实请求上下文（api 启动时由 agent 注入），避免与持久化会话的
        身份不一致；测试等无上下文场景回退到首条用户消息的稳定 hash。
        """
        from runtime import get_runtime
        real_user = get_runtime().user_id.get()
        if real_user:
            return real_user
        for msg in messages:
            if msg["role"] == "user":
                return f"u_{abs(hash(str(msg['content'])[:12]))}"
        return "u_mock"

    # ---------- 工具结果 -> 回复 ----------
    def _on_tool_result(self, user_id: str, tool_name: str, content: str) -> LLMResult:
        if tool_name == "search_plans":
            try:
                plans = json.loads(content)
            except json.JSONDecodeError:
                plans = []
            if not plans:
                return self._respond(
                    "没有找到匹配的商家预设方案，要不要试试 DIY 定制？",
                    "dialog_options",
                    {"question": "如何继续？", "options": [
                        {"label": "DIY 定制方案", "value": "diy"},
                        {"label": "换个关键词试试", "value": "existing"},
                    ]},
                    "SELECT_MODE",
                )
            p = plans[0]
            return self._respond(
                f"为您找到商家预设方案《{p['name']}》（¥{p['price']}），效果图如下，"
                f"确认选择该方案吗？也可以切换 DIY 定制。",
                "plan_card",
                {
                    "plan_id": p["id"], "name": p["name"], "price": p["price"],
                    "desc": p.get("desc", ""), "effect_image_url": p.get("effect_image_url", ""),
                    "merchant_name": p.get("merchant_name", "入驻商家"),
                    "plan_type": "existing",
                },
                "PLAN_CONFIRM",
            )

        if tool_name == "generate_diy_plan":
            plan = json.loads(content)
            return self._respond(
                f"已按您的需求生成 DIY 方案（预估 ¥{plan['price_estimate']}），"
                f"可确认选择，也可生成效果图或切换商家方案。",
                "plan_card",
                {
                    "plan_id": plan["plan_id"], "name": plan["name"],
                    "price": plan["price_estimate"], "desc": f"花材：{plan['flowers']}（{plan['notes']}）",
                    "effect_image_url": "", "merchant_name": "DIY 定制", "plan_type": "diy",
                },
                "PLAN_CONFIRM",
            )

        if tool_name == "search_shops":
            shops = json.loads(content)
            return self._respond(
                "已按距离、价格、服务为您推荐以下店铺，请选择下单店铺：",
                "shop_card",
                {"shops": shops, "question": "确认选择哪家店铺下单？"},
                "SHOP_RECOMMEND",
            )

        if tool_name == "create_order":
            order = json.loads(content)
            return self._respond(
                f"订单已生成（订单号 {order['order_id']}，合计 ¥{order['total_price']}），"
                f"现在为您跳转小程序下单支付页面。",
                "pay_jump",
                {
                    "order_id": order["order_id"],
                    "page_path": "/pages/order/confirm/index",
                    "params": {"order_id": order["order_id"]},
                },
                "DONE",
            )

        if tool_name == "generate_effect_image":
            try:
                task = json.loads(content)
                task_id = task.get("task_id", content)
            except json.JSONDecodeError:
                task_id = content
            return self._respond(
                "效果图生成任务已提交，可通过任务接口查询结果。",
                "text", {"task_id": task_id, "poll_url": f"/tasks/{task_id}"}, "PLAN_CONFIRM",
            )

        return self._respond("好的，请继续说～", "text", {}, "ANALYZE")

    # ---------- 用户消息 -> 动作 ----------
    def _on_user_message(self, user_id: str, text: str, stage: str) -> LLMResult:
        if stage == "SELECT_MODE":
            if any(k in text for k in self.DIY_KEYWORDS):
                self._pending_tool[user_id] = "generate_diy_plan"
                return LLMResult(tool_calls=self._tool_call("generate_diy_plan", {"requirements": text or "一束表达心意的话"}))
            if any(k in text for k in self.EXISTING_KEYWORDS) or text:
                self._pending_tool[user_id] = "search_plans"
                return LLMResult(tool_calls=self._tool_call("search_plans", {"keyword": text or ""}))

        if stage == "PLAN_CONFIRM":
            if any(k in text for k in ("确认", "确定", "可以", "好的", "就要", "选择")):
                self._pending_tool[user_id] = "search_shops"
                return LLMResult(tool_calls=self._tool_call(
                    "search_shops", {"plan_type": "existing"}))
            if "效果图" in text:
                # 进入生图确认阶段：征询用户同意后（后端识别肯定意图）才可调生图工具
                return self._respond(
                    "好的，在生成效果图前需要您确认一下：是否现在生成 AI 效果图？",
                    "dialog_options",
                    {"question": "是否生成 AI 效果图？（免费）", "options": [
                        {"label": "生成效果图", "value": "yes"},
                        {"label": "暂不需要", "value": "no"},
                    ]},
                    "IMAGE_GEN",
                )
            if any(k in text for k in ("切换", "diy", "定制", "换成")):
                self._pending_tool[user_id] = "generate_diy_plan"
                return LLMResult(tool_calls=self._tool_call(
                    "generate_diy_plan", {"requirements": "温馨花束"}))
            if any(k in text for k in self.EXISTING_KEYWORDS):
                self._pending_tool[user_id] = "search_plans"
                return LLMResult(tool_calls=self._tool_call("search_plans", {"keyword": ""}))
            if "放弃" in text or "取消" in text:
                return self._respond("好的，随时可以重新开始新的选购～", "text", {}, "DONE")
            return self._respond("在最终确认方案前，您可以随时切换现有方案或 DIY 定制，也可以直接确认下单。",
                                 "text", {}, "PLAN_CONFIRM")

        if stage == "IMAGE_GEN":
            # 生图确认关卡：否定 -> 跳过；肯定 -> 调生图工具；其余 -> 继续询问
            if any(k in text for k in ("不用", "不要", "不需要", "算了", "跳过", "无需", "否")):
                return self._respond("好的，不生成效果图，我们继续下一步～",
                                     "text", {}, "PLAN_CONFIRM")
            if any(k in text for k in ("生成", "确认", "同意", "好", "可以", "要")):
                self._pending_tool[user_id] = "generate_effect_image"
                return LLMResult(tool_calls=self._tool_call(
                    "generate_effect_image", {"plan_text": text or "花束效果图"}))
            return self._respond(
                "是否生成 AI 效果图？", "dialog_options",
                {"question": "是否生成 AI 效果图？（免费）", "options": [
                    {"label": "生成效果图", "value": "yes"},
                    {"label": "暂不需要", "value": "no"},
                ]},
                "IMAGE_GEN",
            )

        if stage == "SHOP_RECOMMEND":
            if any(k in text for k in ("确认", "下单", "支付", "选择", "就这家")):
                self._pending_tool[user_id] = "create_order"
                return LLMResult(tool_calls=self._tool_call(
                    "create_order", {"plan_type": "existing", "plan_id": "p1",
                                     "plan_name": "康乃馨温情花束", "price": 158.0,
                                     "shop_id": "s1", "quantity": 1}))
            if "放弃" in text or "取消" in text:
                return self._respond("好的，订单已取消，随时可以重新开始～", "text", {}, "DONE")
            return self._respond("请确认选择哪家店铺下单，或回复放弃结束选购。",
                                 "text", {}, "SHOP_RECOMMEND")

        if stage == "ORDER_CONFIRM":
            if any(k in text for k in ("确认", "下单", "支付", "选择", "就这家")):
                self._pending_tool[user_id] = "create_order"
                return LLMResult(tool_calls=self._tool_call(
                    "create_order", {"plan_type": "existing", "plan_id": "p1",
                                     "plan_name": "康乃馨温情花束", "price": 158.0,
                                     "shop_id": "s1", "quantity": 1}))
            if "放弃" in text or "取消" in text:
                return self._respond("好的，订单已取消，随时可以重新开始～", "text", {}, "DONE")
            return self._respond("请确认选择哪家店铺下单，或回复放弃结束选购。",
                                 "text", {}, "ORDER_CONFIRM")

        if stage == "DONE":
            return self._respond("您可以随时找我重新选购鲜花～", "text", {}, "DONE")

        # ---------- 默认 / ANALYZE ----------
        if any(k in text for k in ("放弃", "再见", "拜拜")):
            return self._respond("好的，欢迎随时回来～", "text", {}, "DONE")
        return self._respond(
            "我了解您的鲜花选购需求啦！为您推荐两类方案：\n"
            "① 商家预设方案（已有现货与效果图）\n② DIY 定制方案（按您的需求生成）",
            "dialog_options",
            {"question": "请选择方案类型：", "options": [
                {"label": "查看商家预设方案", "value": "existing"},
                {"label": "DIY 定制方案", "value": "diy"},
            ]},
            "SELECT_MODE",
        )