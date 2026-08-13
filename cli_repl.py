"""cli_repl.py —— 无 UI 时的智能体命令行调试器。

为什么需要它：
- 独立智能体开发早期往往没有配套前端。与其每次开浏览器点 /docs，
  不如在终端里直接"发消息、看返回"，像聊天一样推进开发。
- 支持两种模式：
    * 默认（读 .env）：走真实 DeepSeek + 万相（抽测/验收用，会消耗额度）。
    * --mock：强制覆盖 .env 走内置离线引擎（零成本、确定性，回归用）。
- 支持 --demo：非交互跑一条内置脚本后退出，方便自己验证和 CI 冒烟。

注意：mock 覆盖必须在 import config / agent 之前设置，才能盖掉 .env 里的真实密钥。
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

# ⚠️ 必须在 import config / agent 之前设定，才能覆盖 .env 走 mock 引擎。
if "--mock" in sys.argv:
    os.environ["LLM_API_KEY"] = ""
    os.environ["IMAGE_PROVIDER"] = "mock"

from agent import ReActAgent  # noqa: E402  —— 放 mock 覆盖之后才导入
from config import settings  # noqa: E402

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"


def _c(text: str, code: str, use_color: bool) -> str:
    """简单的 ANSI 上色；非 tty / 关色时原样返回，避免 Windows 终端乱码。"""
    if not use_color:
        return text
    return f"{code}{text}{RESET}"


def print_response(resp: dict, use_color: bool) -> None:
    """把一轮响应按「模式 / stage / ui / 工具 / 回复」拆解打印，便于人工判断。"""
    stage = resp.get("stage", "?")
    ui = resp.get("ui", "?")
    reply = resp.get("reply", "") or ""
    tool_calls = resp.get("tool_calls", []) or []

    print(_c(f"  ├─ mode : {ui}", CYAN, use_color))
    print(_c(f"  ├─ stage: {stage}", CYAN, use_color))
    if tool_calls:
        names = ", ".join(tc.get("name", "?") for tc in tool_calls)
        print(_c(f"  ├─ tools: {names}", YELLOW, use_color))
    print(_c(f"  └─ reply: {reply[:200]}", GREEN, use_color))


def run_demo(agent: ReActAgent, use_color: bool) -> None:
    """非交互：跑一条内置导购脚本，验证端到端链路不崩、状态机推进正常。"""
    uid = f"cli_demo_{uuid.uuid4().hex[:8]}"  # 随机 uid，避免沿用开发库里的历史会话
    script = [
        "想给母亲买一束花，预算200元左右",
        "选现有方案",
        "就第一个吧",
        "第一家",
    ]
    print(_c("=== DEMO 模式：内置脚本 ===\n", BOLD, use_color))
    for i, msg in enumerate(script, 1):
        print(_c(f"[第{i}轮] 你 > {msg}", BOLD, use_color))
        resp = agent.run(uid, msg, session_id=None, user_role="user", location=None).model_dump()
        print_response(resp, use_color)
        print()
    print(_c("DEMO 完成 ✅", BOLD, use_color))


def repl(agent: ReActAgent, use_color: bool) -> None:
    """交互式 REPL：像聊天一样逐轮发消息，实时看智能体返回。"""
    uid = "cli_user"
    print(_c("=== 交互模式（输入 /reset 开新会话，/quit 退出）===\n", BOLD, use_color))
    while True:
        try:
            line = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/reset":
            # run() 按 user_id 串联上下文，换 uid 即等同于清空历史、开新会话
            uid = f"cli_user_{uuid.uuid4().hex[:8]}"
            print(_c("  （已开启新会话）\n", YELLOW, use_color))
            continue
        resp = agent.run(uid, line, session_id=None, user_role="user", location=None).model_dump()
        print_response(resp, use_color)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="花卉导购智能体命令行调试器")
    parser.add_argument("--mock", action="store_true", help="强制走离线 Mock 引擎（不花真实额度）")
    parser.add_argument("--demo", action="store_true", help="非交互跑内置脚本后退出")
    parser.add_argument("--color", action="store_true", help="强制开启 ANSI 彩色输出")
    args = parser.parse_args()

    # 默认仅当 stdout 是终端且未显式关色时才上色，避免管道/CI 里出现乱码转义符。
    use_color = args.color and sys.stdout.isatty()

    mode = "LIVE（真实 DeepSeek + 万相，消耗额度）" if settings.llm_enabled else "MOCK（离线引擎，零成本）"
    print(_c(f"智能体模式：{mode}", BOLD, use_color))
    if settings.llm_enabled:
        print(_c("⚠️ 当前为真实模型模式，每轮都会调用 DeepSeek/万相并产生费用。", YELLOW, use_color))

    agent = ReActAgent()
    if args.demo:
        run_demo(agent, use_color)
    else:
        repl(agent, use_color)


if __name__ == "__main__":
    main()
