"""storage/memory.py —— 短期记忆（多会话消息历史）+ 长期记忆（用户偏好 KV）。

- 多会话：sessions 表即「会话」载体，一个用户可拥有多个会话（多轮对话），
  title/preview 供前端会话列表展示；messages 按 session_id 持久化全部历史，重启不丢。
- 长期：memories(user_id, key, value) KV，记录预算 / 送花对象 / 偏好色系等。
- 所有方法均为同步；由上层用 asyncio.to_thread 调用，避免阻塞事件循环。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from requirements import FlowerRequirement
from storage.db import get_conn, transaction

logger = logging.getLogger("memory")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# 会话（短期记忆载体）
# --------------------------------------------------------------------------- #


def get_or_create_session(user_id: str, conversation_id: str | None = None) -> str:
    """返回会话 ID。

    - conversation_id 为空：为该用户新建一个会话（多会话模型下，不再 1:1 复用）。
    - conversation_id 给定：校验归属后复用；若该 id 不存在（如前端先建会话再发消息），
      则以该 id 创建会话，保证前后端会话 ID 一致。
    """
    conn = get_conn()
    if conversation_id:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if row:
            return row["session_id"]
        with transaction() as c:
            c.execute(
                "INSERT INTO sessions(session_id, user_id, stage, title, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (conversation_id, user_id, "analyze", "新对话", _now(), _now()),
            )
        return conversation_id
    # 无显式 id → 新建会话
    session_id = uuid.uuid4().hex
    with transaction() as c:
        c.execute(
            "INSERT INTO sessions(session_id, user_id, stage, title, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, user_id, "analyze", "新对话", _now(), _now()),
        )
    return session_id


def get_stage(session_id: str) -> str:
    conn = get_conn()
    row = conn.execute("SELECT stage FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return row["stage"] if row else "analyze"


def update_stage(session_id: str, stage: str) -> None:
    with transaction() as c:
        c.execute(
            "UPDATE sessions SET stage = ?, updated_at = ? WHERE session_id = ?",
            (stage, _now(), session_id),
        )


def get_requirement(session_id: str) -> FlowerRequirement | None:
    """读取会话的结构化需求（无则返回 None）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT requirement FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row or not row["requirement"]:
        return None
    try:
        return FlowerRequirement.from_dict(json.loads(row["requirement"]))
    except (json.JSONDecodeError, TypeError):
        return None


def set_requirement(session_id: str, req: FlowerRequirement) -> None:
    """写入 / 覆盖会话的结构化需求（结构化需求状态的可持久化载体）。"""
    with transaction() as c:
        c.execute(
            "UPDATE sessions SET requirement = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(req.to_dict(), ensure_ascii=False), _now(), session_id),
        )


