"""storage/diy.py —— 用户 DIY 方案资产库（确认级持久化）。

只收录用户明确确认过的 DIY 方案：
- 确认（agent 识别「确认方案」意图）→ status=confirmed
- 成交（create_order 以 diy 落单）→ 升级 status=ordered 并累计 order_count

重复方案（同一用户 + 同一内容指纹）不重复落库，只补齐缺失的效果图。
个人复用（search_diy_plans）与平台学习（list_proven_plans）共用本模块。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from storage.db import get_conn

logger = logging.getLogger("storage.diy")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# 内容指纹：同一用户同一配方 = 重复（花材+角色+风格+对象+预算+包装）
# --------------------------------------------------------------------------- #
def _flower_keys(design: dict) -> list[str]:
    out: list[str] = []
    for bucket, key in (("m", "main_flowers"), ("f", "fillers"), ("g", "foliage")):
        for f in design.get(key) or []:
            name = f.get("name") if isinstance(f, dict) else f
            if name:
                out.append(f"{bucket}:{name}")
    return sorted(out)


def _fingerprint(plan: dict) -> str:
    """内容指纹（同一用户维度下判断方案是否重复）。"""
    d = plan.get("design") or plan
    payload = {
        "recipient": str(plan.get("recipient") or ""),
        "occasion": str(plan.get("occasion") or ""),
        "style": str(plan.get("style") or ""),
        "budget": plan.get("budget_num"),
        "flowers": _flower_keys(d),
        "packaging": str(d.get("packaging") or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _plan_image(plan: dict) -> str | None:
    return plan.get("result_url") or plan.get("effect_image_url")


def _flower_rows(design: dict) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket, key in (("主花", "main_flowers"), ("填充", "fillers"), ("叶材", "foliage")):
        for f in design.get(key) or []:
            if isinstance(f, dict):
                rows.append({"bucket": bucket, "name": f.get("name"), "ratio": f.get("ratio")})
            else:
                rows.append({"bucket": bucket, "name": f, "ratio": None})
    return rows


def save_diy_plan(plan: dict, user_id: str) -> dict[str, Any]:
    """落库一条已确认的 DIY 方案；重复（同用户同指纹）不重复写入。

    Returns: {"saved": bool, "duplicate": bool, "plan_id": str}
    """
    plan_id = str(plan.get("plan_id") or "") if plan else ""
    if not plan or not user_id:
        return {"saved": False, "duplicate": False, "plan_id": plan_id}
    d = plan.get("design") or plan
    fp = _fingerprint(plan)
    if not plan_id:
        plan_id = "DIY_" + uuid.uuid4().hex[:6]
    now = _now()
    conn = get_conn()
    with conn:
        row = conn.execute(
            "SELECT id, effect_image_url FROM diy_plans WHERE user_id=? AND fingerprint=?",
            (user_id, fp),
        ).fetchone()
        if row:
            # 重复方案不重写；旧记录缺效果图而新方案有则补齐（生图完成晚于确认）
            if not row["effect_image_url"]:
                img = _plan_image(plan)
                if img:
                    conn.execute(
                        "UPDATE diy_plans SET effect_image_url=?, confirmed_at=? WHERE id=?",
                        (img, now, row["id"]),
                    )
            return {"saved": False, "duplicate": True, "plan_id": row["id"]}
        conn.execute(
            "INSERT INTO diy_plans("
            "id, user_id, fingerprint, name, requirement, recipient, occasion, style, budget,"
            "color_scheme, flowers, packaging, meaning, diy_steps, care_tips, card_message,"
            "budget_breakdown, effect_image_url, status, order_count, created_at, confirmed_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                plan_id,
                user_id,
                fp,
                str(plan.get("name") or "未命名方案"),
                str(plan.get("requirement") or ""),
                str(plan.get("recipient") or ""),
                str(plan.get("occasion") or ""),
                str(plan.get("style") or ""),
                plan.get("budget_num"),
                json.dumps(d.get("color_scheme") or [], ensure_ascii=False),
                json.dumps(_flower_rows(d), ensure_ascii=False),
                str(d.get("packaging") or ""),
                str(d.get("meaning") or ""),
                json.dumps(plan.get("diy_steps") or [], ensure_ascii=False),
                str(plan.get("care_tips") or ""),
                str(plan.get("card_message") or ""),
                json.dumps(plan.get("budget_breakdown") or {}, ensure_ascii=False),
                _plan_image(plan),
                "confirmed",
                0,
                now,
                now,
            ),
        )
    logger.info("[diy] 方案已入库 id=%s user=%s", plan_id, user_id)
    return {"saved": True, "duplicate": False, "plan_id": plan_id}


def mark_diy_plan_ordered(plan_id: str) -> None:
    """DIY 方案成交（create_order 落单）后升级状态并累计成交数。"""
    if not plan_id:
        return
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "UPDATE diy_plans SET status='ordered', order_count=order_count+1 WHERE id=?",
            (plan_id,),
        )
        if cur.rowcount:
            logger.info("[diy] 方案已成交 id=%s", plan_id)


def _j(v: str | None, default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def _row_to_plan(row: Any) -> dict[str, Any]:
    """把 diy_plans 行还原为与 generate_diy_plan 兼容的方案 dict（供卡片/排序/下单）。"""
    flowers = _j(row["flowers"], [])
    design = {
        "main_flowers": [{"name": f["name"], "ratio": f.get("ratio")} for f in flowers if f.get("bucket") == "主花"],
        "fillers": [{"name": f["name"], "ratio": f.get("ratio")} for f in flowers if f.get("bucket") == "填充"],
        "foliage": [{"name": f["name"], "ratio": f.get("ratio")} for f in flowers if f.get("bucket") == "叶材"],
        "color_scheme": _j(row["color_scheme"], []),
        "packaging": row["packaging"],
        "meaning": row["meaning"],
    }
    budget = row["budget"]
    return {
        "plan_id": row["id"],
        "name": row["name"],
        "diy": True,
        "recipient": row["recipient"],
        "occasion": row["occasion"],
        "style": row["style"],
        "budget_num": budget,
        "design": design,
        "estimated_price": f"约 {int(budget)} 元" if budget else "",
        "desc": f"{row['name']}：{design['meaning'] or '我的 DIY 方案'}。",
        "diy_steps": _j(row["diy_steps"], []),
        "care_tips": row["care_tips"],
        "card_message": row["card_message"],
        "budget_breakdown": _j(row["budget_breakdown"], {}),
        "effect_image_url": row["effect_image_url"],
        "price": budget,  # 兼容 _filter_plans_by_requirement / _rank_plans 的预算命中
        "tags": [row["style"], row["occasion"], row["recipient"]],
        "requirement": row["requirement"],
        "order_count": row["order_count"],
        "status": row["status"],
    }


def get_diy_plan(plan_id: str) -> dict[str, Any] | None:
    """按 plan_id 取一条已确认的 DIY 方案。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM diy_plans WHERE id=?", (plan_id,)).fetchone()
    return _row_to_plan(row) if row else None


