"""历史回放净化测试：Mock/真实双轨会话切换时保证「有 tool_calls 必有回执」的合法序列。

覆盖：
1. Mock 形态 tool_calls（无 id、无 function 包装）回放时归一化为 OpenAI schema。
2. 缺回执的 assistant 工具调用消息被整体丢弃（含窗口截断场景）。
3. 前驱不在窗口内的孤儿 tool 回执被丢弃。
"""
import asyncio

from backend.storage import memory as mem
from backend.storage.db import init_db


def _fresh_user(uid: str) -> str:
    init_db()
    return asyncio.run(mem.get_or_create_session(uid))

def test_mock_tool_calls_normalized_to_openai_schema() -> None:
    """Mock 形态（{name, arguments}、空 id）回放时归一化为 OpenAI 规范 schema。"""
    sid = _fresh_user('h_normalize')
    asyncio.run(mem.save_messages(sid, [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'tool_calls': [{'id': '', 'name': 'search_plans', 'arguments': {'keyword': '玫瑰'}}]}, {'role': 'tool', 'content': '[]', 'tool_call_id': ''}]))
    msgs = asyncio.run(mem.load_history(sid, 20))
    assert len(msgs) == 3
    assistant = msgs[1]
    call = assistant['tool_calls'][0]
    assert call['type'] == 'function'
    assert call['function']['name'] == 'search_plans'
    assert isinstance(call['function']['arguments'], str)
    assert msgs[2]['role'] == 'tool' and msgs[2]['tool_call_id'] == ''

def test_assistant_without_tool_reply_is_dropped() -> None:
    """缺回执的 assistant 工具调用消息应被整体丢弃（真实接口会 400）。"""
    sid = _fresh_user('h_missing')
    asyncio.run(mem.save_messages(sid, [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'tool_calls': [{'id': 'c1', 'name': 'search_plans', 'arguments': {}}]}]))
    msgs = asyncio.run(mem.load_history(sid, 20))
    assert len(msgs) == 1
    assert msgs[0]['role'] == 'user'

def test_orphan_tool_reply_is_dropped() -> None:
    """前驱 assistant 不在窗口内的孤儿 tool 回执应被丢弃。"""
    sid = _fresh_user('h_orphan')
    asyncio.run(mem.save_messages(sid, [{'role': 'tool', 'content': '[]', 'tool_call_id': 'c9'}]))
    assert asyncio.run(mem.load_history(sid, 20)) == []

def test_dirty_history_clean_pair_survives() -> None:
    """合法配对（含 Mock 空 id）在净化后完整保留，且顺序正确。"""
    sid = _fresh_user('h_clean')
    asyncio.run(mem.save_messages(sid, [{'role': 'user', 'content': '帮我设计'}, {'role': 'assistant', 'tool_calls': [{'id': '', 'name': 'generate_diy_plan', 'arguments': {}}]}, {'role': 'tool', 'content': '{"plan_id": "DIY_1"}', 'tool_call_id': ''}, {'role': 'assistant', 'content': '已为您设计好'}]))
    msgs = asyncio.run(mem.load_history(sid, 20))
    assert [m['role'] for m in msgs] == ['user', 'assistant', 'tool', 'assistant']
    assert msgs[1]['tool_calls'][0]['function']['name'] == 'generate_diy_plan'
