"""storage/db_async.py —— P1 异步、方言无关的 DB 访问抽象层（迁移地基）。

为什么需要（详见 EXTENSION_ENGINEERING_PLAN.md 第 3 节，已据代码核实）：
- 现状 ``db.py:get_conn()`` 返回**同步 sqlite3**（应用启动时 ``init_db()`` 已置为 WAL 模式），
  被 router 层用 ``asyncio.to_thread`` 包裹。迁 PG(asyncpg) 必须改成 ``await conn.execute``，
  且 ``?`` / ``date('now')`` / ``INSERT OR`` / ``JSON`` 等方言要适配。
- 本模块在**不动现有同步 sqlite 代码**的前提下，提供第二套「异步 + 方言无关」访问层作为迁移地基。

设计要点（地基，非全量迁移）：
- **sqlite 回退路径**：直接复用现有 ``db.get_conn()``（同一连接、同一 WAL 文件，与全站同步代码
  100% 兼容），只在执行时用 ``asyncio.to_thread`` 包一层，对外暴露 ``await`` 接口。
  这样迁来的存储函数（如 report.py）与仍走同步 ``get_conn()`` 的模块共享同一 DB 视图，不会因
  双驱动（aiosqlite vs sqlite3）的 journal 模式不一致而出现可见性错乱。
- **postgresql 路径**：用 ``asyncpg`` 异步引擎；``normalize_sql`` 把 ``?`` 翻成 ``:p0,:p1``、
  ``date('now')`` 翻成 ``CURRENT_DATE``，逐站方言特例（``INSERT OR`` / ``JSON``）后续人工迁移。
- 引擎按 ``DATABASE_URL`` 选择（postgresql+asyncpg）；未配置则回退 sqlite（沿用 ``db_path``），
  本地/dev 零改动可跑。

验证：本模块可在 aiosqlite/sqlite 单测证明抽象正确；PG 端到端需在装有 Postgres 的环境跑。
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import settings
from backend.storage import db as sync_db

logger = logging.getLogger('storage.db_async')
_SQLITE_QMARK = re.compile('\\?')
_INLINE_COMMENT = re.compile('--[^\\n]*')
_DATE_NOW = re.compile('date\\s*\\(\\s*[\'\\"]?now[\'\\"]?\\s*\\)', re.IGNORECASE)
_DATETIME_NOW = re.compile('datetime\\s*\\(\\s*[\'\\"]?now[\'\\"]?\\s*\\)', re.IGNORECASE)
_AUTOINC_RE = re.compile('INTEGER\\s+PRIMARY\\s+KEY\\s+AUTOINCREMENT', re.IGNORECASE)

def dialect() -> str:
    """返回当前启用的方言：``DATABASE_URL`` 配置了 postgresql(+asyncpg) 则为 postgresql，
    否则回退 sqlite（沿用 ``db_path`` 文件）。

    识别基于 SQLAlchemy ``make_url().get_backend_name()``，比硬编码前缀更稳，
    也为未来接入 mysql/mssql 等预留（届时在 ``normalize_sql`` 补对应方言特例即可，
    ``dialect()`` 自身无需改动）。
    """
    url = (settings.database_url or '').strip()
    if not url:
        return 'sqlite'
    try:
        backend = make_url(url).get_backend_name()
    except Exception:
        logger.warning('DATABASE_URL 解析失败，回退 sqlite：%r', url)
        return 'sqlite'
    return 'postgresql' if backend.startswith('postgresql') else 'sqlite'

def normalize_sql(sql: str) -> str:
    """把 ``?`` 位置参数翻成 SQLAlchemy 具名参数 ``:p0,:p1``（PG 编译需要）。

    - sqlite 回退路径：``normalize_sql`` 为恒等（sqlite3 原生支持 ``?``）。
    - postgresql 路径：``?`` → ``:p0,:p1``；``date('now')`` → ``CURRENT_DATE``；
      ``date(col)`` → ``col::date``；``date('now', :pN)`` → interval 运算。
    """
    if dialect() != 'postgresql':
        return sql
    idx = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal idx
        idx += 1
        return f':p{idx - 1}'
    s = _SQLITE_QMARK.sub(_sub, sql)
    # date('now') → CURRENT_DATE::text（与 date(col)→substr 同为 text，可互相比较）
    s = _DATE_NOW.sub('CURRENT_DATE::text', s)
    s = _DATETIME_NOW.sub('CURRENT_TIMESTAMP', s)
    # date(col) → substr(col,1,10)（保持 text 语义：参数仍为 YYYY-MM-DD 字符串，
    # PG 按字典序比较，asyncpg 不会误把参数推断为 date 类型）。
    s = re.sub(r'\bdate\((\w+)\)', r'substr(\1,1,10)', s)
    # sqlite 把整数 0/1 当布尔；PG 需要显式 boolean。仅替换作为独立布尔条件出现
    # 的 ``AND 0`` / ``OR 0`` 等；排除 ``=0``/``=1``（如 ``1=0`` 恒假条件）以免
    # 生成 ``TRUE=0``。
    s = re.sub(r'(?i)\b(AND|OR)\s+0(?!=)', r'\1 FALSE', s)
    s = re.sub(r'(?i)\b(AND|OR)\s+1(?!=)', r'\1 TRUE', s)
    # plans.desc 是 PG 保留字，需加双引号。只引用「列名位置」的 desc（前接 `,`/`(`
    # 或表前缀），绝不引用 ``ORDER BY ... DESC`` 的排序关键字（前接 `)`/列名/数字）。
    s = re.sub(r'([,(]\s*)desc\b', r'\1"desc"', s)
    s = re.sub(r'(\w+\.)desc\b', r'\1"desc"', s)
    # INSERT OR IGNORE → PG 无此语法，等价 ON CONFLICT DO NOTHING（不指定冲突目标）
    if re.search(r'(?i)\bINSERT\s+OR\s+IGNORE\b', s):
        s = re.sub(r'(?i)\bINSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', s)
        s = re.sub(r';\s*$', '', s).rstrip() + ' ON CONFLICT DO NOTHING'
    # datetime('now', offset) → CURRENT_TIMESTAMP（演示数据的时间偏移忽略）
    s = re.sub(r"(?i)\bdatetime\s*\(\s*'now'(?:\s*,\s*'[^']*')?\s*\)", 'CURRENT_TIMESTAMP', s)
    return s

def _bind(params: Any) -> dict[str, Any]:
    """把位置参数元组转成 ``:pN`` 具名字典（供 SQLAlchemy 绑定）。"""
    if params is None:
        return {}
    if isinstance(params, dict):
        return params
    return {f'p{i}': v for i, v in enumerate(params)}


class Row(dict):
    """字典子类，同时支持 ``row['col']`` 与 ``row[0]``（按列顺序取第 N 列）。

    sqlite3.Row / SQLAlchemy 同步接口下访问单列常用 ``row[0]``、``row[1]``，
    异步迁移后用 list[dict] 表达结果，这里让 dict 行也支持整数下标，
    从而存量 ``row[0]`` 代码无需逐处改写。
    """

    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return super().__getitem__(k)
_engines: dict[Any, tuple[Any, Any]] = {}
_lock = threading.Lock()

def get_engine() -> Any:
    """获取（并缓存）postgresql 异步引擎。sqlite 回退路径不会用到。

    按**当前事件循环**缓存：asyncpg 连接绑定到创建它的事件循环，跨循环复用会
    触发 ``another operation is in progress``。测试/脚本中多次 ``asyncio.run``、
    以及应用启动时 ``init_db``（独立线程循环）与请求处理（主循环）属于不同循环，
    各自持有独立引擎即可（连的是同一个 PG 库，schema 共享）。

    同时用 ``id(loop)`` 快速索引 + ``loop is cached`` 身份校验，防止 CPython
    回收后 ``id`` 复用导致命中旧引擎的死连接。
    """
    url = settings.database_url
    try:
        loop: Any = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        key: Any = 'default'
    else:
        key = id(loop)

    if key in _engines:
        cached_loop, engine = _engines[key]
        if cached_loop is loop:
            return engine
        # id() 复用了但 loop 不同 → 旧引擎作废，丢弃连接池后替换
        try:
            engine.dispose()
        except Exception:
            pass

    engine = create_async_engine(url, future=True, pool_pre_ping=True)
    _engines[key] = (loop, engine)
    return engine

def _reset_engine() -> None:
    for _, (_, eng) in _engines.items():
        try:
            eng.dispose()
        except Exception:
            pass
    _engines.clear()

def _dispose_loop_engine(loop: Any) -> Any:
    """同步清掉指定事件循环缓存的引擎（不 await，仅在 loop 已关闭的清理场景用）。"""
    key = id(loop)
    entry = _engines.pop(key, None)
    if entry is None:
        return None
    _, eng = entry
    try:
        eng.dispose()
    except Exception:
        pass
    return None

async def _dispose_engine() -> None:
    """异步 dispose 所有缓存引擎并清空缓存（供 _run_async 临时循环结束后调用）。"""
    for _, (_, eng) in _engines.items():
        try:
            await eng.dispose()
        except Exception:
            pass
    _engines.clear()

class AsyncConn:
    """屏蔽 sqlite（同步连接 + to_thread）与 postgresql（异步连接）的差异。

    ``execute`` 均返回 ``list[dict]``，与 sqlite3.Row / SQLAlchemy RowMapping 解耦。
    """

    def __init__(self, conn: Any, is_async: bool) -> None:
        self._conn = conn
        self._is_async = is_async

    async def execute(self, sql: str, params: Any=None) -> list[dict[str, Any]]:
        if self._is_async:
            result = await self._conn.execute(text(normalize_sql(sql)), _bind(params))
            if result.returns_rows:
                return [Row(r._mapping) for r in result.fetchall()]
            return []
        conn = self._conn
        sql_s = normalize_sql(sql)
        params_s = params or ()

        def _run() -> list[dict[str, Any]]:
            cur = conn.execute(sql_s, params_s)
            if cur.description is None:
                return []
            cols = [d[0] for d in cur.description]
            return [Row(zip(cols, row, strict=True)) for row in cur.fetchall()]
        return await asyncio.to_thread(_run)

_pg_active: contextvars.ContextVar = contextvars.ContextVar('pg_active', default=None)

@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncConn]:
    """方言无关的异步事务上下文。

    - postgresql：用异步引擎开事务，退出时提交。**支持嵌套**：内层
      ``transaction()`` 复用外层同一连接/事务，避免嵌套查询看不到外层
      未提交数据（sqlite 用同一 ``get_conn()`` 天然可见，故一直正常）。
    - sqlite 回退：复用 ``db.get_conn()``（同一 WAL 连接），退出时 commit/rollback。
    """
    if dialect() == 'postgresql':
        cur = _pg_active.get()
        if cur is not None:
            conn, depth = cur
            _pg_active.set((conn, depth + 1))
            try:
                yield AsyncConn(conn, is_async=True)
            finally:
                _pg_active.set((conn, depth))
            return
        engine = get_engine()
        async with engine.connect() as conn:
            trans = await conn.begin()
            _pg_active.set((conn, 1))
            try:
                yield AsyncConn(conn, is_async=True)
                await trans.commit()
            except Exception:
                await trans.rollback()
                raise
            finally:
                _pg_active.set(None)
        return
    conn = sync_db.get_conn()
    try:
        yield AsyncConn(conn, is_async=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def _pg_create_table(sql: str) -> str:
    """把单条 sqlite 建表语句翻译为 PG 语法。

    - ``INTEGER PRIMARY KEY AUTOINCREMENT`` → ``IDENTITY``。
    - ``desc`` 是 PG 保留字（plans 表的列名），需加双引号转义；``description`` 不受影响。
      索引里的 ``DESC`` 排序关键字走 ``_INDEXES`` 分支、不经此函数，不会被误伤。
    """
    s = _AUTOINC_RE.sub('INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY', sql)
    # sqlite REAL 是 64 位浮点；PG REAL 是 32 位，直接建表会丢精度（如 22.6→22.60000038），
    # 故映射为 DOUBLE PRECISION 保持与 sqlite 一致的精度。
    s = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', s)
    s = re.sub('(?i)\\bdesc\\b', '"desc"', s)
    return s

async def _init_pg() -> None:
    """在 PostgreSQL 上建表（幂等，复用 db.py 的 ``_SCHEMA`` / ``_INDEXES`` / ``_ALTERS``）。

    翻译策略（与 sqlite 最终 schema 100% 一致）：
    - ``_SCHEMA``：逐条执行；``INTEGER PRIMARY KEY AUTOINCREMENT`` → ``IDENTITY``；
      跳过 ``PRAGMA``（PG 不需要）。
    - ``_INDEXES``：PG 原生支持，直接执行。
    - ``_ALTERS``：翻成 ``ADD COLUMN IF NOT EXISTS``（幂等；已存在的列自动跳过），
      从而把存量迁移列（username/password_hash/delivery_lat/...）补齐到全新 PG 库。
    """
    async with get_engine().begin() as conn:
        for raw in sync_db._SCHEMA.split(';'):
            stmt = raw.strip()
            if not stmt or stmt.upper().startswith('PRAGMA'):
                continue
            await conn.execute(text(_pg_create_table(stmt)))
        for raw in sync_db._INDEXES.split(';'):
            stmt = raw.strip()
            if not stmt:
                continue
            await conn.execute(text(stmt))
        for _table, _col, alter in sync_db._ALTERS:
            stmt = alter.replace('ADD COLUMN', 'ADD COLUMN IF NOT EXISTS', 1)
            await conn.execute(text(stmt))

async def init_db_async() -> None:
    """建表（幂等）。

    - sqlite 回退：直接复用现有同步 ``db.init_db()``（plain sqlite3 + 种子），
      保证 schema 与现状**完全一致**，避免重复维护 DDL。
    - postgresql：把 ``db.py`` 的交付级 schema 翻译后落到 PG（见 :func:`_init_pg`）。
    """
    if dialect() == 'postgresql':
        await _init_pg()
        logger.info('异步数据库初始化完成（dialect=postgresql）')
        return
    sync_db.init_db()
    logger.info('异步数据库初始化完成（dialect=%s）', dialect())