def search_diy_plans(
    user_id: str, requirement: Any | None = None, limit: int = 3
) -> list[dict[str, Any]]:
    """检索某用户已确认的 DIY 方案（个人资产复用），按需求软过滤、按成交数优先。"""
    if not user_id:
        return []
    from storage.repository import _filter_plans_by_requirement

    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM diy_plans WHERE user_id=? ORDER BY order_count DESC, confirmed_at DESC",
        (user_id,),
    ).fetchall()
    plans = [_row_to_plan(r) for r in rows]
    plans = _filter_plans_by_requirement(plans, requirement)
    # DIY 方案独有字段（recipient/occasion）软过滤：全部不命中时回退不过滤
    if requirement and (requirement.recipient or requirement.occasion):
        want_r = requirement.recipient
        want_o = requirement.occasion
        matched = [
            p for p in plans
            if (not want_r or str(p.get("recipient") or "") == want_r)
            and (not want_o or str(p.get("occasion") or "") == want_o)
        ]
        if matched:
            plans = matched
    return plans[:limit]


def list_proven_plans(limit: int = 20) -> list[dict[str, Any]]:
    """平台级实战方案（学习用）：按成交数/确认时间取 top 方案，供知识库 proven 域检索。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM diy_plans ORDER BY order_count DESC, confirmed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        p = _row_to_plan(r)
        out.append(
            {
                "id": p["plan_id"],
                "name": p["name"],
                "style": p["style"],
                "recipient": p["recipient"],
                "occasion": p["occasion"],
                "budget": p["budget_num"],
                "flowers": [f["name"] for f in p["design"]["main_flowers"]],
                "color_scheme": p["design"]["color_scheme"],
                "packaging": p["design"]["packaging"],
                "meaning": p["design"]["meaning"],
                "status": r["status"],
                "order_count": r["order_count"],
                "confirmed_at": r["confirmed_at"],
            }
        )
    return out
