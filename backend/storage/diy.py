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

from backend.storage.db import get_conn

logger = logging.getLogger("storage.diy")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _flower_keys(design: dict) -> list[str]:
    out: list[str] = []
    for bucket, key in (("m", "main_flowers"), ("f", "fillers"), ("g", "foliage")):
        for f in design.get(key) or []:
            name = f.get("name") if isinstance(f, dict) else f
            if name:
                out.append(f"{bucket}:{name}")
    return sorted(out)


def _fingerprint(plan: dict) -> str:
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
            "budget_breakdown, effect_image_url, difficulty, est_time, shelf_life,"
            "suitable_for, caution, mood_tags, status, order_count, created_at, confirmed_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                plan_id, user_id, fp,
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
                str(d.get("difficulty") or ""),
                d.get("est_time"),
                str(d.get("shelf_life") or ""),
                json.dumps(d.get("suitable_for") or [], ensure_ascii=False),
                str(d.get("caution") or ""),
                json.dumps(d.get("mood_tags") or [], ensure_ascii=False),
                "confirmed",
                0,
                now,
                now,
            ),
        )
    logger.info("[diy] saved id=%s user=%s", plan_id, user_id)
    return {"saved": True, "duplicate": False, "plan_id": plan_id}


def mark_diy_plan_ordered(plan_id: str) -> None:
    if not plan_id:
        return
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "UPDATE diy_plans SET status='ordered', order_count=order_count+1 WHERE id=?",
            (plan_id,),
        )
        if cur.rowcount:
            logger.info("[diy] ordered id=%s", plan_id)


def save_as_template(plan_id: str) -> None:
    if not plan_id:
        return
    conn = get_conn()
    row = conn.execute("SELECT * FROM diy_plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        return
    fp = row["fingerprint"]
    existing = conn.execute(
        "SELECT id FROM diy_plans WHERE user_id='template' AND fingerprint=?",
        (fp,),
    ).fetchone()
    with conn:
        if existing:
            conn.execute(
                "UPDATE diy_plans SET order_count=order_count+1 WHERE id=?",
                (existing["id"],),
            )
            logger.info("[diy] template exists, increment template_id=%s", existing["id"])
        else:
            conn.execute(
                "INSERT INTO diy_plans("
                "id,user_id,fingerprint,name,requirement,recipient,occasion,style,budget,"
                "color_scheme,flowers,packaging,meaning,diy_steps,care_tips,card_message,"
                "budget_breakdown,effect_image_url,difficulty,est_time,shelf_life,"
                "suitable_for,caution,mood_tags,status,order_count,source_user_id,created_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "TPL_" + plan_id, "template", fp,
                    row["name"], row["requirement"], row["recipient"],
                    row["occasion"], row["style"], row["budget"],
                    row["color_scheme"], row["flowers"], row["packaging"],
                    row["meaning"], row["diy_steps"], row["care_tips"],
                    row["card_message"], row["budget_breakdown"],
                    row["effect_image_url"], row["difficulty"], row["est_time"],
                    row["shelf_life"], row["suitable_for"], row["caution"],
                    row["mood_tags"], "template", 1, row["user_id"], row["created_at"],
                ),
            )
            logger.info("[diy] new template plan_id=%s -> TPL_%s", plan_id, plan_id)


def _j(v: str | None, default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def _row_to_plan(row: Any) -> dict[str, Any]:
    flowers = _j(row["flowers"], [])
    design = {
        "main_flowers": [{"name": f["name"], "ratio": f.get("ratio")} for f in flowers if f.get("bucket") == "主花"],
        "fillers": [{"name": f["name"], "ratio": f.get("ratio")} for f in flowers if f.get("bucket") == "填充"],
        "foliage": [{"name": f["name"], "ratio": f.get("ratio")} for f in flowers if f.get("bucket") == "叶材"],
        "color_scheme": _j(row["color_scheme"], []),
        "packaging": row["packaging"],
        "meaning": row["meaning"],
        "difficulty": row["difficulty"],
        "est_time": row["est_time"],
        "shelf_life": row["shelf_life"],
        "suitable_for": _j(row["suitable_for"], []),
        "caution": row["caution"],
        "mood_tags": _j(row["mood_tags"], []),
    }
    budget = row["budget"]
    style_label = row["style"] or "定制"
    main_names = [f["name"] for f in flowers if f.get("bucket") == "主花"]
    fill_names = [f["name"] for f in flowers if f.get("bucket") == "填充"]
    foli_names = [f["name"] for f in flowers if f.get("bucket") == "叶材"]
    colors = _j(row["color_scheme"], [])
    effect_prompt = (
        f"{style_label}风格花束，"
        f"主花为{'、'.join(main_names) or '玫瑰'}，"
        f"搭配{'、'.join(fill_names) or '满天星'}与{'、'.join(foli_names) or '尤加利'}，"
        f"色调{'/'.join(colors) or '温柔粉'}，{row['packaging'] or '花束'}包装，"
        f"背景干净柔和，摄影级静物，高级感"
    )
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
        "effect_prompt": effect_prompt,
        "price": budget,
        "tags": [row["style"], row["occasion"], row["recipient"]],
        "requirement": row["requirement"],
        "order_count": row["order_count"],
        "status": row["status"],
    }


def get_diy_plan(plan_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM diy_plans WHERE id=?", (plan_id,)).fetchone()
    return _row_to_plan(row) if row else None


def search_diy_plans(
    user_id: str, requirement: Any | None = None, limit: int = 3
) -> list[dict[str, Any]]:
    if not user_id:
        return []
    from backend.storage.repository import _filter_plans_by_requirement
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM diy_plans WHERE user_id=? ORDER BY order_count DESC, confirmed_at DESC",
        (user_id,),
    ).fetchall()
    plans = [_row_to_plan(r) for r in rows]
    plans = _filter_plans_by_requirement(plans, requirement)
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
