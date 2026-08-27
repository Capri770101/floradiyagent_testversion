"""多会话（类 ChatGPT）记忆层测试：会话 CRUD + 历史回放持久化。

不依赖 LLM，纯 DB 逻辑单测。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.storage import memory as mem
from backend.storage.db import init_db

init_db()

def test_create_and_list_conversation():
    uid = 'conv_user_a'
    cid = asyncio.run(mem.create_conversation(uid, '给妈妈的生日花束'))
    assert cid
    convs = asyncio.run(mem.list_conversations(uid))
    assert any(c['id'] == cid and c['title'] == '给妈妈的生日花束' for c in convs)
    c = asyncio.run(mem.get_conversation(cid))
    assert c['user_id'] == uid
    assert c['title'] == '给妈妈的生日花束'

def test_preview_update():
    uid = 'conv_user_b'
    cid = asyncio.run(mem.create_conversation(uid))
    asyncio.run(mem.update_conversation_preview(cid, '预算 200 左右'))
    c = asyncio.run(mem.get_conversation(cid))
    assert c['preview'] == '预算 200 左右'

def test_get_or_create_session_with_id():
    uid = 'conv_user_c'
    cid = asyncio.run(mem.create_conversation(uid))
    assert asyncio.run(mem.get_or_create_session(uid, cid)) == cid
    new_id = 'explicit_' + 'x' * 8
    assert asyncio.run(mem.get_or_create_session(uid, new_id)) == new_id
    assert asyncio.run(mem.get_conversation(new_id)) is not None

def test_display_messages_persist_ui_data():
    uid = 'conv_user_d'
    cid = asyncio.run(mem.create_conversation(uid))
    asyncio.run(mem.save_messages(cid, [{'role': 'user', 'content': '想要一束康乃馨'}, {'role': 'assistant', 'content': '为你设计了一款', 'ui': 'plan_card', 'data': {'plans': [{'name': '康乃馨感恩花束', 'price': 199}]}}, {'role': 'tool', 'content': 'ok', 'tool_call_id': 'call_1'}]))
    msgs = asyncio.run(mem.load_display_messages(cid))
    assert [m['role'] for m in msgs] == ['user', 'assistant']
    assert msgs[1]['ui'] == 'plan_card'
    assert msgs[1]['data']['plans'][0]['name'] == '康乃馨感恩花束'

def test_delete_conversation_cascades():
    uid = 'conv_user_e'
    cid = asyncio.run(mem.create_conversation(uid))
    asyncio.run(mem.save_messages(cid, [{'role': 'user', 'content': 'hi'}]))
    assert asyncio.run(mem.delete_conversation(cid)) is True
    assert asyncio.run(mem.get_conversation(cid)) is None
    assert asyncio.run(mem.load_display_messages(cid)) == []
    assert asyncio.run(mem.delete_conversation(cid)) is False
