"""engine/llm.py —— LLM 封装（OpenAI 兼容）+ 零配置 Mock 降级。

对外唯一入口：call_llm(messages, tools=None, stream=False)
- 配置了 LLM_API_KEY → 走 openai>=1.x 真实接口（支持 function calling）。
- 未配置 → 自动降级到内置 _MockEngine，基于「当前阶段 + 用户意图 + 已调用工具」
  输出与 OpenAI 兼容的响应（含 tool_calls 或 content），保证零配置也能跑通导购全链路。

返回结构对 agent 透明：agent 只解析 .choices[0].message 的 content / tool_calls，
不关心背后是真实模型还是 Mock。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from config import settings
from engine.state import SessionStage

logger = logging.getLogger("llm")

# --------------------------------------------------------------------------- #
# 兼容 OpenAI 响应结构的轻量容器（Mock 分支使用）
# --------------------------------------------------------------------------- #


@dataclass
class _MockToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class _MockMessage:
    content: str
    tool_calls: list[_MockToolCall] = field(default_factory=list)


@dataclass
class _MockChoice:
    """对齐 OpenAI 的 Choice 结构，使 resp.choices[0].message 对真实/Mock 一致。"""

    message: _MockMessage


@dataclass
class _MockResponse:
    choices: list[_MockChoice]


# --------------------------------------------------------------------------- #
# 真实 LLM 调用
# --------------------------------------------------------------------------- #


def _openai_call(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
) -> Any:
    """调用 OpenAI 兼容接口。密钥不打印，仅记录输入摘要与工具序列。"""
    from openai import OpenAI  # 仅真实路径才 import，未装也不影响 Mock

    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": stream,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    logger.info(
        "[llm] 真实请求 model=%s tools=%s stream=%s",
        settings.llm_model,
        [t["function"]["name"] for t in tools] if tools else None,
        stream,
    )
    return client.chat.completions.create(**kwargs)


# --------------------------------------------------------------------------- #
# Mock 引擎（零配置降级）
# --------------------------------------------------------------------------- #


def _parse_stage(messages: list[dict[str, Any]]) -> SessionStage:
    """从 system prompt 注入的「当前会话阶段：xxx」标记还原阶段。"""
    for m in messages:
        if m.get("role") == "system":
            hit = re.search(r"阶段[：:]\s*([a-z_]+)", m.get("content", ""))
            if hit:
                try:
                    return SessionStage(hit.group(1))
                except ValueError:
                    break
    return SessionStage.ANALYZE


def _latest_user(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _called_tools(messages: list[dict[str, Any]]) -> set[str]:
    """收集历史里 assistant 已发出的工具调用名，用于避免 Mock 重复调用。"""
    called: set[str] = set()
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                called.add(tc.get("function", {}).get("name") or tc.get("name", ""))
    return called


def _extract_budget(text: str) -> str | None:
    m = re.search(r"预算[约]*\s*(\d+)\s*元?", text)
    return m.group(1) if m else None


def _extract_keyword(text: str) -> str:
    """从用户消息里抠一个搜索词，供 Mock 调 search_plans 用。"""
    for kw in ("康乃馨", "玫瑰", "百合", "多肉", "绿植", "向日葵花", "鲜花", "花"):
        if kw in text:
            return kw
    return "鲜花"


def _intent(text: str) -> dict[str, bool]:
    """朴素意图识别，供 Mock 做分支。"""
    t = text.lower()
    return {
        "diy": any(k in t for k in ("diy", "自己", "手工", "自定", "自制")),
        "confirm": any(k in t for k in (
            "确认", "就这个", "好的", "可以", "要了", "下单", "确定", "行",
            "第一个", "第一家", "这家", "要这个", "就它", "这个方案", "选这个", "订",
        )),
        "abandon": any(k in t for k in ("不要", "重选", "换", "重新", "放弃", "不要了", "取消")),
        "image": any(k in t for k in ("生图", "效果图", "图片", "图", "渲染")),
        "pick_shop": any(k in t for k in ("第一家", "这家", "就这", "第二家", "选它", "这个店")),
    }


#: 明确属于闲聊/寒暄的短句词
_CHITCHAT_WORDS = (
    "你好", "您好", "在吗", "在么", "嗨", "哈喽", "谢谢", "感谢",
    "再见", "拜拜", "哈哈", "辛苦了", "赞", "呵呵",
)


def _is_chitchat(text: str) -> bool:
    """判断消息是否与花卉导购无关（纯寒暄/感谢）。"""
    t = text.strip().lower()
    if not t:
        return True
    # 含导购意图词则一定不是闲聊
    if any(k in t for k in (
        "买", "送", "花", "束", "预算", "方案", "diy", "自己", "店铺",
        "下单", "订单", "确认", "选", "要", "想要", "需要", "推荐",
        "生图", "效果", "图",
    )):
        return False
    return any(w in t for w in _CHITCHAT_WORDS)


def _chitchat_reply(stage: SessionStage) -> str:
    """闲聊时的轻量回复（按阶段给一句引导，不触发工具、不推进）。"""
    return {
        SessionStage.ANALYZE: "您好～我是您的花卉导购小助手🌿 想买花或送花，直接告诉我需求就好！",
        SessionStage.SELECT_MODE: "请问您想选【商家现有方案】还是【自己 DIY 设计】呢？",
        SessionStage.VIEW_PLAN: "上面是推荐方案，确认或想换方式都可以告诉我～",
        SessionStage.DIY_DESIGN: "上面是 DIY 草稿，需要生图或确认都行～",
        SessionStage.IMAGE_GEN: "效果图生成中，完成后会回到确认环节～",
        SessionStage.SHOP_RECOMMEND: "以上是推荐店铺，选一家我就帮您下单～",
        SessionStage.ORDER_CONFIRM: "订单已就绪，请在小程序完成支付～",
        SessionStage.DONE: "感谢您的选购，期待再次为您服务🌿",
    }.get(stage, "我在的，请问还有什么可以帮您？")


def _mock_decide(
    stage: SessionStage, user_msg: str, called: set[str]
) -> tuple[str, list[_MockToolCall]]:
    """返回 (回复文本, 工具调用列表)。无工具调用即视为最终回复。

    设计原则：每个用户回合（一次 run）内 Mock 至多推进「一步」。本轮先发一个
    工具，下一轮（用户下条消息）再根据新意图发下一个工具；否则只回文本。这样
    避免一轮 ReAct 里连发多个工具，导致 UI 类型与状态机阶段错位（例如刚查到
    方案就直接被推进到店铺推荐，前端拿不到 plan_card）。

    阶段推进与工具调用保持一致：
    - SELECT_MODE 选 DIY → 先问需求（不调工具，下轮在 DIY_DESIGN 出草稿）；
    - VIEW_PLAN / DIY_DESIGN 只有明确「确认/选定」才进店铺推荐；
    - 生图意图只做引导，真正调 generate_effect_image 在 IMAGE_GEN 阶段发生；
    - SHOP_RECOMMEND 先推荐店铺，用户选定后才下单。
    """
    intent = _intent(user_msg)
    budget = _extract_budget(user_msg)

    # 闲聊：与花卉导购无关的消息，不触发任何工具，仅对话回复（不推进阶段）
    if _is_chitchat(user_msg):
        return _chitchat_reply(stage), []

    # 1) 理解需求阶段：有预算则记一笔长期偏好，否则直接问模式
    if stage == SessionStage.ANALYZE:
        if budget and "save_memory" not in called:
            return (
                f"已记录您的预算约 {budget} 元。请问您想选择【商家现有方案】还是【自己 DIY 设计】？",
                [_MockToolCall("save_memory", {"key": "budget", "value": f"{budget} 元"})],
            )
        return ("请问您想选择【商家现有方案】还是【自己 DIY 设计】？", [])

    # 2) 模式选择阶段：DIY 先收集需求（不调工具）；现有方案一步查列表，确认交给下一回合
    if stage == SessionStage.SELECT_MODE:
        if intent["diy"]:
            return (
                "好的，DIY 请描述您的需求：送谁 / 什么场合 / 预算 / 喜好色系，我来为您设计～",
                [],
            )
        if "search_plans" not in called:
            kw = _extract_keyword(user_msg)
            return (
                f"好的，为您查找现有「{kw}」相关方案……",
                [_MockToolCall("search_plans", {"keyword": kw})],
            )
        return ("已为您找到方案，请确认或告诉我您想换一种方式。", [])

    # 3) 浏览现有方案：明确确认/选定才进店铺推荐
    if stage == SessionStage.VIEW_PLAN:
        if intent["abandon"]:
            return ("好的，我们重新选择购买方式。", [])
        if (intent["confirm"] or intent["pick_shop"]) and "search_shops" not in called:
            return (
                "已为您选定方案，正在推荐合适店铺……",
                [_MockToolCall("search_shops", {"plan": "latest"})],
            )
        return ("以上为推荐方案，确认或想换方式都可以告诉我～", [])

    # 4) DIY 设计：先出草稿；描述/提问不推进；生图只做引导；确认才进店铺推荐
    if stage == SessionStage.DIY_DESIGN:
        if intent["abandon"]:
            return ("好的，我们重新选择购买方式。", [])
        if "generate_diy_plan" not in called:
            return (
                "正在为您生成 DIY 花艺方案草稿……",
                [_MockToolCall("generate_diy_plan", {"requirements": user_msg})],
            )
        if intent["image"]:
            return (
                "好的，正在为您生成效果图，请稍候……",
                [],
            )
        if intent["confirm"] and "search_shops" not in called:
            return (
                "已生成 DIY 方案，正在推荐合适店铺……",
                [_MockToolCall("search_shops", {"plan": "latest_diy"})],
            )
        return ("DIY 草稿已就绪，可生图看效果或确认下单，也可以继续修改～", [])

    # 5) 生图阶段：先提交生图任务（前端轮询 /tasks），确认后才进店铺推荐
    if stage == SessionStage.IMAGE_GEN:
        if intent["abandon"]:
            return ("好的，我们重新选择购买方式。", [])
        if "generate_effect_image" not in called:
            return (
                "正在为您生成效果图，请稍候……",
                [_MockToolCall("generate_effect_image", {"plan": "latest_diy"})],
            )
        if intent["confirm"] and "search_shops" not in called:
            return (
                "效果图已就绪，正在推荐合适店铺……",
                [_MockToolCall("search_shops", {"plan": "latest_diy"})],
            )
        return ("效果图已生成，可确认后进入店铺推荐，也可以继续调整方案～", [])

    # 6) 店铺推荐：先出店铺卡片，用户选定后才下单
    if stage == SessionStage.SHOP_RECOMMEND:
        if intent["abandon"]:
            return ("好的，我们回到方案确认环节重新选择。", [])
        if "search_shops" not in called:
            return (
                "正在为您推荐合适店铺……",
                [_MockToolCall("search_shops", {"plan": "latest"})],
            )
        if (intent["confirm"] or intent["pick_shop"]) and "create_order" not in called:
            plan_type = "diy" if "latest_diy" in called else "existing"
            return (
                "正在为您组装订单并生成支付跳转参数……",
                [_MockToolCall("create_order", {"shop_id": "first", "plan_id": "latest", "plan_type": plan_type})],
            )
        return ("以上为推荐店铺，选一家我就帮您下单～", [])

    # 7) 已完成
    return ("感谢您的选购，期待再次为您服务 🌿", [])


def _mock_llm_response(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> _MockResponse:
    """Mock 引擎：解析阶段与意图，产出与 OpenAI 兼容的响应。

    一次 run 内严格执行「一次一步」：若上一条消息是工具回执（observation），
    本轮只回引导文本、不再发工具，保证每轮至多推进一步（工具结果/UI 与阶段不错位）。
    """
    stage = _parse_stage(messages)
    user_msg = _latest_user(messages)

    if messages and messages[-1].get("role") == "tool":
        reply = {
            SessionStage.VIEW_PLAN: "已为您找到方案，请确认或告诉我您想换一种方式。",
            SessionStage.DIY_DESIGN: "DIY 草稿已就绪，可生图看效果或确认下单，也可以继续修改～",
            SessionStage.IMAGE_GEN: "效果图任务已提交，稍后可在小程序查看效果图；确认后为您推荐店铺～",
            SessionStage.SHOP_RECOMMEND: "以上为推荐店铺，选一家我就帮您下单～",
        }.get(stage, "好的，还有什么可以帮您？")
        logger.info("[llm:mock] stage=%s 工具回填轮（只回文本）", stage.value)
        return _MockResponse(choices=[_MockChoice(message=_MockMessage(content=reply, tool_calls=[]))])

    called = _called_tools(messages)
    reply, tool_calls = _mock_decide(stage, user_msg, called)
    logger.info("[llm:mock] stage=%s reply=%s tools=%s", stage.value, reply[:30], [t.name for t in tool_calls])
    return _MockResponse(choices=[_MockChoice(message=_MockMessage(content=reply, tool_calls=tool_calls))])


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #


def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
) -> Any:
    """统一的 LLM 调用入口。

    Args:
        messages: OpenAI 格式消息列表（system/user/assistant/tool）。
        tools: OpenAI function-calling 工具定义列表；为 None 时走纯文本补全。
        stream: 是否流式（本期真实接口支持，agent 默认非流式）。

    Returns:
        与 OpenAI ChatCompletion 兼容的对象（.choices[0].message 含 content/tool_calls）。
        未配置密钥时返回 _MockResponse（结构兼容）。

    Raises:
        RuntimeError: 真实接口调用失败时抛出，由上层捕获并记录。
    """
    if settings.llm_enabled:
        try:
            return _openai_call(messages, tools, stream)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[llm] 真实接口调用失败，将信息上抛由 agent 处理")
            raise RuntimeError(f"LLM 调用失败: {exc}") from exc
    return _mock_llm_response(messages, tools)