def _normalize_tool_calls(raw: Any) -> list[dict[str, Any]]:
    """把历史 tool_calls 归一化为 OpenAI 规范 schema。

    真实会话存的是 {id, type, function:{name, arguments}}；Mock 会话存的是
    {name, arguments}（无 id）。若不归一化，同一会话从 Mock 切到真实 LLM 时
    回放历史会触发 400（missing field 'type' / arguments 非 JSON 字符串）。
    """
    calls: list[dict[str, Any]] = []
    for tc in raw or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else None
        if fn:
            name = fn.get("name", "")
            args = fn.get("arguments")
        else:
            name = tc.get("name", "")
            args = tc.get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args or {}, ensure_ascii=False)
        calls.append(
            {
                "id": tc.get("id") or "",
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
    return calls


def load_history(conversation_id: str, limit: int) -> list[dict[str, Any]]:
    """载入某会话最近 limit 条消息（不含 system），还原为 OpenAI 格式。

    历史回放净化（保证「有 tool_calls 必有对应 tool 回执」的合法序列）：
    - assistant 的 tool_calls 统一归一化为 OpenAI schema（兼容 Mock/真实双轨存储）。
    - tool 回执按 FIFO 与其前驱 assistant 的 tool_call 配对：孤儿回执丢弃；
      回执缺失（窗口截断 / Mock 空 id）的 assistant 工具调用消息一并丢弃，
      避免真实接口 400。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content, tool_calls, tool_call_id FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    cleaned: list[dict[str, Any]] = []
    pending: list[str] = []  # 尚待回执的 tool_call_id（FIFO，与 OpenAI 回执顺序一致）
    for r in reversed(rows):  # 恢复原时间顺序
        if r["role"] == "assistant" and r["tool_calls"]:
            calls = _normalize_tool_calls(json.loads(r["tool_calls"]))
            for tc in calls:
                pending.append(tc["id"])
            cleaned.append({"role": "assistant", "tool_calls": calls})
        elif r["role"] == "tool":
            tid = r["tool_call_id"]
            # 孤儿 / 失配回执（前驱不在窗口内，或 id 顺序错位）→ 丢弃，连带其 assistant 后段清理。
            # 注意：Mock 会话的配对 id 是空串（""），是合法配对键，不能用「非空」判定。
            if tid is None or not pending or pending[0] != tid:
                continue
            pending.pop(0)
            cleaned.append(
                {"role": "tool", "content": r["content"] or "", "tool_call_id": tid}
            )
        else:
            cleaned.append({"role": r["role"], "content": r["content"] or ""})
    # 仍有未收到回执的 assistant 工具调用消息 → 丢弃（缺回执的序列真实接口会 400）
    if pending:
        stale = set(pending)
        cleaned = [
            m
            for m in cleaned
            if not (
                m.get("role") == "assistant"
                and m.get("tool_calls")
                and any(tc["id"] in stale for tc in m["tool_calls"])
            )
        ]
    return cleaned


def save_messages(session_id: str, messages: list[dict[str, Any]]) -> None:
    """批量追加本轮新产生的消息（user / assistant / tool）。

    除角色/内容/工具调用外，助手消息的 ui/data 一并持久化，供前端会话回放时直接渲染
    结构化卡片（plan_card / dialog_options / pay_jump 等），无需重新请求智能体。
    """
    with transaction() as c:
        for m in messages:
            tool_calls = m.get("tool_calls")
            ui = m.get("ui")  # 纯字符串（如 'plan_card'），直接存，无需 JSON 包裹
            data = m.get("data")  # dict，需 JSON 序列化
            c.execute(
                "INSERT INTO messages(session_id, role, content, tool_calls, tool_call_id, ui, data, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    m["role"],
                    m.get("content"),
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                    m.get("tool_call_id"),  # tool 消息的回执标识，OpenAI 要求必填
                    ui if ui is not None else None,
                    json.dumps(data, ensure_ascii=False) if data is not None else None,
                    _now(),
                ),
            )


def reset_session(user_id: str, conversation_id: str | None = None) -> bool:
    """清空短期记忆。

    - conversation_id 给定：仅删除该会话（会话级重置，保留其他历史）。
    - 否则（兼容旧调试端点）：删除该用户最近的一个会话。
    长期偏好（memories）始终保留。返回是否清到了数据。
    """
    conn = get_conn()
    if conversation_id:
        sid = conversation_id
    else:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row:
            return False
        sid = row["session_id"]
    with transaction() as c:
        c.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
        c.execute("DELETE FROM session_flags WHERE session_id = ?", (sid,))
        c.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
    return True


# --------------------------------------------------------------------------- #
# 多会话管理（前端「类 ChatGPT」会话列表 / 切换 / 删除）
# --------------------------------------------------------------------------- #


def create_conversation(user_id: str, title: str = "新对话") -> str:
    """新建一个会话，返回会话 ID。"""
    sid = uuid.uuid4().hex
    with transaction() as c:
        c.execute(
            "INSERT INTO sessions(session_id, user_id, stage, title, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (sid, user_id, "analyze", (title or "新对话")[:50], _now(), _now()),
        )
    return sid


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    """列出某用户的全部会话（按最近活动时间倒序）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, title, preview, created_at, updated_at "
        "FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r["session_id"],
            "title": r["title"] or "新对话",
            "preview": r["preview"] or "",
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    """读取单个会话元信息（无则返回 None）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT session_id, user_id, title, preview, created_at, updated_at "
        "FROM sessions WHERE session_id = ?",
        (conversation_id,),
    ).fetchone()
    return dict(row) if row else None


def update_conversation_preview(conversation_id: str, preview: str) -> None:
    """更新会话列表预览与最近活动时间。"""
    with transaction() as c:
        c.execute(
            "UPDATE sessions SET preview = ?, updated_at = ? WHERE session_id = ?",
            ((preview or "")[:100], _now(), conversation_id),
        )


def delete_conversation(conversation_id: str) -> bool:
    """删除会话（级联清消息与控制标记）。返回是否真的删到了。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT session_id FROM sessions WHERE session_id = ?", (conversation_id,)
    ).fetchone()
    if not row:
        return False
    with transaction() as c:
        c.execute("DELETE FROM messages WHERE session_id = ?", (conversation_id,))
        c.execute("DELETE FROM session_flags WHERE session_id = ?", (conversation_id,))
        c.execute("DELETE FROM sessions WHERE session_id = ?", (conversation_id,))
    return True


def load_display_messages(conversation_id: str) -> list[dict[str, Any]]:
    """载入会话内供前端回放的消息（仅 user/assistant，按时间正序）。

    每条含 role/content，助手消息附带 ui/data（若有），直接喂给前端 renderMessage。
    工具观测消息（role=tool）不返回——它们仅用于智能体内部推理，无需展示。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content, ui, data FROM messages "
        "WHERE session_id = ? AND role IN ('user','assistant') ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        msg: dict[str, Any] = {"role": r["role"], "content": r["content"] or ""}
        if r["ui"]:
            msg["ui"] = r["ui"]  # 纯字符串，直接取
        if r["data"]:
            try:
                msg["data"] = json.loads(r["data"])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(msg)
    return out


# --------------------------------------------------------------------------- #
# 会话控制标记（一次性业务约束，如生图确认 image_confirmed/image_submitted）
# --------------------------------------------------------------------------- #


def set_session_flag(user_id: str, session_id: str, key: str, value: str) -> None:
    """写入 / 覆盖一条会话控制标记。"""
    with transaction() as c:
        c.execute(
            "INSERT OR REPLACE INTO session_flags (user_id, session_id, key, value, updated_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, session_id, key, value, _now()),
        )


def get_session_flag(user_id: str, session_id: str, key: str) -> str:
    """读取会话控制标记（无则返回空串）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM session_flags WHERE user_id = ? AND session_id = ? AND key = ?",
        (user_id, session_id, key),
    ).fetchone()
    return row["value"] if row else ""


