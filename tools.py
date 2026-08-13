"""tools.py —— 工具注册表 TOOL_REGISTRY + 内建工具。

设计：
- 每个工具用 @register_tool 装饰，自动写入 TOOL_REGISTRY（名称 / 中文描述 / 参数 JSON Schema / 实现）。
- agent 从注册表自动生成「工具说明书」注入 system prompt，并生成 OpenAI function-calling 定义。
- 新增工具只要写一个带装饰器的函数，agent 与提示词零改动。
- 需要用户上下文（如 user_id）的工具加 inject_context=True，execute_tool 时注入 _context。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from engine.ui_protocol import UIType
from knowledge import get_by_id, query_knowledge
from requirements import FlowerRequirement
from storage import memory, tasks
from storage.repository import repo

logger = logging.getLogger("tools")


# --------------------------------------------------------------------------- #
# 注册表
# --------------------------------------------------------------------------- #


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]            # JSON Schema
    func: Callable[..., Any]
    inject_context: bool = False          # True 时注入 _context（含 user_id 等）
    tags: set[str] = field(default_factory=set)


#: 全局工具注册表，agent 与提示词都从这里取
TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    inject_context: bool = False,
    tags: list[str] | None = None,
) -> Callable[[Callable], Callable]:
    """装饰器：把函数登记进 TOOL_REGISTRY。"""

    def deco(func: Callable) -> Callable:
        TOOL_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
            inject_context=inject_context,
            tags=set(tags or []),
        )
        return func

    return deco


# --------------------------------------------------------------------------- #
# 内建工具
# --------------------------------------------------------------------------- #


def _requirement_from_context(_context: dict | None) -> FlowerRequirement | None:
    """从工具上下文取出结构化需求（由 agent 每轮抽取并注入）。"""
    if not _context:
        return None
    req = _context.get("requirement")
    return req if isinstance(req, FlowerRequirement) else None


def _store_diy_plan(plan: dict, _context: dict | None) -> None:
    """把最新 DIY 方案写入当前会话（会话级，替代旧全局变量，杜绝多用户串号）。

    latest_diy_plan 供生图生成精确 prompt；selected_plan 作为「最近引用方案」，
    让 search_shops / create_order 的 latest 占位符解析到正确方案。
    """
    uid = (_context or {}).get("user_id", "")
    sid = (_context or {}).get("session_id", "")
    if not uid or not sid:
        return
    memory.set_session_json(uid, sid, "latest_diy_plan", plan)
    memory.set_session_json(uid, sid, "selected_plan", plan)


def _resolve_session_plan(plan: str | None, _context: dict | None) -> dict | None:
    """把工具参数里的方案引用解析为具体方案 dict。

    - "latest" / "latest_diy" / 空：会话「最近引用方案」→ 会话最新 DIY 方案 → 首条预设方案。
    - 显式 plan_id：先查仓库（现有方案）；查不到且形如 DIY_xxx 时回退到会话最新 DIY 方案。
    - 解析结果与用户、会话绑定，不再依赖进程级全局状态（并发安全）。
    """
    uid = (_context or {}).get("user_id", "")
    sid = (_context or {}).get("session_id", "")
    if plan in ("latest", "latest_diy", "", None):
        if sid:
            selected = memory.get_session_json(uid, sid, "selected_plan")
            if selected:
                return selected
            diy = memory.get_session_json(uid, sid, "latest_diy_plan")
            if diy:
                return diy
        plans = repo.search_plans("")
        return plans[0] if plans else None
    found = repo.get_plan(plan)
    if found:
        return found
    if sid:
        diy = memory.get_session_json(uid, sid, "latest_diy_plan")
        if diy and (diy.get("plan_id") == plan or str(plan).startswith("DIY_")):
            return diy
    return None


@register_tool(
    name="search_plans",
    description=(
        "搜索商家预设花卉方案（含名称、价格、描述、效果图 URL）；"
        "会结合当前会话的结构化需求（预算/色系/风格）做软过滤。"
    ),
    parameters={
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "搜索关键词，如 康乃馨 / 玫瑰 / 母亲；留空则浏览全部"}},
        "required": ["keyword"],
    },
    inject_context=True,
    tags=["plan"],
)
def search_plans(keyword: str, _context: dict | None = None) -> str:
    """搜索商家预设方案（按结构化需求软过滤）。"""
    req = _requirement_from_context(_context)
    plans = repo.search_plans(keyword, requirement=req)
    return json.dumps(plans, ensure_ascii=False)


@register_tool(
    name="get_plan_detail",
    description="根据方案 ID 获取单个方案的完整详情。",
    parameters={
        "type": "object",
        "properties": {"plan_id": {"type": "string", "description": "方案 ID，如 P001"}},
        "required": ["plan_id"],
    },
    tags=["plan"],
)
def get_plan_detail(plan_id: str) -> str:
    """获取方案详情。"""
    plan = repo.get_plan(plan_id)
    return json.dumps(plan or {"error": "not found"}, ensure_ascii=False)


@register_tool(
    name="retrieve_knowledge",
    description=(
        "检索花卉 DIY 知识库：花材(花语/色系/季节/价格档/搭配性)、风格体系、搭配规则、"
        "预算映射、包装器型。在设计方案前调用以获取可靠的领域知识，避免凭空编造。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "检索域：flower(花材) | style(风格) | pairing(搭配规则) | budget(预算) | packaging(包装) | all(全部)",
            },
            "query": {"type": "string", "description": "关键词或自然语言，如 母亲/生日/北欧/200元"},
        },
        "required": ["domain", "query"],
    },
    tags=["knowledge"],
)
def retrieve_knowledge(domain: str, query: str) -> str:
    """检索知识库，返回相关条目 JSON。"""
    result = query_knowledge(domain, query)
    return json.dumps(result, ensure_ascii=False)


@register_tool(
    name="generate_diy_plan",
    description=(
        "根据用户需求设计一份结构化 DIY 花艺方案：抽取维度→查知识库→组装主花/配材/配比、"
        "色彩方案、包装、寓意文案与预算估算，并返回可供生图的 effect_prompt。"
        "输出另含分步插花指引(diy_steps)、养护建议(care_tips)、贺卡寄语文案(card_message)与预算明细(budget_breakdown)。"
    ),
    parameters={
        "type": "object",
        "properties": {"requirements": {"type": "string", "description": "用户的 DIY 需求描述"}},
        "required": ["requirements"],
    },
    inject_context=True,
    tags=["diy"],
)
def generate_diy_plan(requirements: str, _context: dict | None = None) -> str:
    """设计 DIY 方案（基于知识库的结构化生成），并写入当前会话供生图/下单引用。"""
    plan = design_diy_plan(requirements)
    _store_diy_plan(plan, _context)
    return json.dumps(plan, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# DIY 设计核心：抽维度 → 查知识库 → 组装结构化方案
# --------------------------------------------------------------------------- #

#: 维度关键词表（轻量规则抽取，不依赖额外 NLP）
_RECIPIENT_KW = {
    "妈妈": "母亲", "母亲": "母亲", "妈": "母亲", "娘": "母亲",
    "恋人": "恋人", "女朋友": "恋人", "男朋友": "恋人", "老婆": "恋人",
    "老公": "恋人", "对象": "恋人", "爱人": "恋人",
    "男友": "恋人", "女友": "恋人", "先生": "恋人", "丈夫": "恋人",
    "朋友": "朋友", "闺蜜": "朋友", "兄弟": "朋友", "同事": "朋友", "姐妹": "朋友",
    "自己": "自己", "悦己": "自己", "我": "自己",
    "长辈": "长辈", "老人": "长辈", "父母": "长辈", "领导": "长辈", "上司": "长辈",
    "老板": "长辈", "老师": "长辈",
    "宝宝": "宝宝", "婴儿": "宝宝", "新生儿": "宝宝",
}
_OCCASION_KW = {
    "生日": "生日", "庆祝": "生日",
    "母亲节": "母亲", "父亲节": "父亲", "节": "节日",
    "告白": "告白", "表白": "告白", "纪念日": "告白", "求婚": "告白",
    "婚礼": "婚礼", "结婚": "婚礼", "领证": "婚礼",
    "探病": "探病", "生病": "探病", "康复": "探病", "住院": "探病",
    "道歉": "道歉", "对不起": "道歉", "抱歉": "道歉",
    "毕业": "毕业", "乔迁": "乔迁", "开业": "开业", "升职": "升职", "入职": "入职",
}
_STYLE_KW = {
    "韩式": "S_KOREAN", "韩系": "S_KOREAN",
    "北欧": "S_NORDIC", "简约": "S_NORDIC", "极简": "S_NORDIC",
    "复古": "S_VINTAGE", "古典": "S_VINTAGE", "港风": "S_VINTAGE", "中古": "S_VINTAGE",
    "自然": "S_NATURAL", "野趣": "S_NATURAL", "田园": "S_NATURAL",
    "ins": "S_INS", "ins风": "S_INS", "网红": "S_INS", "奶油风": "S_INS", "法式": "S_INS",
    "日式": "S_JAPANESE", "禅": "S_JAPANESE", "日系": "S_JAPANESE",
}
_COLOR_KW = {
    "红": "红", "粉": "粉", "白": "白", "香槟": "香槟", "紫": "紫",
    "蓝": "蓝", "黄": "黄", "橙": "橙", "绿": "绿", "多彩": "多彩混合",
    "亮": "亮", "鲜艳": "亮", "缤纷": "多彩混合",
    "粉嫩": "粉", "浅粉": "粉", "桃红": "粉", "正红": "红", "酒红": "红",
    "橘": "橙", "鹅黄": "黄", "天蓝": "蓝", "湖蓝": "蓝", "香槟色": "香槟",
    "五彩": "多彩混合", "撞色": "多彩混合",
}
_MOOD_KW = {
    "温柔": "温柔", "温馨": "温馨", "浪漫": "浪漫", "清新": "清新",
    "热烈": "热烈", "活泼": "活泼", "高级": "高级", "素雅": "素雅", "优雅": "优雅",
    "莫兰迪": "素雅", "马卡龙": "清新", "小清新": "清新", "轻奢": "高级",
    "低调": "素雅", "治愈": "治愈", "安静": "素雅", "甜美": "甜美",
    "氛围感": "优雅", "高级感": "高级",
}
#: 口语化预算表述 → 估算金额（替换进文本后由数字正则统一抽取）
_BUDGET_ORAL = {
    "一两百": 150, "一二百": 150, "小几百": 200, "两三百": 250, "二三百": 250,
    "三四百": 350, "三五百": 400, "五六百": 550, "七八百": 750,
    "千把块": 1000, "一千": 1000, "一两千": 1500, "两三千": 2500,
}

#: 场景/节日关键词 → scenes.json 中的 id（模块加载时由知识库构建，避免与 JSON 重复）
def _build_scene_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for s in query_knowledge("scene", "")["results"]:
        for kw in s.get("keywords", []):
            m[kw] = s["id"]
    return m


_SCENE_MAP = _build_scene_map()


def _get_style_full(style_id: str | None) -> tuple[dict | None, dict | None]:
    """解析风格（含子风格）：返回 (resolved_style, parent_style)。

    先查顶层风格；再查各风格的 substyles；找不到返回 (None, None)。
    resolved_style 用于取 typical_flowers/color_palette/packaging/vibe；
    parent_style 在子风格缺字段时回退。
    """
    if not style_id:
        return None, None
    top = get_by_id("style", style_id)
    if top:
        return top, top
    for parent in query_knowledge("style", "")["results"]:
        for sub in parent.get("substyles", []):
            if sub["id"] == style_id:
                return sub, parent
    return None, None


#: 全部花材名（反馈解析时用于识别「不要X花」）
_ALL_FLOWER_NAMES: list[str] = [f["name"] for f in query_knowledge("flower", "")["results"]]


def _get_tier(budget_num: int | None, scene_anchor: str | None) -> dict:
    """解析预算档：显式预算优先 → 场景锚点 → 默认「精致/送礼」档。"""
    all_tiers = query_knowledge("budget", "")["results"]
    if budget_num is not None:
        t = next((t for t in all_tiers if t["range"][0] <= budget_num <= t["range"][1]), None)
        if t:
            return t
    if scene_anchor:
        t = next((t for t in all_tiers if t["tier"] == scene_anchor), None)
        if t:
            return t
    return all_tiers[1]


def _infer_substyle(style_id: str, dims: dict[str, str]) -> str | None:
    """未由场景指定子风格时，按情感/氛围从粗风格推导细分。"""
    mood = dims.get("mood", "")
    if style_id == "S_KOREAN":
        return "S_KOREAN_LUXE" if mood in ("高级", "克制") else "S_KOREAN_SWEET"
    if style_id == "S_NORDIC":
        return "S_NORDIC_MINIMAL" if mood in ("极简", "文艺", "素雅") else "S_NORDIC_PASTORAL"
    if style_id == "S_VINTAGE":
        return "S_VINTAGE_HK" if mood in ("港风", "怀旧", "浓烈") else "S_VINTAGE_OIL"
    if style_id == "S_NATURAL":
        return "S_NATURAL_FOREST" if mood in ("森系", "治愈", "安静") else "S_NATURAL_WILD"
    if style_id == "S_INS":
        return "S_INS_POP" if mood in ("撞色", "活泼", "年轻", "打卡") else "S_INS_CREAM"
    if style_id == "S_JAPANESE":
        return "S_JAPANESE_SEASON" if mood in ("季节", "情绪") else "S_JAPANESE_MINIMAL"
    return None


def _parse_plan(plan: str) -> dict:
    """尽力解析传入的方案（可能是 JSON 字符串或含 JSON 的文本）。"""
    if isinstance(plan, dict):
        return plan
    text = plan.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试抽取第一个 { ... } 块
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _dims_from_plan(plan: dict) -> dict[str, str]:
    """从已有方案反推设计维度，供迭代时复用。"""
    dims: dict[str, str] = {}
    if plan.get("recipient"):
        dims["recipient"] = plan["recipient"]
    if plan.get("occasion"):
        dims["occasion"] = plan["occasion"]
    if plan.get("style_id"):
        dims["style"] = plan["style_id"]
    if plan.get("substyle_id"):
        dims["substyle"] = plan["substyle_id"]
    if plan.get("scene_id"):
        dims["scene"] = plan["scene_id"]
    if plan.get("budget_num") is not None:
        dims["budget"] = str(plan["budget_num"])
    elif plan.get("budget_tier"):
        # 从档位标签回推一个代表值
        for t in query_knowledge("budget", "")["results"]:
            if t["label"] == plan["budget_tier"]:
                dims["budget"] = str(t["range"][0])
                break
    # 主花名 → 作为色系无关的方向（保持主花）
    design = plan.get("design", {})
    main = [m["name"] for m in design.get("main_flowers", [])]
    if main:
        dims["_keep_main"] = ",".join(main)
    return dims


def _extract_feedback(feedback: str) -> dict[str, Any]:
    """解析自然语言反馈为调整指令：维度覆盖 + 需移除花材集合。"""
    import re

    dims: dict[str, str] = {}
    exclude: set[str] = set()
    # 预算
    m = re.search(r"(\d{2,5})\s*(?:元|块|块钱)?", feedback)
    if m:
        dims["budget"] = m.group(1)
    elif any(k in feedback for k in ("便宜", "低价", "省", "预算低", "降档")):
        dims["budget"] = "120"
    elif any(k in feedback for k in ("高档", "贵一点", "升级", "好一点", "加预算")):
        dims["budget"] = "500"
    # 风格
    for kw, val in _STYLE_KW.items():
        if kw in feedback:
            dims["style"] = val
            break
    # 色系
    for kw, val in _COLOR_KW.items():
        if kw in feedback:
            dims["color"] = val
            break
    # 情感/氛围
    for kw, val in _MOOD_KW.items():
        if kw in feedback:
            dims["mood"] = val
            break
    # 移除花材：不要X / 去掉X / 别用X / 换掉X
    for name in _ALL_FLOWER_NAMES:
        if any(seg in feedback for seg in (f"不要{name}", f"去掉{name}", f"别用{name}", f"换掉{name}", f"去掉{name}花")):
            exclude.add(name)
    return {"dims": dims, "exclude": exclude}


_RELATIONSHIP_MAP = {
    "母亲": "亲子", "恋人": "情侣", "朋友": "朋友",
    "自己": "自用", "长辈": "长辈/同事", "宝宝": "亲子",
}


def _extract_budget(text: str) -> tuple[str | None, float | None, float | None, float | None]:
    """从文本抽预算：返回 (口语锚点, 精确金额, 区间下界, 区间上界)。

    精确金额与旧 _extract 的 dims['budget'] 保持一致（如「两三百」→ 250），
    区间按 ±20% 推导，供检索时做软过滤。
    """
    anchor: str | None = None
    for oral, num in _BUDGET_ORAL.items():
        if oral in text:
            text = text.replace(oral, f" {num} ")
            anchor = oral
            break
    m = re.search(r"(\d{2,5})\s*(?:元|块|块钱)?", text)
    if not m:
        return anchor, None, None, None
    num = float(m.group(1))
    return anchor, num, round(num * 0.8), round(num * 1.2)


def extract_requirement(text: str) -> FlowerRequirement:
    """共享需求抽取器：自然语言 → 结构化 FlowerRequirement。

    DIY 设计、方案检索、店铺检索共用同一套维度识别，避免散落多处。
    """
    req = FlowerRequirement(raw=text)
    # 取「最长命中」避免短词遮蔽更具体别名（如「桃红」优先于「红」）
    for table, key in (
        (_RECIPIENT_KW, "recipient"),
        (_OCCASION_KW, "occasion"),
        (_STYLE_KW, "style"),
        (_COLOR_KW, "color"),
        (_MOOD_KW, "mood"),
    ):
        attr = "colors" if key == "color" else key
        if getattr(req, attr):
            continue
        best_kw = None
        for kw in table:
            if kw in text and (best_kw is None or len(kw) > len(best_kw)):
                best_kw = kw
        if best_kw is not None:
            if key == "color":
                req.colors = [table[best_kw]]
            else:
                setattr(req, key, table[best_kw])
    # 场景 / 节日：精确优先（如「母亲节」优先于泛化「节日」）
    for kw, sid in _SCENE_MAP.items():
        if kw in text:
            req.scene = sid
            break
    anchor, exact, bmin, bmax = _extract_budget(text)
    req.budget_anchor = anchor
    req.budget_num = exact
    req.budget_min = bmin
    req.budget_max = bmax
    if req.recipient:
        req.relationship = _RELATIONSHIP_MAP.get(req.recipient)
    return req


def _extract(text: str) -> dict[str, str]:
    """从自然语言需求中抽取维度（兼容旧形态，供 DIY 设计管线 / _extract_dims 测试）。"""
    return extract_requirement(text).to_legacy_dict()


def _resolve_flowers(
    dims: dict[str, str],
    style: dict,
    budget_tier: dict,
    prefer_flowers: list[str] | None = None,
    exclude_flowers: set[str] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """根据维度 + 风格 + 预算，从知识库挑主花/配材/叶材。

    Args:
        prefer_flowers: 场景模板指定的优先主花（最高权重）。
        exclude_flowers: 用户反馈中要求移除的花材名集合（迭代时用到）。
    """
    prefer_flowers = prefer_flowers or []
    exclude_flowers = exclude_flowers or set()
    # 1) 对象 / 场合 → 搭配规则推荐花材名（分层：对象信号强于场合）
    rec_recipient: list[str] = []
    rec_occasion: list[str] = []
    all_fl = query_knowledge("flower", "")["results"]
    if dims.get("recipient"):
        for p in query_knowledge("pairing", dims["recipient"])["results"]:
            for f in all_fl:
                if f["name"] in p.get("recommendation", ""):
                    rec_recipient.append(f["name"])
    if dims.get("occasion"):
        for p in query_knowledge("pairing", dims["occasion"])["results"]:
            for f in all_fl:
                if f["name"] in p.get("recommendation", ""):
                    rec_occasion.append(f["name"])
    # 2) 色系筛选
    color = dims.get("color")
    # 3) 风格典型花材
    style_flowers = style.get("typical_flowers", [])
    # 4) 预算建议花材
    budget_flowers = budget_tier.get("suggested_flowers", [])

    all_flowers = {f["name"]: f for f in query_knowledge("flower", "")["results"]}
    # 候选主花：场景优先 + 对象推荐 + 场合推荐 + 风格典型 + 预算建议 的并集
    candidates = []
    seen = set()
    for name in list(prefer_flowers) + list(rec_recipient) + list(rec_occasion) + list(style_flowers) + list(budget_flowers):
        f = all_flowers.get(name)
        if not f or name in seen or name in exclude_flowers:
            continue
        seen.add(name)
        candidates.append(f)

    # 按色系过滤（若有）
    if color and color != "亮" and color != "多彩混合":
        colored = [f for f in candidates if color in f.get("colors", [])]
        if colored:
            candidates = colored

    # 兜底：没有任何候选就用风格典型花材（仍排除被要求移除的）
    if not candidates:
        candidates = [all_flowers[n] for n in style_flowers if n in all_flowers and n not in exclude_flowers]

    main_candidates = [f for f in candidates if f.get("category") == "主花"] or candidates
    # 主花优先级：场景优先(-1) > 对象推荐(0) > 风格典型(1) > 场合推荐(2) > 其他(3)
    style_set = set(style.get("typical_flowers", []))
    rec_rec_set = set(rec_recipient)
    rec_occ_set = set(rec_occasion)
    prefer_set = set(prefer_flowers)
    scored = []
    for idx, f in enumerate(main_candidates):
        if f["name"] in prefer_set:
            w = -1
        elif f["name"] in rec_rec_set:
            w = 0
        elif f["name"] in style_set:
            w = 1
        elif f["name"] in rec_occ_set:
            w = 2
        else:
            w = 3
        scored.append((w, idx, f))
    scored.sort(key=lambda x: (x[0], x[1]))
    main = [f for _, _, f in scored][:2] or candidates[:1]
    fillers = [f for f in candidates if f.get("category") == "填充" and f["name"] not in exclude_flowers][:1] or [
        all_flowers.get("满天星")
    ]
    foliage = [f for f in candidates if f.get("category") == "叶材" and f["name"] not in exclude_flowers][:1] or [
        all_flowers.get("尤加利")
    ]
    return (
        [f for f in main if f],
        [f for f in fillers if f],
        [f for f in foliage if f],
    )


# --------------------------------------------------------------------------- #
# 方案落地化增强：插花步骤 / 养护 / 贺卡文案 / 预算明细（纯模板，不依赖真实数据）
# --------------------------------------------------------------------------- #

#: 花材单价粗略基准（元/支），用于预算明细估算；真实接入时可由知识库价格档替换
_PRICE_UNIT = {"低": 12, "中": 28, "高": 60}
#: 各预算档主花支数基准（与 budget.json 的 main_count 对齐）
_TIER_MAIN_STEMS = {"T1": 6, "T2": 10, "T3": 16}


def _build_diy_steps(
    main: list[dict], fillers: list[dict], foliage: list[dict],
    color_scheme: list[str], packaging: dict | None,
) -> list[str]:
    """生成可照做的分步插花指引（基于本方案实际花材/包装）。"""
    m = [f["name"] for f in main if f]
    f1 = [f["name"] for f in fillers if f]
    f2 = [f["name"] for f in foliage if f]
    pk_name = packaging["name"] if packaging else "花束"
    pk_desc = packaging.get("description", "") if packaging else ""
    colors = "/".join(color_scheme) or "自然色系"
    return [
        f"1. 备材处理：取主花 {'、'.join(m) or '玫瑰'}，斜剪根部 45° 并剥去下半部叶；"
        f"若有玫瑰需去刺，百合建议摘除雄蕊防染色。",
        "2. 定高构图：以主花为视觉重心，整体高度约为花束/花器的 1.5 倍；先插主花确定骨架与朝向。",
        f"3. 填充层次：加入配材 {'、'.join(f1) or '满天星'} 填补空隙，"
        f"叶材 {'、'.join(f2) or '尤加利'} 勾边制造空气感，形成前低后高。",
        f"4. 配色比例：按色系 {colors} 控制主花:配材 ≈ 7:3，避免头重脚轻或色彩打架。",
        f"5. 包装收尾：用「{pk_name}」（{pk_desc}）螺旋扎制并整理外层叶材外扩，丝带/韩素纸收尾。",
        "6. 醒花养护：完成后深水醒花 2-4 小时再摆放，详见「养护建议」。",
    ]


def _build_care_tips(main: list[dict]) -> str:
    """生成养护建议（通用 + 针对主花的特例提示）。"""
    names = {f["name"] for f in main if f}
    tips = [
        "收到后斜剪根部 45°，深水醒花 2-4 小时再入瓶；",
        "每日换水并清洗花茎切口，花瓶水位保持 2/3；",
        "远离空调出风口与阳光直射，可延长花期 3-7 天。",
    ]
    if "百合" in names:
        tips.append("百合：摘除雄蕊避免花粉染色衣物，花蕊变褐及时剪去。")
    if "绣球" in names:
        tips.append("绣球：喜水，可整支浸入水中 1-2 小时急救脱水；花头可轻柔喷水。")
    if "向日葵" in names:
        tips.append("向日葵：花头重，建议浅水位并支托花茎，防止垂头。")
    return "".join(tips)


def _build_card_message(
    recipient: str, occasion_phrase: str, style_label: str, tone: str, short_meaning: str
) -> str:
    """生成可复用的贺卡寄语文案（场景基调优先，避免长串花语堆砌）。"""
    base = f"致{recipient}：{occasion_phrase}之际，送上这束{style_label}花束，"
    if tone:
        return base + f"愿它替我传递「{tone}」。"
    return base + f"愿它替我传递{short_meaning}。"


def _build_budget_breakdown(
    main: list[dict], fillers: list[dict], foliage: list[dict],
    packaging: dict | None, tier: dict, budget_num: int | None,
) -> dict:
    """按花材档位粗略估算预算分项（标注为估算，实际以门店为准）。"""
    known = {x["name"]: x for x in (list(main) + list(fillers) + list(foliage)) if x and x.get("name")}

    def unit(name: str) -> int:
        return _PRICE_UNIT.get(known.get(name, {}).get("price_tier", "中"), 28)

    main_n = _TIER_MAIN_STEMS.get(tier.get("tier", "T2"), 10)
    avg_main_unit = (sum(unit(m["name"]) for m in main) / max(len(main), 1)) if main else 28
    main_cost = main_n * avg_main_unit
    filler_cost = sum(unit(f["name"]) for f in fillers) or 18
    foliage_cost = sum(unit(f["name"]) for f in foliage) or 14
    pkg_cost = 35 if (packaging and packaging.get("id") == "PK_BOX") else 8
    total = round(main_cost + filler_cost + foliage_cost + pkg_cost)
    items = [
        {"item": "主花", "detail": f"{main_n} 支（{'、'.join(m['name'] for m in main) or '玫瑰'}）", "amount": round(main_cost)},
        {"item": "配材", "detail": "、".join(f["name"] for f in fillers) or "满天星", "amount": round(filler_cost)},
        {"item": "叶材", "detail": "、".join(f["name"] for f in foliage) or "尤加利", "amount": round(foliage_cost)},
        {"item": "包装/人工", "detail": packaging["name"] if packaging else "花束", "amount": pkg_cost},
    ]
    return {
        "total_estimate": total,
        "currency": "CNY",
        "items": items,
        "note": "以上为按花材档位做的粗略估算，实际价格以门店/供应商为准。",
    }


def _build_plan(
    dims: dict[str, str],
    version: int = 1,
    parent_id: str | None = None,
    exclude_flowers: set[str] | None = None,
) -> dict:
    """设计核心：基于维度组装一份结构化 DIY 方案（场景感知 + 细分风格）。

    Args:
        dims: 抽取出的维度（recipient/occasion/style/substyle/scene/color/mood/budget/_keep_main）。
        version: 方案版本号，迭代时递增。
        parent_id: 上一版方案 id，便于追溯。
        exclude_flowers: 反馈中要求移除的花材名集合。
    """
    scene = get_by_id("scene", dims.get("scene")) if dims.get("scene") else None

    # 风格解析：显式风格 > 场景推荐 > 默认韩式
    style_id = dims.get("style") or (scene.get("recommended_style") if scene else None) or "S_KOREAN"
    # 子风格：显式 > 场景推荐 > 由氛围推导
    substyle_id = dims.get("substyle")
    if not substyle_id and scene:
        substyle_id = scene.get("recommended_substyle")
    if not substyle_id:
        substyle_id = _infer_substyle(style_id, dims)
    resolved, parent = (None, None)
    if substyle_id:
        resolved, parent = _get_style_full(substyle_id)
    if not resolved:
        resolved, parent = _get_style_full(style_id)
    style = resolved or get_by_id("style", "S_KOREAN")
    parent_style = parent or style
    style_label = style.get("name", parent_style.get("name", "韩式"))

    # 预算档：显式预算 > 场景锚点 > 默认「精致/送礼」
    budget_num = int(dims["budget"]) if dims.get("budget") else None
    tier = _get_tier(budget_num, scene.get("budget_anchor") if scene else None)

    # 花材：场景偏好花材最高优先级（无场景时沿用上一版主花保持连续）
    prefer = list(scene.get("main_flower_preference", [])) if scene else []
    keep_main = [n for n in dims.get("_keep_main", "").split(",") if n] if dims.get("_keep_main") else []
    main, fillers, foliage = _resolve_flowers(
        dims, style, tier, prefer_flowers=(prefer or keep_main), exclude_flowers=exclude_flowers
    )
    main_flowers = [{"name": f["name"], "role": "主花", "flower_language": f.get("flower_language", [])} for f in main]
    filler_flowers = [{"name": f["name"], "role": "填充"} for f in fillers]
    foliage_flowers = [{"name": f["name"], "role": "叶材"} for f in foliage]

    # 包装：高档预算 / 重要场景 → 礼盒
    packaging = get_by_id("packaging", "PK_BOUQUET")
    important = dims.get("occasion") in ("告白", "生日") or (scene and scene["id"] in ("SC_WEDDING", "SC_ANNIVERSARY", "SC_NEWYEAR"))
    if "高档" in tier["label"] or important:
        packaging = get_by_id("packaging", "PK_BOX") or packaging

    # 色彩方案：场景色调整合 → 风格调色板 → 用户显式色系
    color_scheme = list(style.get("color_palette", [])) or list(parent_style.get("color_palette", []))
    if scene:
        tone = [c for c in scene.get("color_tone", []) if c not in color_scheme]
        color_scheme = tone + color_scheme
    if dims.get("color") and dims["color"] not in ("亮", "多彩混合") and dims["color"] not in color_scheme:
        color_scheme = [dims["color"]] + color_scheme

    # 寓意文案
    meanings = []
    for f in main:
        meanings.extend(f.get("flower_language", []))
    meaning = "、".join(dict.fromkeys(meanings)) or "美好心意"
    if scene:
        meaning = f"{meaning}（{scene.get('meaning_tone', '')}）"
    short_meaning = "、".join(list(dict.fromkeys(meanings))[:2]) or "美好心意"
    tone = scene.get("meaning_tone", "") if scene else ""

    # 预算估算文案
    lo, hi = tier["range"]
    est = f"{lo}-{hi} 元" if budget_num is None else f"约 {budget_num} 元（{tier['label']}档）"

    # 生图 prompt
    effect_prompt = (
        f"{style_label}风格花束，"
        f"主花为{ '、'.join(f['name'] for f in main) or '玫瑰' }，"
        f"搭配{ '、'.join(f['name'] for f in fillers) or '满天星' }与{ '、'.join(f['name'] for f in foliage) or '尤加利' }，"
        f"色调{'/'.join(color_scheme)}，{ packaging['name'] if packaging else '花束' }包装，"
        f"背景干净柔和，摄影级静物，高级感"
    )

    occ_label = dims.get("occasion") or (scene["name"] if scene else "定制")
    notes = []
    if scene:
        notes.append(f"场景模板：{scene['name']} —— {scene.get('notes', '')}")
    notes.append(f"风格：{style_label}（{style.get('description', '')}）")
    notes.append(f"预算档：{tier['label']}（{tier['config']}）")
    if exclude_flowers:
        notes.append(f"已按反馈移除：{ '、'.join(sorted(exclude_flowers)) }")

    plan = {
        "plan_id": "DIY_" + uuid.uuid4().hex[:6],
        "version": version,
        "parent_id": parent_id,
        "name": f"{style_label}·{occ_label}花束",
        "diy": True,
        "style": style_label,
        "style_id": style_id,
        "substyle_id": substyle_id,
        "substyle": style.get("name") if (substyle_id and resolved is not parent) else None,
        "recipient": dims.get("recipient", "通用"),
        "occasion": occ_label,
        "scene_id": scene["id"] if scene else None,
        "scene": scene["name"] if scene else None,
        "budget_num": budget_num,
        "budget_tier": tier["label"],
        "design": {
            "main_flowers": main_flowers,
            "fillers": filler_flowers,
            "foliage": foliage_flowers,
            "color_scheme": color_scheme,
            "packaging": packaging["name"] if packaging else "花束",
            "meaning": meaning,
            "notes": notes,
        },
        "estimated_price": est,
        "effect_prompt": effect_prompt,
        "desc": (
            f"为你设计了一份{style_label}{occ_label}花束："
            f"以{ '、'.join(f['name'] for f in main) or '玫瑰' }为主花，"
            f"{ '、'.join(f['name'] for f in fillers) or '满天星' }与"
            f"{ '、'.join(f['name'] for f in foliage) or '尤加利' }点缀，"
            f"色调{'/'.join(color_scheme)}，寓意{meaning}。预算{est}。"
        ),
        # —— 落地化增强（纯模板，不依赖真实数据）——
        "diy_steps": _build_diy_steps(main, fillers, foliage, color_scheme, packaging),
        "care_tips": _build_care_tips(main),
        "card_message": _build_card_message(
            dims.get("recipient", "朋友"),
            scene["name"] if scene else occ_label,
            style_label,
            tone,
            short_meaning,
        ),
        "budget_breakdown": _build_budget_breakdown(main, fillers, foliage, packaging, tier, budget_num),
    }
    return plan


def design_diy_plan(requirements: str) -> dict:
    """设计一份结构化 DIY 花艺方案。

    链路：抽维度 → 查知识库（场景/风格/预算/搭配/花材/包装）→ 组装方案 → 生成生图 prompt。
    返回可供 UI 渲染、生图与下单承接的结构化 dict。
    """
    dims = _extract(requirements)
    return _build_plan(dims)


@register_tool(
    name="revise_diy_plan",
    description=(
        "基于已有方案 + 自然语言反馈，调整出下一版花艺方案：可调预算（便宜点/高档）、改风格、改色系、"
        "移除指定花材（不要X/去掉X）。返回带 version 与 parent_id 的可追溯新方案。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "plan": {"type": "string", "description": "上一版方案 JSON 或含 JSON 的文本"},
            "feedback": {"type": "string", "description": "用户反馈，如 便宜点/换成红玫瑰/不要康乃馨/颜色再大胆"},
        },
        "required": ["plan", "feedback"],
    },
    inject_context=True,
    tags=["diy"],
)
def revise_diy_plan(plan: str, feedback: str, _context: dict | None = None) -> str:
    """基于已有方案 + 自然语言反馈，生成一版调整方案（version 递增），并写入会话。"""
    original = _parse_plan(plan)
    dims = _dims_from_plan(original)
    fb = _extract_feedback(feedback)
    dims.update(fb["dims"])
    new_plan = _build_plan(
        dims,
        version=original.get("version", 1) + 1,
        parent_id=original.get("plan_id"),
        exclude_flowers=fb["exclude"],
    )
    _store_diy_plan(new_plan, _context)
    return json.dumps(new_plan, ensure_ascii=False)


@register_tool(
    name="generate_effect_image",
    description=(
        "为 DIY 方案提交 AI 生图任务。若传入 latest_diy 则自动使用最近一次设计的方案生成精确 prompt"
        "（花材/色彩/形态/包装一致）；也可直接传入自定义描述。立即返回 task_id，客户端通过 GET /tasks/{task_id} 轮询。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "方案描述或方案 ID；latest/latest_diy 表示使用最近设计的方案",
            }
        },
        "required": ["plan"],
    },
    tags=["image"],
    inject_context=True,
)
def generate_effect_image(plan: str = "latest_diy", _context: dict | None = None) -> str:
    """提交生图异步任务，返回 task_id。基于最近设计方案生成精确 prompt。

    生图安全闸门（后端强约束，不依赖模型自觉）—— 融合自 111 的 session_flags 守卫：
    - 仅在 IMAGE_GEN（生图确认）阶段可调用；
    - 必须已获用户明确同意（image_confirmed 标记，由 agent 识别肯定意图写入）；
    - 同一轮确认只允许提交一次（image_submitted 标记）。
    """
    ctx = _context or {}
    sid = ctx.get("session_id", "")
    uid = ctx.get("user_id", "")
    if sid:
        from engine.state import SessionStage

        stage = memory.get_stage(sid)
        if stage != SessionStage.IMAGE_GEN.value:
            return json.dumps(
                {"error": f"当前业务阶段（{stage or '无会话'}）不可直接生成效果图，请先征求用户是否生成效果图"},
                ensure_ascii=False,
            )
        if memory.get_session_flag(uid, sid, "image_confirmed") != "1":
            return json.dumps(
                {"error": "生成效果图前必须先获得用户明确同意（请先询问用户）"},
                ensure_ascii=False,
            )
        if memory.get_session_flag(uid, sid, "image_submitted") == "1":
            return json.dumps(
                {"error": "本轮确认已提交过效果图任务，如需重新生成请再次征求用户确认"},
                ensure_ascii=False,
            )

    # 生图可控化：有结构化方案时，用设计产出的 effect_prompt，而非盲填原文。
    # 方案从当前会话读取（latest_diy_plan），不再使用进程级全局变量（并发安全）。
    if plan in ("latest", "latest_diy", "", None):
        diy = memory.get_session_json(uid, sid, "latest_diy_plan") if sid else None
        if diy:
            prompt = diy.get("effect_prompt") or diy.get("desc", "")
        else:
            prompt = plan
    else:
        prompt = plan
    task_id = tasks.create_image_task(prompt)
    if sid:
        memory.set_session_flag(uid, sid, "image_submitted", "1")
    return json.dumps(
        {"task_id": task_id, "status": "submitted", "poll": f"/tasks/{task_id}"},
        ensure_ascii=False,
    )


@register_tool(
    name="respond_to_user",
    description=(
        "当你准备好向用户输出本轮最终回复时，必须调用该工具结束本轮对话。"
        "携带：reply（自然语言回复）、ui（UI 动作类型）、data（按 ui 类型填充）、"
        "stage（协商后的下一业务阶段）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "reply": {"type": "string", "description": "给用户的自然语言回复"},
            "ui": {
                "type": "string",
                "enum": [e.value for e in UIType],
                "description": "小程序渲染的 UI 动作类型",
            },
            "data": {"type": "object", "description": "按 ui 类型约定的结构化数据"},
            "stage": {
                "type": "string",
                "description": "下一业务阶段，如 analyze/select_mode/view_plan/diy_design/image_gen/shop_recommend/done",
            },
        },
        "required": ["reply", "ui", "data", "stage"],
    },
    tags=["meta"],
)
def respond_to_user(
    reply: str = "",
    ui: str = "text",
    data: dict | None = None,
    stage: str = "analyze",
) -> str:
    """终结工具：模型以此结束本轮，参数由 agent 提取并校验后返回前端。"""
    return json.dumps(
        {"reply": reply, "ui": ui, "data": data or {}, "stage": stage},
        ensure_ascii=False,
    )


@register_tool(
    name="search_shops",
    description=(
        "按距离、价格、服务评价综合排序推荐店铺；"
        "会结合用户位置与预算（来自结构化需求）做排序与过滤。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "方案 ID；或 latest/latest_diy 表示使用最近方案",
            }
        },
        "required": ["plan"],
    },
    inject_context=True,
    tags=["shop"],
)
def search_shops(plan: str = "latest", _context: dict | None = None) -> str:
    """推荐店铺（结合用户位置与结构化需求排序）。

    方案引用经 _resolve_session_plan 解析到「会话最近引用方案」（不再取全局首方案），
    解析结果写回 selected_plan，保证后续 create_order(plan_id="latest") 下单到同一方案。
    """
    req = _requirement_from_context(_context)
    location = None
    if _context:
        location = _context.get("location") or (req.location if req else None)
    plan_obj = _resolve_session_plan(plan, _context)
    sid = (_context or {}).get("session_id", "")
    uid = (_context or {}).get("user_id", "")
    if plan_obj and sid:
        memory.set_session_json(uid, sid, "selected_plan", plan_obj)
    shops = repo.list_shops(plan_obj, location, requirement=req)
    return json.dumps(shops, ensure_ascii=False)


@register_tool(
    name="save_memory",
    description="把用户明确表达的偏好写入长期记忆（如预算、送花对象、偏好色系）。",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "偏好键，如 budget / recipient / color"},
            "value": {"type": "string", "description": "偏好值"},
        },
        "required": ["key", "value"],
    },
    inject_context=True,
    tags=["memory"],
)
def save_memory(key: str, value: str, _context: dict | None = None) -> str:
    """写入用户长期偏好。"""
    user_id = (_context or {}).get("user_id", "anonymous")
    memory.set_long_term(user_id, key, value)
    return json.dumps({"saved": {key: value}}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# 注册表消费接口（供 agent 使用）
# --------------------------------------------------------------------------- #


def get_tool_specs() -> list[ToolSpec]:
    return list(TOOL_REGISTRY.values())


def to_openai_tools() -> list[dict[str, Any]]:
    """生成 OpenAI function-calling 的 tools 定义。"""
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            },
        }
        for s in TOOL_REGISTRY.values()
    ]


def generate_tool_manual() -> str:
    """生成中文工具说明书，注入 system prompt。"""
    lines = ["你当前可以使用的工具（需要时以 JSON 或 function call 形式调用）："]
    for s in TOOL_REGISTRY.values():
        params = ", ".join(
            f"{k}: {v.get('type', 'any')}" for k, v in s.parameters.get("properties", {}).items()
        )
        lines.append(f"- {s.name}({params})：{s.description}")
    return "\n".join(lines)


def execute_tool(name: str, arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> tuple[str, str]:
    """执行工具，返回 (结果字符串, 状态 ok|error)。"""
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        return f"未知工具: {name}", "error"
    try:
        kwargs = dict(arguments or {})
        if spec.inject_context:
            kwargs["_context"] = context
        result = spec.func(**kwargs)
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False)
        return result, "ok"
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tools] 执行 %s 失败", name)
        return f"工具执行失败: {exc}", "error"
