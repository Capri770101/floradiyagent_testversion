"""engine/llm.py —— LLM 封装（OpenAI 兼容，live-only）。

对外唯一入口：call_llm(messages, tools=None, stream=False)
- 配置了 LLM_API_KEY → 走 openai>=1.x 真实接口（支持 function calling）。
- 未配置 → 直接抛 RuntimeError（系统已弃用 Mock 引擎，必须配置真实密钥）。

返回结构对 agent 透明：agent 只解析 .choices[0].message 的 content / tool_calls。
"""

from __future__ import annotations

import logging
from typing import Any

from config import settings

logger = logging.getLogger("llm")


def _openai_call(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
    response_format: dict[str, Any] | None = None,
) -> Any:
    """调用 OpenAI 兼容接口。密钥不打印，仅记录输入摘要与工具序列。"""
    from openai import OpenAI  # 仅真实路径才 import

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
    if response_format:
        kwargs["response_format"] = response_format

    logger.info(
        "[llm] 真实请求 model=%s tools=%s stream=%s",
        settings.llm_model,
        [t["function"]["name"] for t in tools] if tools else None,
        stream,
    )
    return client.chat.completions.create(**kwargs)


def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    response_format: dict[str, Any] | None = None,
) -> Any:
    """统一的 LLM 调用入口（live-only）。

    Args:
        messages: OpenAI 格式消息列表（system/user/assistant/tool）。
        tools: OpenAI function-calling 工具定义列表；为 None 时走纯文本补全。
        stream: 是否流式（本期真实接口支持，agent 默认非流式）。

    Returns:
        与 OpenAI ChatCompletion 兼容的对象（.choices[0].message 含 content/tool_calls）。

    Raises:
        RuntimeError: 未配置 LLM_API_KEY（系统已弃用 Mock 引擎，必须配置真实密钥）。
    """
    if not settings.llm_enabled:
        raise RuntimeError(
            "未配置 LLM_API_KEY，系统已切换为 live-only（已弃用 Mock 引擎）。"
            "请在 .env 配置 LLM_API_KEY 后启动。"
        )
    try:
        return _openai_call(messages, tools, stream, response_format)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[llm] 真实接口调用失败，将信息上抛由 agent 处理")
        raise RuntimeError(f"LLM 调用失败: {exc}") from exc
