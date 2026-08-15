"""storage/db.py —— SQLite 连接、事务封装与统一建表（交付级 schema）。

设计要点：
- SQLite 是同步库，不能在 async 里直接阻塞事件循环。本项目通过
  ``asyncio.to_thread`` 调用同步存储函数，配合「每线程独立连接」避免跨线程共享。
- 使用 WAL 模式 + busy_timeout，多个请求并发读写更稳。
- 所有建表在此集中维护，启动时调用 init_db() 即可（幂等 + 迁移兼容旧库）。

交付级数据模型（含电商 + 智能体记忆 + 多会话）：
- 用户/地址：users、addresses
- 商品目录：categories、plans、shops、shop_plans（多对多）
- 智能体记忆与多会话：sessions（= 会话，含 title/preview）、messages、session_flags、memories
- 电商交易：cart_items、orders、order_items、payments、reviews
- 任务：image_tasks

完整性策略：SQLite 外键在跨表删除/迁移时易踩坑，故不强制开启 PRAGMA foreign_keys，
改以「应用层维护引用 + 关键列建索引」保证可交付级性能与一致性；外键语义在
DDL 注释中明确标注，便于将来迁 Postgres/MySQL 时直接映射。
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

#: 建表语句（幂等：CREATE TABLE IF NOT EXISTS）
_SCHEMA = """
-- 用户（微信 openid 维度；H5 未登录时用本地生成的匿名 uid）
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,        -- 与 user_id 同值（openid 或匿名 uid）
    openid      TEXT UNIQUE,             -- 微信 openid（匿名用户为空）
    nickname    TEXT,
    avatar      TEXT,
    phone       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 商品分类
CREATE TABLE IF NOT EXISTS categories (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sort        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- 花艺方案（商品目录，DB 为唯一来源，init 时从种子数据灌入）
CREATE TABLE IF NOT EXISTS plans (
    id               TEXT PRIMARY KEY,           -- plan_id，如 P001
    name             TEXT NOT NULL,
    price            REAL NOT NULL DEFAULT 0,
    desc             TEXT,
    effect_image_url TEXT,
    merchant_name    TEXT,                       -- 示例商家名（用于购物车/下单归类展示）
    tags             TEXT,                       -- JSON 数组字符串
    style            TEXT,                       -- 风格，如 韩式/日式/田园
    category_id      TEXT,                       -- -> categories.id
    created_at       TEXT NOT NULL
);

-- 店铺
CREATE TABLE IF NOT EXISTS shops (
    id           TEXT PRIMARY KEY,               -- shop_id，如 S001
    name         TEXT NOT NULL,
    rating       REAL NOT NULL DEFAULT 0,
    distance_km  REAL,                           -- 静态距离（无定位时展示）
    price_range  TEXT,                           -- '100-300'
    lat          REAL,                           -- 经纬度，用于真实距离排序
    lng          REAL,
    status       TEXT NOT NULL DEFAULT '营业中',
    intro        TEXT,
    created_at   TEXT NOT NULL
);

-- 店铺-方案 多对多
CREATE TABLE IF NOT EXISTS shop_plans (
    shop_id  TEXT NOT NULL,
    plan_id  TEXT NOT NULL,
    PRIMARY KEY (shop_id, plan_id)
);

-- 会话（= 智能体一次对话；多会话由此表承载，title/preview 供前端列表展示）
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    stage       TEXT NOT NULL DEFAULT 'analyze',  -- 仅 UI 焦点高亮，不参与流程闸门
    requirement TEXT,                             -- 结构化需求 JSON
    title       TEXT,                             -- 会话标题（取首条用户消息）
    preview     TEXT,                             -- 列表预览（取最近一条消息摘要）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 消息（会话内消息；role 含 user/assistant/tool；ui/data 供前端回放结构化卡片）
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,                   -- -> sessions.session_id
    role         TEXT NOT NULL,
    content      TEXT,
    tool_calls   TEXT,                            -- assistant 工具调用列表，JSON 字符串
    tool_call_id TEXT,                            -- tool 回执对应的 tool_call_id（OpenAI 规范必填）
    ui           TEXT,                            -- 前端渲染类型，如 plan_card / text，JSON 字符串
    data         TEXT,                            -- 前端渲染数据，JSON 字符串
    created_at   TEXT NOT NULL
);

-- 会话级控制标记（一次性业务约束，如 image_confirmed）
CREATE TABLE IF NOT EXISTS session_flags (
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, session_id, key)
);

