"""tests/test_db_async.py —— P1 异步 DB 抽象层地基测试（aiosqlite，无需真实 PG）。

验证：占位符归一化跨方言、PG 下 date('now') 改写、以及在 aiosqlite 上的建表+读写往返。
"""
from __future__ import annotations

import asyncio

from backend.config import Settings
from backend.storage import db_async as dba


def test_normalize_sqlite_keeps_qmark_and_date(monkeypatch) -> None:
    """sqlite 回退路径下 normalize_sql 为恒等（sqlite3 原生支持 ? / date('now')）。"""
    monkeypatch.setattr(dba, 'settings', Settings(database_url=''))
    out = dba.normalize_sql("SELECT 1 WHERE id = ? AND date('now') = ?")
    assert out == "SELECT 1 WHERE id = ? AND date('now') = ?"

def test_normalize_postgres_rewrites_date(monkeypatch) -> None:
    """postgresql 下 date('now') 改写为 CURRENT_DATE::text（与 date(col)→substr 同为 text 可比），? 仍翻具名。"""
    monkeypatch.setattr(dba, 'settings', Settings(database_url='postgresql+asyncpg://u:p@h/db'))
    out = dba.normalize_sql("SELECT 1 WHERE date('now') = ?")
    assert out == 'SELECT 1 WHERE CURRENT_DATE::text = :p0'
    out2 = dba.normalize_sql('SELECT date(created_at) FROM orders WHERE date(created_at) >= ?')
    assert out2 == 'SELECT substr(created_at,1,10) FROM orders WHERE substr(created_at,1,10) >= :p0'

def test_async_roundtrip(tmp_path, monkeypatch) -> None:
    """aiosqlite 上：建表 → 插入(? 占位) → 查询，行以 dict 返回。"""
    from backend.storage import db as db_mod
    s = Settings(db_path=str(tmp_path / 't.db'), database_url='')
    monkeypatch.setattr(dba, 'settings', s)
    monkeypatch.setattr(db_mod, 'settings', s)
    try:
        delattr(db_mod._thread_local, 'conn')
    except AttributeError:
        pass
    dba._reset_engine()

    async def run() -> list[dict]:
        await dba.init_db_async()
        async with dba.transaction() as c:
            await c.execute('INSERT INTO users(id, role, created_at, updated_at) VALUES (?,?,?,?)', ('u1', 'user', '2026-01-01', '2026-01-01'))
        async with dba.transaction() as c:
            return await c.execute('SELECT id, role FROM users WHERE id = ?', ('u1',))
    rows = asyncio.run(run())
    assert rows == [{'id': 'u1', 'role': 'user'}]
    dba._reset_engine()
    try:
        delattr(db_mod._thread_local, 'conn')
    except AttributeError:
        pass