def clear_session_flags(user_id: str, session_id: str, prefix: str = "") -> None:
    """清除会话控制标记；prefix 非空时仅清除该前缀的标记（如进入生图阶段清 image_*）。"""
    with transaction() as c:
        if prefix:
            c.execute(
                "DELETE FROM session_flags WHERE user_id = ? AND session_id = ? AND key LIKE ?",
                (user_id, session_id, f"{prefix}%"),
            )
        else:
            c.execute(
                "DELETE FROM session_flags WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )


def set_session_json(user_id: str, session_id: str, key: str, value: Any) -> None:
    """写入 / 覆盖一条会话级 JSON 状态（如会话内最新 DIY 方案、最近引用方案）。

    用 session_flags 表承载（value 存 JSON 字符串），随会话隔离，多用户互不串号。
    """
    with transaction() as c:
        c.execute(
            "INSERT OR REPLACE INTO session_flags (user_id, session_id, key, value, updated_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, session_id, key, json.dumps(value, ensure_ascii=False), _now()),
        )


def get_session_json(user_id: str, session_id: str, key: str) -> Any:
    """读取会话级 JSON 状态（无或解析失败返回 None）。"""
    raw = get_session_flag(user_id, session_id, key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# 长期记忆（用户偏好 KV）
# --------------------------------------------------------------------------- #


def get_long_term(user_id: str) -> dict[str, str]:
    """读取用户全部长期偏好。"""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM memories WHERE user_id = ?", (user_id,)).fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_long_term(user_id: str, key: str, value: str) -> None:
    """写入 / 覆盖一条长期偏好。"""
    with transaction() as c:
        c.execute(
            "INSERT INTO memories(user_id, key, value) VALUES (?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, key, value),
        )
    logger.info("[memory] 用户 %s 长期记忆已写入 %s=%s", user_id, key, value)