-- 长期记忆（用户偏好 KV：预算/对象/色系等）
CREATE TABLE IF NOT EXISTS memories (
    user_id TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

-- 购物车项（按 user_id 隔离）
CREATE TABLE IF NOT EXISTS cart_items (
    item_id    TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    plan_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    price      REAL NOT NULL,
    shop       TEXT,
    qty        INTEGER NOT NULL DEFAULT 1,
    selected   INTEGER NOT NULL DEFAULT 1,        -- 1=已勾选结算
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 订单
CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    plan_id        TEXT,
    plan_type      TEXT,
    shop_id        TEXT,
    items          TEXT,                          -- JSON 字符串（快照）
    total_price    REAL,
    status         TEXT NOT NULL DEFAULT 'created',  -- created|paid|shipped|done|canceled
    paid           INTEGER NOT NULL DEFAULT 0,    -- 0=未支付 1=已支付（兼容旧库）
    paid_at        TEXT,
    address_id     TEXT,                          -- -> addresses.id
    recipient_name  TEXT,
    recipient_phone TEXT,
    recipient_address TEXT,
    delivery_time  TEXT,
    note           TEXT,
    created_at     TEXT NOT NULL
);

-- 订单明细（与 orders.items 冗余，便于按方案统计/售后）
CREATE TABLE IF NOT EXISTS order_items (
    order_id  TEXT NOT NULL,
    plan_id   TEXT NOT NULL,
    name      TEXT NOT NULL,
    price     REAL NOT NULL,
    qty       INTEGER NOT NULL DEFAULT 1,
    shop      TEXT,
    PRIMARY KEY (order_id, plan_id)
);

-- 支付记录
CREATE TABLE IF NOT EXISTS payments (
    id            TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,                  -- -> orders.order_id
    method        TEXT NOT NULL,                 -- wechat|alipay|union|huabei
    amount        REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending|paid|failed|refunded
    transaction_id TEXT,                         -- 第三方交易号
    created_at    TEXT NOT NULL,
    paid_at       TEXT
);

-- 评价
CREATE TABLE IF NOT EXISTS reviews (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    plan_id    TEXT,
    order_id   TEXT,
    rating     INTEGER NOT NULL DEFAULT 5,
    content    TEXT,
    created_at TEXT NOT NULL
);

-- 生图任务
CREATE TABLE IF NOT EXISTS image_tasks (
    task_id    TEXT PRIMARY KEY,
    status     TEXT NOT NULL,                    -- pending|running|done|failed
    prompt     TEXT,
    result_url TEXT,
    created_at TEXT NOT NULL
);

-- 订单物流轨迹（时间线事件，按 seq 顺序回放）
CREATE TABLE IF NOT EXISTS order_logistics (
    order_id   TEXT NOT NULL,                    -- -> orders.order_id
    seq        INTEGER NOT NULL,                 -- 事件序号（0 起）
    text       TEXT NOT NULL,                    -- 事件描述（如「包裹已揽收」）
    created_at TEXT NOT NULL,
    PRIMARY KEY (order_id, seq)
);
"""

#: 索引（交付级查询性能）
_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_sessions_user        ON sessions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session     ON messages(session_id, id ASC);
CREATE INDEX IF NOT EXISTS idx_session_flags_sid    ON session_flags(session_id);
CREATE INDEX IF NOT EXISTS idx_cart_user            ON cart_items(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user          ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_items_order    ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order       ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_logistics_order      ON order_logistics(order_id);
CREATE INDEX IF NOT EXISTS idx_shop_plans_plan      ON shop_plans(plan_id);
CREATE INDEX IF NOT EXISTS idx_plans_category       ON plans(category_id);
"""

#: 旧库增量迁移：给已存在的表补缺失列（仅开发期存量数据需要）
_ALTERS = [
    # users: 账号密码体系（非微信注册/登录）
    ("users", "username", "ALTER TABLE users ADD COLUMN username TEXT"),
    ("users", "password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT"),
    # sessions: 会话列表展示字段
    ("sessions", "title", "ALTER TABLE sessions ADD COLUMN title TEXT"),
    ("sessions", "preview", "ALTER TABLE sessions ADD COLUMN preview TEXT"),
    # messages: 前端回放所需结构化字段
    ("messages", "ui", "ALTER TABLE messages ADD COLUMN ui TEXT"),
    ("messages", "data", "ALTER TABLE messages ADD COLUMN data TEXT"),
    # orders: 状态机/收货/备注
    ("orders", "status", "ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'created'"),
    ("orders", "paid_at", "ALTER TABLE orders ADD COLUMN paid_at TEXT"),
    ("orders", "address_id", "ALTER TABLE orders ADD COLUMN address_id TEXT"),
    ("orders", "recipient_name", "ALTER TABLE orders ADD COLUMN recipient_name TEXT"),
    ("orders", "recipient_phone", "ALTER TABLE orders ADD COLUMN recipient_phone TEXT"),
    ("orders", "recipient_address", "ALTER TABLE orders ADD COLUMN recipient_address TEXT"),
    ("orders", "delivery_time", "ALTER TABLE orders ADD COLUMN delivery_time TEXT"),
    ("orders", "note", "ALTER TABLE orders ADD COLUMN note TEXT"),
]


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
    """建表 + 索引 + 旧库迁移；应用启动时调用一次。"""
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.executescript(_INDEXES)
    # 兼容旧库：补齐缺失列（开发期存量数据）
    for table, col, ddl in _ALTERS:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:  # pragma: no cover
                logger.warning("迁移跳过 %s.%s: %s", table, col, exc)
    conn.commit()
    # 目录种子数据：首次启动（plans 为空）灌入示例方案/店铺，DB 成为唯一来源
    try:
        from storage import catalog

        catalog.seed_catalog()
    except Exception:  # pragma: no cover
        logger.warning("目录种子数据灌入失败（不影响记忆/交易表）", exc_info=True)
    logger.info("长期记忆数据库就绪: %s", settings.db_path)
