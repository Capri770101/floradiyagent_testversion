"""live_check.py —— 用真实实例判断智能体设计质量的入口脚本。

为什么需要它：
- 本服务是纯 API（H5 为独立前端，Vite 构建后单独部署，不在此挂载），直接用 curl 看到的是一大坨 JSON，不直观。
- 本脚本把「设计引擎 / 完整对话」的真实产出（DeepSeek 实跑）结构化打印出来，
  并附带「质量判断点」，你对着看就能判断设计质量达标与否。

运行环境（项目真实依赖装在 Python 3.12）：
    C:/Users/Capri/AppData/Local/Programs/Python/Python312/python.exe agent/examples/live_check.py

说明：
- 一运行即真实调用 DeepSeek（产生少量额度消耗），不是 mock。
- 配置来自项目根目录 .env，import backend.config as config 时自动加载，无需手动 export。
- 顶部 MODE 变量切换：「design」= 跑设计引擎对比（快，聚焦设计质量）；
  「chat」= 跑完整多轮对话（含改设计 + 生图，慢但完整）。

质量判断点（脚本会逐项提示你对着看）：
  1. 配花/配色是否贴合语义（如「治愈系」→ 暖色向日葵/洋甘菊，而非套路玫瑰）。
  2. 文案/花语是否有故事感、不模板化。
  3. 顶层 diy_steps / budget_breakdown 是否与设计内层自洽（不残留规则基线）。
  4. 改设计后 plan_id 的 parent_id / version 是否可追溯。
  5. effect_prompt 是否 readable、能生成合理图。
  6. 流程是否灵活（中途改、跳过某步仍成立）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 脚本位于 agent/examples/ 子目录，把项目根目录加入 sys.path 才能 import backend.config as config/tools/agent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.config import settings

# ── 切换模式： "design"（默认，快） 或 "chat"（完整对话，含生图）──────────
MODE = "design"
# ────────────────────────────────────────────────────────────────────────


def _check_live() -> None:
    """确认当前跑的是真实 LLM，避免误以为在看 mock。"""
    print("=" * 72)
    print(f"  LLM 模式 : {'LIVE (真实 DeepSeek)' if settings.llm_enabled else 'MOCK/未配置'}")
    print(f"  生图模式 : {'LIVE' if settings.image_enabled else 'MOCK'}")
    print(f"  RAG 检索 : {'开启' if settings.rag_enabled else '关闭'}")
    print("=" * 72)
    if not settings.llm_enabled:
        raise SystemExit("⚠️ 未配置 LLM_API_KEY，无法跑真实实例。请检查 .env。")


def _names(lst: object, key: str = "name") -> str | None:
    """从 [{name:..}, ...] 抽取姓名串。"""
    if not isinstance(lst, list):
        return None
    return "、".join(str(x.get(key)) for x in lst if isinstance(x, dict))


def _print_plan(title: str, plan: dict) -> None:
    """结构化打印一份方案，并标出质量判断点。

    关键对照：design 内层（LLM 语义版） vs 顶层 diy_steps/budget_breakdown（规则基线）。
    两者不一致 = 表里不一 bug（_merge_plan 只覆盖 design 内层）。
    """
    from agent.tools import _match_style

    d = plan.get("design", {}) or {}
    print(f"\n{'─' * 72}\n  📋 {title}\n{'─' * 72}")
    print(f"  方案名   : {plan.get('name')}  (plan_id={plan.get('plan_id')})")
    print(f"  版本追溯 : version={plan.get('version')}  parent_id={plan.get('parent_id')}")
    # 修法 B 验证：style 名反查出的 id 是否与当前 style_id 一致
    expected_sid, expected_sub, expected_subname = _match_style(plan.get("style"))
    sid_ok = (expected_sid == plan.get("style_id")) or expected_sid is None
    anchor_flag = "✅ 已锚定" if sid_ok else f"❌ 错位(应为 {expected_sid})"
    print(f"  风格     : {plan.get('style')}  (style_id={plan.get('style_id')})  [{anchor_flag}]")
    print(f"  对象/场景: {plan.get('recipient')} / {plan.get('occasion')}")
    print(f"  主花     : {_names(d.get('main_flowers'))}")
    print(f"  填充/叶材: {_names(d.get('fillers'))} / {_names(d.get('foliage'))}")
    print(f"  色系     : {d.get('color_scheme')}")
    print(f"  文案     : {d.get('card_message') or plan.get('card_message')}")
    print(f"  effect_prompt: {plan.get('effect_prompt')}")
    print("  ── 质量判断点（重点对照：design内层 主花/填充  vs 顶层基线）──")
    print(f"  [3a] 顶层 diy_steps  : {plan.get('diy_steps')}")
    print(f"  [3b] 顶层 budget     : {plan.get('budget_breakdown')}")
    print(f"  [3c] design.budget   : {d.get('budget_breakdown')}")
    print("  [1] 配花配色贴合语义?  [2] 文案有故事感?  [3] 3a/3b 与 主花/填充 自洽?")
    print("  [4] parent/version 可追溯?  [5] effect_prompt 能生成合理图?")


def run_design_demo() -> None:
    """跑 3 个代表性需求的设计引擎对比（真实 DeepSeek）。"""
    from agent.tools import design_diy_plan, revise_diy_plan

    cases = [
        ("治愈系·送妈妈", "帮我做一个治愈系的花束送妈妈，预算200左右，希望她每天看到心情好"),
        ("失恋朋友·重生感", "朋友刚失恋，想送一束有『破晓重生』感觉的花，不要太俗气的红玫瑰"),
        ("妈妈生日·不俗气", "妈妈生日，想要惊喜感但不想太俗气，预算300，最好有她的名字元素"),
    ]
    plans = []
    for name, text in cases:
        plan = design_diy_plan(text)
        plans.append(plan)
        _print_plan(f"需求：{name}", plan)

    # 演示「改设计」追溯：把第一个方案主花换掉，看 parent_id/version
    print(f"\n{'=' * 72}\n  🔁 演示「改设计」追溯能力\n{'=' * 72}")
    plan0 = plans[0]
    # 注意：revise_diy_plan 的 plan 参数要传「方案 JSON 文本」而非 plan_id 字符串，
    # 否则 _parse_plan 解析失败 → original 为空 → parent_id 落 None（追溯断链）。
    new_plan_str = revise_diy_plan(json.dumps(plan0, ensure_ascii=False),
                                   "主花换成向日葵，整体配色再明亮一点",
                                   _context={"user_id": "demo_user"})
    new_plan = json.loads(new_plan_str) if isinstance(new_plan_str, str) else new_plan_str
    _print_plan("改设计后（应 version=2, parent 指向原版）", new_plan)


async def run_chat_demo() -> None:
    """跑完整多轮对话（真实 ReAct + 改设计 + 生图）。"""
    from agent.agent import ReActAgent

    agent = ReActAgent()
    turns = [
        "帮我做一个治愈系花束送妈妈，预算200",
        "主花换成向日葵，整体配色再明亮一点",
        "好，帮我生成效果图",
    ]
    for i, msg in enumerate(turns, 1):
        print(f"\n{'#' * 72}\n  👤 用户第 {i} 轮: {msg}\n{'#' * 72}")
        res = await agent.arun("demo_user", msg)
        data = res.model_dump() if hasattr(res, "model_dump") else res
        print(f"  🤖 回复: {data.get('reply')}")
        print(f"  🎯 focus: {data.get('focus')}  ui_type: {data.get('ui_type')}")
        print(f"  🖼️  生图 task_id: {data.get('task_id')}")
        print(f"  📦 数据摘要: {json.dumps(data.get('data', {}), ensure_ascii=False)[:400]}")


def main() -> None:
    _check_live()
    if MODE == "chat":
        asyncio.run(run_chat_demo())
    else:
        run_design_demo()
    print(f"\n{'=' * 72}\n  ✅ 真实实例跑完。对照上面的「质量判断点」即可评估设计质量。\n{'=' * 72}")


if __name__ == "__main__":
    main()
