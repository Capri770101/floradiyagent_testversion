"""storage/db.py —— SQLite 连接、事务封装与统一建表（交付级 schema）。

设计要点：
- SQLite 是同步库，不能在 async 里直接阻塞事件循环。本项目通过
  ``asyncio.to_thread`` 调用同步存储函数，配合「每线程独立连接」避免跨线程共享。
- 使用 WAL 模式 + busy_timeout，多个请求并发读写更稳。
- 所有建表在此集中维护，启动时调用 init_db() 即可（幂等 + 迁移兼容旧库）。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from backend.config import settings

logger = logging.getLogger("db")

_thread_local = threading.local()

_SCHEMA = """
-- 用户（微信 openid 维度；H5 未登录时用本地生成的匿名 uid）
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    openid      TEXT UNIQUE,
    nickname    TEXT,
    avatar      TEXT,
    phone       TEXT,
    role        TEXT NOT NULL DEFAULT 'user',
    status      TEXT NOT NULL DEFAULT 'active',
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
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    price            REAL NOT NULL DEFAULT 0,
    desc             TEXT,
    effect_image_url TEXT,
    merchant_name    TEXT,
    tags             TEXT,
    style            TEXT,
    category_id      TEXT,
    rating           REAL NOT NULL DEFAULT 4.8,
    sold             INTEGER NOT NULL DEFAULT 0,
    ai_reason        TEXT,
    created_at       TEXT NOT NULL
);

-- 用户 DIY 方案资产库：只收录「用户确认过」的方案
CREATE TABLE IF NOT EXISTS diy_plans (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    fingerprint      TEXT NOT NULL,
    name             TEXT NOT NULL,
    requirement      TEXT,
    recipient        TEXT,
    occasion         TEXT,
    style            TEXT,
    budget           REAL,
    color_scheme     TEXT,
    flowers          TEXT,
    packaging        TEXT,
    meaning          TEXT,
    diy_steps        TEXT,
    care_tips        TEXT,
    card_message     TEXT,
    budget_breakdown TEXT,
    effect_image_url TEXT,
    difficulty       TEXT,
    est_time         INTEGER,
    shelf_life       TEXT,
    suitable_for     TEXT,
    caution          TEXT,
    mood_tags        TEXT,
    status           TEXT NOT NULL DEFAULT 'confirmed',
    order_count      INTEGER NOT NULL DEFAULT 0,
    source_user_id   TEXT,
    created_at       TEXT NOT NULL,
    confirmed_at     TEXT,
    UNIQUE (user_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_diy_plans_user ON diy_plans(user_id);

-- 店铺
CREATE TABLE IF NOT EXISTS shops (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    rating       REAL NOT NULL DEFAULT 0,
    distance_km  REAL,
    price_range  TEXT,
    lat          REAL,
    lng          REAL,
    status       TEXT NOT NULL DEFAULT '营业中',
    intro        TEXT,
    sales        INTEGER NOT NULL DEFAULT 0,
    min_delivery REAL NOT NULL DEFAULT 30,
    delivery_fee REAL NOT NULL DEFAULT 5,
    hours        TEXT NOT NULL DEFAULT '09:00 - 21:00',
    delivery_time TEXT NOT NULL DEFAULT '30分钟',
    address      TEXT,
    notice       TEXT,
    created_at   TEXT NOT NULL
);

-- 店铺-方案 多对多
CREATE TABLE IF NOT EXISTS shop_plans (
    shop_id  TEXT NOT NULL,
    plan_id  TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'on',
    PRIMARY KEY (shop_id, plan_id)
);

-- 商家-店铺 绑定
CREATE TABLE IF NOT EXISTS merchant_shops (
    user_id    TEXT NOT NULL,
    shop_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, shop_id)
);

-- 商家智库 · 主档（1:1 shops）
CREATE TABLE IF NOT EXISTS shop_profiles (
    shop_id     TEXT PRIMARY KEY,
    brand_story TEXT,
    price_level TEXT,
    packaging   TEXT,
    services    TEXT,
    strengths   TEXT,
    keywords    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 商家智库 · 风格（多对多）
CREATE TABLE IF NOT EXISTS shop_styles (
    shop_id  TEXT NOT NULL,
    style_id TEXT NOT NULL,
    level    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (shop_id, style_id)
);

-- 商家智库 · 场景（多对多）
CREATE TABLE IF NOT EXISTS shop_scenes (
    shop_id  TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    level    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (shop_id, scene_id)
);

-- 会话（= 智能体一次对话；多会话由此表承载）
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    stage       TEXT NOT NULL DEFAULT 'analyze',
    requirement TEXT,
    title       TEXT,
    preview     TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 消息（会话内消息；role 含 user/assistant/tool；ui/data 供前端回放结构化卡片）
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL,
    content      TEXT,
    tool_calls   TEXT,
    tool_call_id TEXT,
    ui           TEXT,
    data         TEXT,
    created_at   TEXT NOT NULL
);

-- 会话级控制标记（一次性业务约束）
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
    selected   INTEGER NOT NULL DEFAULT 1,
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
    items          TEXT,
    total_price    REAL,
    status         TEXT NOT NULL DEFAULT 'created',
    paid           INTEGER NOT NULL DEFAULT 0,
    paid_at        TEXT,
    expires_at     TEXT,
    address_id     TEXT,
    recipient_name  TEXT,
    recipient_phone TEXT,
    recipient_address TEXT,
    delivery_time  TEXT,
    note           TEXT,
    created_at     TEXT NOT NULL
);

