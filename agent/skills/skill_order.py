"""skills/skill_order.py —— 下单技能（独立自包含模块）。

作为「技能」而非普通工具注册：自描述（docstring + schema）+ 自注册（@register_tool）。
职责边界清晰：
- 组装订单数据（从仓库取方案/店铺，计算金额）
- 写入 orders 表
- 返回 pay_jump 参数（小程序的 /pages/order/confirm 跳转信息）
**不直接调用微信支付**——支付由小程序承接，后端只负责把订单和跳转参数交给前端。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime

from agent.tools import _resolve_session_plan, register_tool
from backend.config import settings
from backend.storage.commerce import apply_best_coupon
from backend.storage.db import get_conn, transaction
from backend.storage.repository import repo

logger = logging.getLogger("skills.order")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _plan_price(plan: dict) -> float:
    """方案金额：预设方案取 price；DIY 方案用 budget 兜底；兜底查 DB。"""
    pid = plan.get("plan_id", "")
    # 1. 直接取 price（shop 商品 / 预设方案），要求 > 0
    if isinstance(plan.get("price"), (int, float)) and plan["price"] > 0:
        return float(plan["price"])
    # 2. DIY 方案用 budget
    if isinstance(plan.get("budget"), (int, float)) and plan["budget"] > 0:
        return float(plan["budget"])
    # 3. 从 budget_breakdown 取估算价
    breakdown = plan.get("budget_breakdown") or {}
    if isinstance(breakdown.get("total_estimate"), (int, float)):
        return float(breakdown["total_estimate"])
    # 4. 从 estimated_price 字符串解析
    m = re.search(r"(\d+(?:\.\d+)?)", str(plan.get("estimated_price", "")))
    if m:
        return float(m.group(1))
    # 5. 兜底：从 DB 查 plans 表
    if pid:
        try:
            row = get_conn().execute("SELECT price FROM plans WHERE id=?", (pid,)).fetchone()
            if row and isinstance(row["price"], (int, float)) and row["price"] > 0:
                return float(row["price"])
        except Exception:  # noqa: BLE001
            pass
    return 0.0


def _extract_flower_names(plan: dict) -> list[str]:
    """从 DIY 方案中提取花材名称列表（兼容 in-memory 和 DB 两种格式）。"""
    design = plan.get("design") or {}
    flowers_raw = plan.get("flowers") or []

    names: list[str] = []
    # in-memory 格式：design.main_flowers / fillers / foliage
    for key in ("main_flowers", "fillers", "foliage"):
        for f in design.get(key, []):
            name = f.get("name", "") if isinstance(f, dict) else str(f)
            if name and name not in names:
                names.append(name)
    # DB 格式：flowers 带 bucket 字段
    for f in flowers_raw:
        if isinstance(f, dict) and f.get("name") and f["name"] not in names:
            names.append(f["name"])
    return names


def _match_flowers_to_shop(flower_list: list[str], shop_id: str) -> dict:
    """将花材列表与店铺在售商品做匹配，返回匹配结果。

    匹配策略（优先级从高到低）：
    1. 商品名包含花材名（如 "单支粉玫瑰" 包含 "粉玫瑰"）
    2. 标签包含花材名（如 tags="粉玫瑰,单支" 包含 "粉玫瑰"）
    3. 花材名出现在标签列表的任一元素中
    4. 子串兜底：花材名的任一词根（≥2字）出现在商品名中（如 "蝴蝶兰" → "蝴蝶" 命中 "蝴蝶兰鲜切花"）
    """
    conn = get_conn()
    items = conn.execute(
        """SELECT p.id, p.name, p.price, p.tags, p.desc
           FROM plans p JOIN shop_plans sp ON p.id = sp.plan_id
           WHERE sp.shop_id=? AND sp.status='on'""",
        (shop_id,),
    ).fetchall()

    matched = []
    missing = []
    total_cost = 0.0

    for fl in flower_list:
        best = None
        for item in items:
            name = item["name"] or ""
            tags_raw = item["tags"] or ""
            # 解析 tags（可能是 JSON 数组字符串或逗号分隔）
            if tags_raw.startswith("["):
                try:
                    tags_list = json.loads(tags_raw)
                except json.JSONDecodeError:
                    tags_list = [t.strip().strip('"') for t in tags_raw.strip("[]").split(",")]
            else:
                tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]

            # 精确匹配：花材名必须完整出现在商品名或标签中
            if fl in name or fl in tags_raw or fl in tags_list:
                best = {
                    "plan_id": item["id"],
                    "name": name,
                    "price": item["price"],
                    "flower": fl,
                }
                break
        if not best:
            # 子串兜底：花材名拆成 ≥2 字词根，任一命中商品名即匹配
            # （如 "蝴蝶兰" → ["蝴蝶", "蝶兰", "蝴蝶兰"]，"尤加利叶" → ["尤加利", "加利叶", "尤加利叶"]）
            for item in items:
                name = item["name"] or ""
                candidates = {fl[i:i+2] for i in range(len(fl)-1)} | {fl[i:i+3] for i in range(max(0, len(fl)-2))}
                if any(c in name for c in candidates if len(c) >= 2):
                    best = {
                        "plan_id": item["id"],
                        "name": name,
                        "price": item["price"],
                        "flower": fl,
                    }
                    break
        if best:
            matched.append(best)
            total_cost += best["price"]
        else:
            missing.append(fl)

    return {
        "matched": matched,
        "missing": missing,
        "estimated_cost": round(total_cost, 2),
        "coverage": round(len(matched) / len(flower_list), 2) if flower_list else 0,
    }


def _build_detailed_items(plan: dict) -> list[dict]:
    """非 DIY 方案：返回单条方案项。"""
    pid = plan.get("plan_id", "")
    return [{"plan_id": pid, "name": plan.get("name", "花束"), "role": "方案", "price": _plan_price(plan), "unit_price": _plan_price(plan), "qty": 1}]


def _build_diy_order_items(plan: dict, shop_id: str) -> tuple[list[dict], float]:
    """DIY 方案：从 shop 单品匹配组装订单明细。

    返回 (items, total)：
    - items: 每条 = {plan_id, name, role, price, unit_price, qty, product_id}
    - total: 所有匹配商品实际价格之和
    """
    flower_names = _extract_flower_names(plan)
    if not flower_names:
        # 无花材信息，走方案估算价兜底
        return _build_detailed_items(plan), _plan_price(plan)

    match_result = _match_flowers_to_shop(flower_names, shop_id)
    matched = match_result["matched"]
    missing = match_result["missing"]

    items: list[dict] = []
    pid = plan.get("plan_id", "")

    # 已匹配的商品：用店铺实际价格
    for m in matched:
        items.append({
            "plan_id": pid,
            "name": m["name"],
            "role": m["flower"],
            "price": m["price"],
            "unit_price": m["price"],
            "qty": 1,
            "product_id": m["plan_id"],
        })

    # 缺少的花材：标价 0，提示店铺无此花材
    for fl in missing:
        items.append({
            "plan_id": pid,
            "name": f"{fl}（店铺暂无）",
            "role": fl,
            "price": 0,
            "unit_price": 0,
            "qty": 1,
        })

    total = match_result["estimated_cost"]
    # 兜底：匹配全失败（无任何商品命中）时，用方案估算价生成一条方案级明细，
    # 避免订单卡片显示空列表 + ¥0。
    if not items:
        items = _build_detailed_items(plan)
        total = _plan_price(plan)
    elif total <= 0:
        total = _plan_price(plan)
    return items, total


@register_tool(
    name="create_order",
    description="组装订单并生成小程序支付跳转参数（pay_jump）。不直接调用微信支付，支付由小程序承接。",
    parameters={
        "type": "object",
        "properties": {
            "shop_id": {"type": "string", "description": "店铺 ID，或 'first' 表示推荐列表第一家"},
            "plan_id": {"type": "string", "description": "方案 ID，或 'latest' 表示当前方案"},
            "plan_type": {"type": "string", "description": "existing | diy"},
        },
        "required": ["shop_id", "plan_id", "plan_type"],
    },
    inject_context=True,
    tags=["order"],
)
def create_order(
    shop_id: str, plan_id: str, plan_type: str, _context: dict | None = None
) -> str:
    """组装订单并写入 orders 表，返回 order_card + pay_jump 数据。

    DIY 方案：从 shop 单品匹配花材，用店铺实际价格计算总价。
    现有方案：直接使用方案价格。
    """
    user_id = (_context or {}).get("user_id", "anonymous")

    shop = repo.get_shop(shop_id) if shop_id != "first" else repo.list_shops(None, None)[0]
    plan = _resolve_session_plan(plan_id, _context)
    if not shop or not plan:
        return json.dumps({"error": "店铺或方案不存在"}, ensure_ascii=False)

    if plan.get("diy"):
        plan_type = "diy"

    order_id = "O_" + uuid.uuid4().hex[:10]

    # DIY 方案：从 shop 单品匹配组装；现有方案：直接用方案价格
    if plan_type == "diy":
        items, total = _build_diy_order_items(plan, shop["shop_id"])
    else:
        total = _plan_price(plan)
        items = _build_detailed_items(plan)

    with transaction() as c:
        c.execute(
            "INSERT INTO orders(order_id, user_id, plan_id, plan_type, shop_id, items, total_price, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                order_id,
                user_id,
                plan["plan_id"],
                plan_type,
                shop["shop_id"],
                json.dumps(items, ensure_ascii=False),
                total,
                _now(),
            ),
        )

    discount = apply_best_coupon(order_id, user_id, total)

    if plan_type == "diy":
        try:
            from backend.storage.diy import mark_diy_plan_ordered, save_as_template
            mark_diy_plan_ordered(plan["plan_id"])
            save_as_template(plan["plan_id"])
        except Exception:  # noqa: BLE001
            logger.warning("[skill_order] 标记 DIY 方案成交/沉淀模板失败", exc_info=True)

    pay_jump = {
        "order_id": order_id,
        "page_path": settings.pay_page_path,
        "params": {
            "order_id": order_id,
            "total_price": total,
            "discount": discount,
            "shop_id": shop["shop_id"],
        },
    }
    logger.info("[skill_order] 订单 %s 已创建 user=%s shop=%s total=%.2f discount=%.2f", order_id, user_id, shop["shop_id"], total, discount)

    return json.dumps(
        {
            "order_id": order_id,
            "plan_name": plan.get("name", ""),
            "items": items,
            "total_price": total,
            "discount": discount,
            "plan_type": plan_type,
            "pay_jump": pay_jump,
            "effect_image_url": plan.get("effect_image_url") or plan.get("result_url") or "",
        },
        ensure_ascii=False,
    )
