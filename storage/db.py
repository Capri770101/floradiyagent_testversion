"""storage/db.py —— SQLite 连接与事务封装（线程安全）。

要点：
- SQLite 是同步库，不能在 async 里直接阻塞事件循环。本项目通过
  ``asyncio.to_thread`` 调用同步存储函数，配合「每线程独立连接」避免跨线程共享。
- 使用 WAL 模式 + busy_timeout，多个请求并发读写得更好。
- 所有建表在此集中维护，启动时调用 init_db() 即可。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from config import settings

logger = logging.getLogger("db")

#: 单线程连接缓存，避免每条 SQL 都重连
_thread_local = threading.local()

#: 建表语句（幂等）
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    stage      TEXT NOT NULL DEFAULT 'analyze',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT,
    tool_calls  TEXT,            -- assistant 的工具调用列表，JSON 字符串
    tool_call_id TEXT,           -- tool 角色消息对应的 tool_call_id（OpenAI/DeepSeek 要求必填）
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    user_id TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS orders (
    order_id   TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    plan_id    TEXT,
    plan_type  TEXT,
    shop_id    TEXT,
    items      TEXT,            -- JSON 字符串
    total_price REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS image_tasks (
    task_id    TEXT PRIMARY KEY,
    status     TEXT NOT NULL,   -- pending | running | done | failed
    prompt     TEXT,
    result_url TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_flags (
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, session_id, key)
);
"""


def get_conn() -> sqlite3.Connection:
    """获取当前线程的 SQLite 连接（懒初始化，线程安全）。"""
    if not hasattr(_thread_local, "conn"):
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        _thread_local.conn = conn
    return _thread_local.conn


@contextmanager
def transaction() -> sqlite3.Connection:
    """事务上下文：正常提交，异常回滚。"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    """建表并切换 WAL。应用启动时调用一次。"""
    conn = get_conn()
    conn.executescript(_SCHEMA)
    # 兼容旧库：messages 表若缺 tool_call_id 列则补上（仅开发期存量数据需要）
    cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "tool_call_id" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
    # 兼容旧库：sessions 表若缺 requirement 列则补上（结构化需求状态）
    s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "requirement" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN requirement TEXT")
    conn.commit()
    logger.info("长期记忆数据库就绪: %s", settings.db_path)