-- 订单明细
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
    order_id      TEXT NOT NULL,
    method        TEXT NOT NULL,
    amount        REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    transaction_id TEXT,
    created_at    TEXT NOT NULL,
    paid_at       TEXT
);

-- 评价（商家可回复；管理后台可隐藏）
CREATE TABLE IF NOT EXISTS reviews (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    plan_id    TEXT,
    order_id   TEXT,
    rating     INTEGER NOT NULL DEFAULT 5,
    content    TEXT,
    created_at TEXT NOT NULL,
    reply      TEXT,
    reply_at   TEXT,
    status     TEXT NOT NULL DEFAULT 'visible'
);

-- 售后单
CREATE TABLE IF NOT EXISTS aftersales (
    id            TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    shop_id       TEXT,
    type          TEXT NOT NULL DEFAULT 'refund',
    reason        TEXT,
    description   TEXT,
    evidence_imgs TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    refund_amount REAL,
    review_note   TEXT,
    handled_by    TEXT,
    handled_at    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- 商家入驻申请
CREATE TABLE IF NOT EXISTS merchant_applications (
    id                TEXT PRIMARY KEY,
    applicant_user_id TEXT NOT NULL,
    shop_name         TEXT NOT NULL,
    contact_name      TEXT,
    contact_phone     TEXT,
    license_no        TEXT,
    license_img       TEXT,
    address           TEXT,
    intro             TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    review_note       TEXT,
    reviewed_by       TEXT,
    reviewed_at       TEXT,
    created_at        TEXT NOT NULL
);

-- 运营配置
CREATE TABLE IF NOT EXISTS operations_config (
    key        TEXT PRIMARY KEY,
    value      TEXT
);

-- 生图任务
CREATE TABLE IF NOT EXISTS image_tasks (
    task_id    TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    prompt     TEXT,
    result_url TEXT,
    created_at TEXT NOT NULL
);

-- 订单物流轨迹
CREATE TABLE IF NOT EXISTS order_logistics (
    order_id   TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (order_id, seq)
);

-- 收货地址（按用户隔离）
CREATE TABLE IF NOT EXISTS addresses (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    phone      TEXT NOT NULL,
    address    TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 收藏（方案收藏）
CREATE TABLE IF NOT EXISTS favorites (
    user_id    TEXT NOT NULL,
    plan_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, plan_id)
);

-- 优惠券
CREATE TABLE IF NOT EXISTS coupons (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    title      TEXT NOT NULL,
    discount   REAL NOT NULL,
    min_spend  REAL NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'unused',
    offer_id   TEXT,
    order_id   TEXT,
    created_at TEXT NOT NULL,
    used_at    TEXT
);

-- 领券中心 / 积分商城
CREATE TABLE IF NOT EXISTS coupon_offers (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    discount    REAL NOT NULL,
    min_spend   REAL NOT NULL DEFAULT 0,
    points_cost INTEGER NOT NULL DEFAULT 0,
    stock       INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

-- 积分账户 + 流水
CREATE TABLE IF NOT EXISTS user_points (
    user_id      TEXT PRIMARY KEY,
    balance      INTEGER NOT NULL DEFAULT 0,
    total_earned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS point_records (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    delta      INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    order_id   TEXT,
    created_at TEXT NOT NULL
);

-- 商家-顾客会话
CREATE TABLE IF NOT EXISTS shop_chats (
    id             TEXT PRIMARY KEY,
    shop_id        TEXT NOT NULL,
    user_id        TEXT NOT NULL,
    last_msg       TEXT,
    last_at        TEXT,
    unread_user    INTEGER NOT NULL DEFAULT 0,
    unread_merchant INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    UNIQUE (shop_id, user_id)
);

-- 会话消息
CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    chat_id    TEXT NOT NULL,
    sender     TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 站内消息通知中心
CREATE TABLE IF NOT EXISTS notifications (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    type         TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    ref_type     TEXT,
    ref_id       TEXT,
    push_channel TEXT NOT NULL DEFAULT 'inbox',
    is_read      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

-- 内容举报
CREATE TABLE IF NOT EXISTS reports (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    TEXT NOT NULL,
    reason       TEXT NOT NULL,
    content      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    handled_at   TEXT,
    handled_by   TEXT,
    created_at   TEXT NOT NULL
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_sessions_user        ON sessions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session     ON messages(session_id, id ASC);
CREATE INDEX IF NOT EXISTS idx_session_flags_sid    ON session_flags(session_id);
CREATE INDEX IF NOT EXISTS idx_cart_user            ON cart_items(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user          ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_items_order    ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order       ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_logistics_order      ON order_logistics(order_id);
CREATE INDEX IF NOT EXISTS idx_coupons_user          ON coupons(user_id, status);
CREATE INDEX IF NOT EXISTS idx_point_records_user    ON point_records(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_addresses_user        ON addresses(user_id, is_default);
CREATE INDEX IF NOT EXISTS idx_shop_plans_plan      ON shop_plans(plan_id);
CREATE INDEX IF NOT EXISTS idx_merchant_shops_shop  ON merchant_shops(shop_id);
CREATE INDEX IF NOT EXISTS idx_plans_category       ON plans(category_id);
CREATE INDEX IF NOT EXISTS idx_shop_styles_style    ON shop_styles(style_id);
CREATE INDEX IF NOT EXISTS idx_shop_scenes_scene    ON shop_scenes(scene_id);
CREATE INDEX IF NOT EXISTS idx_chats_shop           ON shop_chats(shop_id, last_at DESC);
CREATE INDEX IF NOT EXISTS idx_chats_user           ON shop_chats(user_id, last_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat   ON chat_messages(chat_id, id ASC);
CREATE INDEX IF NOT EXISTS idx_notifications_user   ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_status       ON reports(status, created_at DESC);
"""

_ALTERS = [
    ("users", "username", "ALTER TABLE users ADD COLUMN username TEXT"),
    ("users", "password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT"),
    ("users", "role", "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"),
    ("sessions", "title", "ALTER TABLE sessions ADD COLUMN title TEXT"),
    ("sessions", "preview", "ALTER TABLE sessions ADD COLUMN preview TEXT"),
    ("messages", "ui", "ALTER TABLE messages ADD COLUMN ui TEXT"),
    ("messages", "data", "ALTER TABLE messages ADD COLUMN data TEXT"),
    ("orders", "status", "ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'created'"),
    ("orders", "paid_at", "ALTER TABLE orders ADD COLUMN paid_at TEXT"),
    ("orders", "address_id", "ALTER TABLE orders ADD COLUMN address_id TEXT"),
    ("orders", "recipient_name", "ALTER TABLE orders ADD COLUMN recipient_name TEXT"),
    ("orders", "recipient_phone", "ALTER TABLE orders ADD COLUMN recipient_phone TEXT"),
    ("orders", "recipient_address", "ALTER TABLE orders ADD COLUMN recipient_address TEXT"),
    ("orders", "delivery_time", "ALTER TABLE orders ADD COLUMN delivery_time TEXT"),
    ("orders", "note", "ALTER TABLE orders ADD COLUMN note TEXT"),
    ("orders", "coupon_id", "ALTER TABLE orders ADD COLUMN coupon_id TEXT"),
    ("orders", "discount", "ALTER TABLE orders ADD COLUMN discount REAL NOT NULL DEFAULT 0"),
    ("orders", "expires_at", "ALTER TABLE orders ADD COLUMN expires_at TEXT"),
    ("coupons", "offer_id", "ALTER TABLE coupons ADD COLUMN offer_id TEXT"),
    ("shop_plans", "status", "ALTER TABLE shop_plans ADD COLUMN status TEXT NOT NULL DEFAULT 'on'"),
    ("shops", "image", "ALTER TABLE shops ADD COLUMN image TEXT"),
    ("plans", "rating", "ALTER TABLE plans ADD COLUMN rating REAL NOT NULL DEFAULT 4.8"),
    ("plans", "sold", "ALTER TABLE plans ADD COLUMN sold INTEGER NOT NULL DEFAULT 0"),
    ("plans", "ai_reason", "ALTER TABLE plans ADD COLUMN ai_reason TEXT"),
    ("shops", "sales", "ALTER TABLE shops ADD COLUMN sales INTEGER NOT NULL DEFAULT 0"),
    ("shops", "min_delivery", "ALTER TABLE shops ADD COLUMN min_delivery REAL NOT NULL DEFAULT 30"),
    ("shops", "delivery_fee", "ALTER TABLE shops ADD COLUMN delivery_fee REAL NOT NULL DEFAULT 5"),
    ("shops", "hours", "ALTER TABLE shops ADD COLUMN hours TEXT NOT NULL DEFAULT '09:00 - 21:00'"),
    ("shops", "delivery_time", "ALTER TABLE shops ADD COLUMN delivery_time TEXT NOT NULL DEFAULT '30分钟'"),
    ("shops", "address", "ALTER TABLE shops ADD COLUMN address TEXT"),
    ("shops", "notice", "ALTER TABLE shops ADD COLUMN notice TEXT"),
    ("shops", "cover", "ALTER TABLE shops ADD COLUMN cover TEXT"),
    ("shops", "logo", "ALTER TABLE shops ADD COLUMN logo TEXT"),
    ("reviews", "reply", "ALTER TABLE reviews ADD COLUMN reply TEXT"),
    ("reviews", "reply_at", "ALTER TABLE reviews ADD COLUMN reply_at TEXT"),
    ("users", "status", "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"),
    ("reviews", "status", "ALTER TABLE reviews ADD COLUMN status TEXT NOT NULL DEFAULT 'visible'"),
    ("diy_plans", "difficulty", "ALTER TABLE diy_plans ADD COLUMN difficulty TEXT"),
    ("diy_plans", "est_time", "ALTER TABLE diy_plans ADD COLUMN est_time INTEGER"),
    ("diy_plans", "shelf_life", "ALTER TABLE diy_plans ADD COLUMN shelf_life TEXT"),
    ("diy_plans", "suitable_for", "ALTER TABLE diy_plans ADD COLUMN suitable_for TEXT"),
    ("diy_plans", "caution", "ALTER TABLE diy_plans ADD COLUMN caution TEXT"),
    ("diy_plans", "mood_tags", "ALTER TABLE diy_plans ADD COLUMN mood_tags TEXT"),
    ("diy_plans", "source_user_id", "ALTER TABLE diy_plans ADD COLUMN source_user_id TEXT"),
]


def get_conn() -> sqlite3.Connection:
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
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.executescript(_INDEXES)
    for table, col, ddl in _ALTERS:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                logger.warning("%s.%s: %s", table, col, exc)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) "
            "WHERE phone IS NOT NULL AND phone != ''"
        )
    except sqlite3.OperationalError as exc:
        logger.warning("users.phone unique index failed, degraded: %s", exc)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone) "
            "WHERE phone IS NOT NULL AND phone != ''"
        )
    conn.commit()
    try:
        from backend.storage import catalog
        plans_n = conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        if plans_n == 0:
            catalog.seed_catalog()
    except Exception:
        logger.warning("Seed data failed", exc_info=True)
    logger.info("DB ready: %s", settings.db_path)
