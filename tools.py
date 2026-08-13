"""工具注册表：所有工具（含技能）统一注册、统一生成说明书。

- TOOL_REGISTRY: name -> {"description", "parameters"(JSON Schema), "func"}
- tool_descriptions(): 生成 OpenAI function calling 格式（tools 参数）
- tool_body_text(): 生成文本说明书（注入系统提示词，mock 等非 function-calling 场景兜底）
- 工具函数通过 runtime（contextvars）访问请求上下文与数据层
"""
import json
import logging
from typing import Callable, Dict, List

from runtime import get_runtime
from engine.state import SessionStage

logger = logging.getLogger(__name__)

TOOL_REGISTRY: Dict[str, dict] = {}


def register_tool(name: str, description: str, parameters: dict, func: Callable) -> None:
    """注册工具：名称为全局唯一键。"""
    if name in TOOL_REGISTRY:
        logger.warning("工具重复注册，将被覆盖: %s", name)
    TOOL_REGISTRY[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "func": func,
    }


def tool_descriptions() -> List[dict]:
    """生成 OpenAI function calling 的 tools 参数（按注册序）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOL_REGISTRY.values()
    ]


def tool_body_text() -> str:
    """生成供系统提示词使用的纯文本工具说明书（JSON Schema 说明）。"""
    lines = ["可用工具如下（参数为 JSON Schema 形式）："]
    for name, t in TOOL_REGISTRY.items():
        lines.append(f"- {name}: {t['description']}，参数: {json.dumps(t['parameters'], ensure_ascii=False)}")
    return "\n".join(lines)


def execute_tool(name: str, arguments: dict) -> str:
    """执行工具并返回 JSON 字符串结果；异常不抛出，以结构化错误返回。"""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return json.dumps({"error": f"工具不存在: {name}"}, ensure_ascii=False)
    try:
        result = spec["func"](**arguments)
        return json.dumps(result, ensure_ascii=False)
    except TypeError as exc:
        logger.warning("工具参数错误 %s: %s", name, exc)
        return json.dumps({"error": f"参数不正确: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("工具执行失败 %s", name)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


# ======================================================================
# 内建工具：via runtime 注入存储 / 数据层
# ======================================================================
def search_plans(keyword: str = "") -> list:
    """按关键词检索商家预设方案（含效果图 URL、商家名、价格等）。"""
    rt = get_runtime()
    plans = rt.repository.search_plans(keyword)
    result = []
    for p in plans:
        shop = rt.repository.get_shop(p.merchant_id)
        d = {
            "id": p.id, "name": p.name, "price": p.price, "desc": p.desc,
            "effect_image_url": p.effect_image_url, "merchant_id": p.merchant_id,
        }
        d["merchant_name"] = shop.name if shop else ""
        result.append(d)
    return result


def get_plan_detail(plan_id: str) -> dict:
    """获取单个商家方案详情。"""
    rt = get_runtime()
    p = rt.repository.get_plan(plan_id)
    if p is None:
        return {"error": f"方案不存在: {plan_id}"}
    return {
        "id": p.id, "name": p.name, "price": p.price, "desc": p.desc,
        "effect_image_url": p.effect_image_url, "merchant_id": p.merchant_id,
        "tags": p.tags,
    }


def generate_diy_plan(requirements: str = "") -> dict:
    """根据用户具体需求生成一版 DIY 花束定制方案。"""
    rt = get_runtime()
    return rt.repository.generate_diy_plan(requirements)


def generate_effect_image(plan_text: str = "") -> dict:
    """为方案提交 AI 效果图生成任务（异步），返回 task_id，客户端轮询 /tasks/{id}。

    关卡守卫（后端强约束，不依赖模型自觉）：
    - 仅在 IMAGE_GEN（生图确认）阶段可调用；
    - 必须已获得用户明确同意（image_confirmed 标记，由 agent 识别肯定意图写入）；
    - 同一轮确认只允许提交一次（image_submitted 标记）。
    """
    rt = get_runtime()
    user_id = rt.user_id.get()
    session = rt.memory.latest_session(user_id)
    session_id = session["session_id"] if session else ""
    stage = session["stage"] if session else ""

    if stage != SessionStage.IMAGE_GEN.value:
        return {"error": f"当前业务阶段（{stage or '无会话'}）不可直接生成效果图，"
                         "请先征求用户是否生成效果图"}
    if rt.memory.get_session_flag(user_id, session_id, "image_confirmed") != "1":
        return {"error": "生成效果图前必须先获得用户明确同意（请先询问用户）"}
    if rt.memory.get_session_flag(user_id, session_id, "image_submitted") == "1":
        return {"error": "本轮确认已提交过效果图任务，如需重新生成请再次征求用户确认"}

    task_id = rt.tasks.submit_image_task(user_id, plan_text)
    rt.memory.set_session_flag(user_id, session_id, "image_submitted", "1")
    return {"task_id": task_id, "status": "pending", "poll_url": f"/tasks/{task_id}"}


def search_shops(plan_type: str = "", requirements: str = "") -> list:
    """按距离、价格、服务评价推荐合适店铺（数据来自接入商家）。"""
    rt = get_runtime()
    shops = rt.repository.list_shops()
    location = rt.location.get() or ""
    return [
        {
            "shop_id": s.id, "name": s.name, "address": s.address,
            "distance_km": s.distance_km, "price_range": s.price_range,
            "rating": s.rating,
        }
        for s in shops
    ]


def save_memory(key: str, value: str) -> dict:
    """把明确的用户偏好写入长期记忆（预算、送花对象、偏好色系等）。"""
    rt = get_runtime()
    rt.memory.save_memory(rt.user_id.get(), key, value)
    return {"saved": key, "value": value}


# ---------- 工具注册（参数 schema 为 JSON Schema） ----------
register_tool(
    "search_plans",
    "按关键词搜索入驻商家预设的花卉方案，返回方案列表（含名称/价格/描述/效果图 URL/商家名）。关键词为空时返回全部。",
    {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "搜索关键词，如 母亲、玫瑰、向日葵"}},
        "required": [],
    },
    search_plans,
)

register_tool(
    "get_plan_detail",
    "获取某个商家预设方案（plan_id）的完整详情。",
    {
        "type": "object",
        "properties": {"plan_id": {"type": "string", "description": "方案 ID，来自 search_plans 结果"}},
        "required": ["plan_id"],
    },
    get_plan_detail,
)

register_tool(
    "generate_diy_plan",
    "根据用户具体需求（花材、用途、风格、预算等）生成一版 DIY 定制方案草稿。",
    {
        "type": "object",
        "properties": {"requirements": {"type": "string", "description": "用户原始需求描述"}},
        "required": ["requirements"],
    },
    generate_diy_plan,
)

register_tool(
    "generate_effect_image",
    "为方案提交 AI 效果图生成任务（异步），返回 task_id；客户端通过 GET /tasks/{task_id} 轮询生成结果。"
    "仅可在生图确认（IMAGE_GEN）阶段且用户明确同意后调用；未经确认调用会被拒绝。",
    {
        "type": "object",
        "properties": {"plan_text": {"type": "string", "description": "方案描述文本，用于生图"}},
        "required": ["plan_text"],
    },
    generate_effect_image,
)

register_tool(
    "search_shops",
    "为用户推荐符合订单需求的花店，综合距离、价格区间、服务评分排序后返回列表。",
    {
        "type": "object",
        "properties": {
            "plan_type": {"type": "string", "description": "方案类型 existing 或 diy", "enum": ["existing", "diy"]},
            "requirements": {"type": "string", "description": "订单相关描述（可选）"},
        },
        "required": [],
    },
    search_shops,
)

register_tool(
    "save_memory",
    "当用户明确表达偏好（预算、送花对象、颜色偏好、场合等）时调用，写入长期记忆，下次对话自动带入。",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "偏好条目名，如 budget、recipient、color"},
            "value": {"type": "string", "description": "偏好内容，如 200"},
        },
        "required": ["key", "value"],
    },
    save_memory,
)