"""storage/memory.py —— 短期记忆（多会话消息历史）+ 长期记忆（用户偏好 KV）。

- 多会话：sessions 表即「会话」载体，一个用户可拥有多个会话（多轮对话），
  title/preview 供前端会话列表展示；messages 按 session_id 持久化全部历史，重启不丢。
- 长期：memories(user_id, key, value) KV，记录预算 / 送花对象 / 偏好色系等。
- 本模块已迁为异步（P1 异步迁移），统一通过 db_async.transaction 读写。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from agent.requirements import FlowerRequirement

from backend.storage import db_async as dba

logger = logging.getLogger('memory')

def _now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds')

async def get_or_create_session(user_id: str, conversation_id: str | None=None, shop_id: str | None=None) -> str:
    """返回会话 ID。

    - conversation_id 为空：为该用户新建一个会话（多会话模型下，不再 1:1 复用）。
    - conversation_id 给定：校验归属后复用；若该 id 不存在（如前端先建会话再发消息），
      则以该 id 创建会话，保证前后端会话 ID 一致。
    - shop_id：新建会话时绑定店铺，整个会话期间不变。
    """
    async with dba.transaction() as c:
        if conversation_id:
            rows = await c.execute('SELECT session_id FROM sessions WHERE session_id = ? AND user_id = ?', (conversation_id, user_id))
            if rows:
                return rows[0]['session_id']
            await c.execute('INSERT INTO sessions(session_id, user_id, stage, title, shop_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)', (conversation_id, user_id, 'analyze', '新对话', shop_id, _now(), _now()))
            return conversation_id
        session_id = uuid.uuid4().hex
        await c.execute('INSERT INTO sessions(session_id, user_id, stage, title, shop_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)', (session_id, user_id, 'analyze', '新对话', shop_id, _now(), _now()))
        return session_id

async def get_stage(session_id: str) -> str:
    async with dba.transaction() as c:
        rows = await c.execute('SELECT stage FROM sessions WHERE session_id = ?', (session_id,))
    return rows[0]['stage'] if rows else 'analyze'

async def get_session_shop_id(session_id: str) -> str | None:
    """读取会话绑定的 shop_id（无绑定返回 None）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT shop_id FROM sessions WHERE session_id = ?', (session_id,))
    return rows[0]['shop_id'] if rows else None

async def update_stage(session_id: str, stage: str) -> None:
    async with dba.transaction() as c:
        await c.execute('UPDATE sessions SET stage = ?, updated_at = ? WHERE session_id = ?', (stage, _now(), session_id))

