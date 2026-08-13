"""storage/memory.py —— 短期记忆（会话消息历史）+ 长期记忆（用户偏好 KV）。

- 短期：sessions / messages 表，按 session_id 持久化全部历史，重启不丢。
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


def get_or_create_session(user_id: str) -> str:
    """返回该用户的会话 ID（一个用户一个会话，简单 1:1）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT session_id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        return row["session_id"]
    session_id = uuid.uuid4().hex
    with transaction() as c:
        c.execute(
            "INSERT INTO sessions(session_id, user_id, stage, created_at, updated_at) VALUES (?,?,?,?,?)",
            (session_id, user_id, "analyze", _now(), _now()),
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


def load_history(user_id: str, limit: int) -> list[dict[str, Any]]:
    """载入该用户最近 limit 条消息（不含 system），还原为 OpenAI 格式。"""
    conn = get_conn()
    session = conn.execute(
        "SELECT session_id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if not session:
        return []
    rows = conn.execute(
        "SELECT role, content, tool_calls, tool_call_id FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session["session_id"], limit),
    ).fetchall()
    messages: list[dict[str, Any]] = []
    for r in reversed(rows):  # 恢复原时间顺序
        msg: dict[str, Any] = {"role": r["role"]}
        if r["tool_calls"]:
            msg["tool_calls"] = json.loads(r["tool_calls"])
        else:
            msg["content"] = r["content"] or ""
        # OpenAI/DeepSeek 规范：tool 角色消息必须携带 tool_call_id，否则真实接口 400。
        # 历史脏数据（缺 tool_call_id）直接丢弃，并连带丢弃其前面的 assistant(tool_calls)，
        # 避免「有 tool_calls 却无对应 tool 回执」的非法序列。
        if r["role"] == "tool":
            if not r["tool_call_id"]:
                if messages and messages[-1].get("role") == "assistant" and messages[-1].get("tool_calls"):
                    messages.pop()
                continue
            msg["tool_call_id"] = r["tool_call_id"]
        messages.append(msg)
    return messages


def save_messages(session_id: str, messages: list[dict[str, Any]]) -> None:
    """批量追加本轮新产生的消息（user / assistant / tool）。"""
    with transaction() as c:
        for m in messages:
            tool_calls = m.get("tool_calls")
            c.execute(
                "INSERT INTO messages(session_id, role, content, tool_calls, tool_call_id, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    session_id,
                    m["role"],
                    m.get("content"),
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                    m.get("tool_call_id"),  # tool 消息的回执标识，OpenAI 要求必填
                    _now(),
                ),
            )


def reset_session(user_id: str) -> bool:
    """清空该用户的短期记忆（会话与消息），保留长期偏好。返回是否清到了数据。"""
    conn = get_conn()
    session = conn.execute(
        "SELECT session_id FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not session:
        return False
    sid = session["session_id"]
    with transaction() as c:
        c.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
        c.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
    return True


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