async def get_requirement(session_id: str) -> FlowerRequirement | None:
    """读取会话的结构化需求（无则返回 None）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT requirement FROM sessions WHERE session_id = ?', (session_id,))
    if not rows or not rows[0]['requirement']:
        return None
    try:
        return FlowerRequirement.from_dict(json.loads(rows[0]['requirement']))
    except (json.JSONDecodeError, TypeError):
        return None

async def set_requirement(session_id: str, req: FlowerRequirement) -> None:
    """写入 / 覆盖会话的结构化需求（结构化需求状态的可持久化载体）。"""
    async with dba.transaction() as c:
        await c.execute('UPDATE sessions SET requirement = ?, updated_at = ? WHERE session_id = ?', (json.dumps(req.to_dict(), ensure_ascii=False), _now(), session_id))

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
        fn = tc.get('function') if isinstance(tc.get('function'), dict) else None
        if fn:
            name = fn.get('name', '')
            args = fn.get('arguments')
        else:
            name = tc.get('name', '')
            args = tc.get('arguments')
        if not isinstance(args, str):
            args = json.dumps(args or {}, ensure_ascii=False)
        calls.append({'id': tc.get('id') or '', 'type': 'function', 'function': {'name': name, 'arguments': args}})
    return calls

async def load_history(conversation_id: str, limit: int) -> list[dict[str, Any]]:
    """载入某会话最近 limit 条消息（不含 system），还原为 OpenAI 格式。

    历史回放净化（保证「有 tool_calls 必有对应 tool 回执」的合法序列）：
    - assistant 的 tool_calls 统一归一化为 OpenAI schema（兼容 Mock/真实双轨存储）。
    - tool 回执按 FIFO 与其前驱 assistant 的 tool_call 配对：孤儿回执丢弃；
      回执缺失（窗口截断 / Mock 空 id）的 assistant 工具调用消息一并丢弃，
      避免真实接口 400。
    """
    async with dba.transaction() as c:
        rows = await c.execute('SELECT role, content, tool_calls, tool_call_id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?', (conversation_id, limit))
    cleaned: list[dict[str, Any]] = []
    pending: list[str] = []
    for r in reversed(rows):
        if r['role'] == 'assistant' and r['tool_calls']:
            calls = _normalize_tool_calls(json.loads(r['tool_calls']))
            for tc in calls:
                pending.append(tc['id'])
            cleaned.append({'role': 'assistant', 'tool_calls': calls})
        elif r['role'] == 'tool':
            tid = r['tool_call_id']
            if tid is None or not pending or pending[0] != tid:
                continue
            pending.pop(0)
            cleaned.append({'role': 'tool', 'content': r['content'] or '', 'tool_call_id': tid})
        else:
            cleaned.append({'role': r['role'], 'content': r['content'] or ''})
    if pending:
        stale = set(pending)
        cleaned = [m for m in cleaned if not (m.get('role') == 'assistant' and m.get('tool_calls') and any(tc['id'] in stale for tc in m['tool_calls']))]
    return cleaned

async def save_messages(session_id: str, messages: list[dict[str, Any]]) -> None:
    """批量追加本轮新产生的消息（user / assistant / tool）。

    除角色/内容/工具调用外，助手消息的 ui/data 一并持久化，供前端会话回放时直接渲染
    结构化卡片（plan_card / dialog_options / pay_jump 等），无需重新请求智能体。
    """
    async with dba.transaction() as c:
        for m in messages:
            tool_calls = m.get('tool_calls')
            ui = m.get('ui')
            data = m.get('data')
            await c.execute('INSERT INTO messages(session_id, role, content, tool_calls, tool_call_id, ui, data, created_at) VALUES (?,?,?,?,?,?,?,?)', (session_id, m['role'], m.get('content'), json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None, m.get('tool_call_id'), ui if ui is not None else None, json.dumps(data, ensure_ascii=False) if data is not None else None, _now()))

async def reset_session(user_id: str, conversation_id: str | None=None) -> bool:
    """清空短期记忆。

    - conversation_id 给定：仅删除该会话（会话级重置，保留其他历史）。
    - 否则（兼容旧调试端点）：删除该用户最近的一个会话。
    长期偏好（memories）始终保留。返回是否清到了数据。
    """
    async with dba.transaction() as c:
        if conversation_id:
            sid = conversation_id
        else:
            rows = await c.execute('SELECT session_id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1', (user_id,))
            if not rows:
                return False
            sid = rows[0]['session_id']
        await c.execute('DELETE FROM messages WHERE session_id = ?', (sid,))
        await c.execute('DELETE FROM session_flags WHERE session_id = ?', (sid,))
        await c.execute('DELETE FROM sessions WHERE session_id = ?', (sid,))
    return True

async def create_conversation(user_id: str, title: str='新对话', shop_id: str | None=None) -> str:
    """新建一个会话，返回会话 ID。shop_id 绑定后整个会话期间不变。"""
    sid = uuid.uuid4().hex
    async with dba.transaction() as c:
        await c.execute('INSERT INTO sessions(session_id, user_id, stage, title, shop_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)', (sid, user_id, 'analyze', (title or '新对话')[:50], shop_id, _now(), _now()))
    return sid

async def list_conversations(user_id: str) -> list[dict[str, Any]]:
    """列出某用户的全部会话（按最近活动时间倒序）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT session_id, title, preview, shop_id, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC', (user_id,))
    return [{'id': r['session_id'], 'title': r['title'] or '新对话', 'preview': r['preview'] or '', 'shop_id': r['shop_id'], 'created_at': r['created_at'], 'updated_at': r['updated_at']} for r in rows]

async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    """读取单个会话元信息（无则返回 None）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT session_id, user_id, title, preview, shop_id, created_at, updated_at FROM sessions WHERE session_id = ?', (conversation_id,))
    return dict(rows[0]) if rows else None

async def update_conversation_preview(conversation_id: str, preview: str) -> None:
    """更新会话列表预览与最近活动时间。"""
    async with dba.transaction() as c:
        await c.execute('UPDATE sessions SET preview = ?, updated_at = ? WHERE session_id = ?', ((preview or '')[:100], _now(), conversation_id))

async def rename_conversation(conversation_id: str, title: str) -> bool:
    """重命名会话标题，返回是否真的改到了。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT session_id FROM sessions WHERE session_id = ?', (conversation_id,))
        if not rows:
            return False
        await c.execute('UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?', ((title or '新对话')[:50], _now(), conversation_id))
    return True

async def delete_conversation(conversation_id: str) -> bool:
    """删除会话（级联清消息与控制标记）。返回是否真的删到了。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT session_id FROM sessions WHERE session_id = ?', (conversation_id,))
        if not rows:
            return False
        await c.execute('DELETE FROM messages WHERE session_id = ?', (conversation_id,))
        await c.execute('DELETE FROM session_flags WHERE session_id = ?', (conversation_id,))
        await c.execute('DELETE FROM sessions WHERE session_id = ?', (conversation_id,))
    return True

async def load_display_messages(conversation_id: str) -> list[dict[str, Any]]:
    """载入会话内供前端回放的消息（仅 user/assistant，按时间正序）。

    每条含 role/content，助手消息附带 ui/data（若有），直接喂给前端 renderMessage。
    工具观测消息（role=tool）不返回——它们仅用于智能体内部推理，无需展示。
    """
    async with dba.transaction() as c:
        rows = await c.execute("SELECT role, content, ui, data FROM messages WHERE session_id = ? AND role IN ('user','assistant') ORDER BY id ASC", (conversation_id,))
    out: list[dict[str, Any]] = []
    for r in rows:
        msg: dict[str, Any] = {'role': r['role'], 'content': r['content'] or ''}
        if r['ui']:
            msg['ui'] = r['ui']
        if r['data']:
            try:
                msg['data'] = json.loads(r['data'])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(msg)
    return out

async def set_session_flag(user_id: str, session_id: str, key: str, value: str) -> None:
    """写入 / 覆盖一条会话控制标记。"""
    async with dba.transaction() as c:
        await c.execute('INSERT INTO session_flags (user_id, session_id, key, value, updated_at) VALUES (?,?,?,?,?) ON CONFLICT (user_id, session_id, key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at', (user_id, session_id, key, value, _now()))

async def get_session_flag(user_id: str, session_id: str, key: str) -> str:
    """读取会话控制标记（无则返回空串）。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT value FROM session_flags WHERE user_id = ? AND session_id = ? AND key = ?', (user_id, session_id, key))
    return rows[0]['value'] if rows else ''

async def clear_session_flags(user_id: str, session_id: str, prefix: str='') -> None:
    """清除会话控制标记；prefix 非空时仅清除该前缀的标记（如进入生图阶段清 image_*）。"""
    async with dba.transaction() as c:
        if prefix:
            await c.execute('DELETE FROM session_flags WHERE user_id = ? AND session_id = ? AND key LIKE ?', (user_id, session_id, f'{prefix}%'))
        else:
            await c.execute('DELETE FROM session_flags WHERE user_id = ? AND session_id = ?', (user_id, session_id))

async def set_session_json(user_id: str, session_id: str, key: str, value: Any) -> None:
    """写入 / 覆盖一条会话级 JSON 状态（如会话内最新 DIY 方案、最近引用方案）。

    用 session_flags 表承载（value 存 JSON 字符串），随会话隔离，多用户互不串号。
    """
    async with dba.transaction() as c:
        await c.execute('INSERT INTO session_flags (user_id, session_id, key, value, updated_at) VALUES (?,?,?,?,?) ON CONFLICT (user_id, session_id, key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at', (user_id, session_id, key, json.dumps(value, ensure_ascii=False), _now()))

async def get_session_json(user_id: str, session_id: str, key: str) -> Any:
    """读取会话级 JSON 状态（无或解析失败返回 None）。"""
    raw = await get_session_flag(user_id, session_id, key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

async def get_long_term(user_id: str) -> dict[str, str]:
    """读取用户全部长期偏好。"""
    async with dba.transaction() as c:
        rows = await c.execute('SELECT key, value FROM memories WHERE user_id = ?', (user_id,))
    return {r['key']: r['value'] for r in rows}

async def set_long_term(user_id: str, key: str, value: str) -> None:
    """写入 / 覆盖一条长期偏好。"""
    async with dba.transaction() as c:
        await c.execute('INSERT INTO memories(user_id, key, value) VALUES (?,?,?) ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value', (user_id, key, value))
    logger.info('[memory] 用户 %s 长期记忆已写入 %s=%s', user_id, key, value)
