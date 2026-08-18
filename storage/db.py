"""storage/db.py —— SQLite 连接、事务封装与统一建表（交付级 schema）。

设计要点：
- SQLite 是同步库，不能在 async 里直接阻塞事件循环。本项目通过
  ``asyncio.to_thread`` 调用同步存储函数，配合「每线程独立连接」避免跨线程共享。
- 使用 WAL 模式 + busy_timeout，多个请求并发读写更稳。
- 所有建表在此集中维护，启动时调用 init_db() 即可（幂等 + 迁移兼容旧库）。

交付级数据模型（含电商 + 智能体记忆 + 多会话）：
- 用户/地址：users、addresses
- 商品目录：categories、plans、shops、shop_plans（多对多）
- 商家智库：shop_profiles（1:1 档案）、shop_styles / shop_scenes（风格/场景多对多，供 AI 检索）
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
    role        TEXT NOT NULL DEFAULT 'user',  -- user | merchant | admin（权限模型）
    status      TEXT NOT NULL DEFAULT 'active', -- active | banned（管理后台禁用）
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
    rating           REAL NOT NULL DEFAULT 4.8,  -- 评分（种子/商家后台维护，上线前可清空重灌）
    sold             INTEGER NOT NULL DEFAULT 0, -- 已售（种子演示值，正式上线由订单统计）
    ai_reason        TEXT,                       -- 推荐理由（种子/商家后台维护，详情页 aiReason 来源）
    created_at       TEXT NOT NULL
);

-- 用户 DIY 方案资产库：只收录「用户确认过」的方案（确认→confirmed，成交→ordered）；
-- 按 user_id + 内容指纹去重，同一用户同一配方不重复落库
CREATE TABLE IF NOT EXISTS diy_plans (
    id               TEXT PRIMARY KEY,           -- plan_id，如 DIY_1a2b3c
    user_id          TEXT NOT NULL,
    fingerprint      TEXT NOT NULL,              -- 内容指纹（花材/角色/风格/对象/预算/包装）
    name             TEXT NOT NULL,
    requirement      TEXT,                       -- 原始需求文本（学习/复用输入）
    recipient        TEXT,
    occasion         TEXT,
    style            TEXT,
    budget           REAL,
    color_scheme     TEXT,                       -- JSON 数组
    flowers          TEXT,                       -- JSON [{bucket,name,ratio}]
    packaging        TEXT,
    meaning          TEXT,
    diy_steps        TEXT,                       -- JSON 数组
    care_tips        TEXT,
    card_message     TEXT,
    budget_breakdown TEXT,                       -- JSON 对象
    effect_image_url TEXT,
    status           TEXT NOT NULL DEFAULT 'confirmed',
    order_count      INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    confirmed_at     TEXT,
    UNIQUE (user_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_diy_plans_user ON diy_plans(user_id);

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
    -- 经营信息（种子/商家后台维护；正式上线由经营数据统计，上线前可清空重灌）
    sales        INTEGER NOT NULL DEFAULT 0,     -- 月售
    min_delivery REAL NOT NULL DEFAULT 30,       -- 起送价（元）
    delivery_fee REAL NOT NULL DEFAULT 5,        -- 配送费（元）
    hours        TEXT NOT NULL DEFAULT '09:00 - 21:00',  -- 营业时间
    delivery_time TEXT NOT NULL DEFAULT '30分钟',  -- 配送时长（详情页展示，商家后台维护）
    address      TEXT,                           -- 门店地址
    notice       TEXT,                           -- 公告
    created_at   TEXT NOT NULL
);

-- 店铺-方案 多对多
CREATE TABLE IF NOT EXISTS shop_plans (
    shop_id  TEXT NOT NULL,
    plan_id  TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'on',        -- on=在售 off=已下架（商家端上下架）
    PRIMARY KEY (shop_id, plan_id)
);

-- 商家-店铺 绑定（商家后台按店隔离的权限来源；admin 不受限）
CREATE TABLE IF NOT EXISTS merchant_shops (
    user_id    TEXT NOT NULL,                   -- users.id
    shop_id    TEXT NOT NULL,                   -- shops.id
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, shop_id)
);

-- 商家智库 · 主档（1:1 shops）：以商家为单位沉淀品牌定位/风格/能力等知识，
-- 供 AI 检索（query_knowledge 的 shop 域）与店铺详情页展示
CREATE TABLE IF NOT EXISTS shop_profiles (
    shop_id     TEXT PRIMARY KEY,               -- -> shops.id
    brand_story TEXT,                           -- 品牌故事 / 定位（自然语言档案）
    price_level TEXT,                           -- 经济 | 中端 | 高端 | 轻奢
    packaging   TEXT,                           -- 包装特色（自然语言）
    services    TEXT,                           -- JSON 数组：服务能力（同城速递/宴会布置/花艺课…）
    strengths   TEXT,                           -- 卖点 / 特色（自然语言，供向量检索）
    keywords    TEXT,                           -- 运营补充关键词（逗号分隔，供关键词命中）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 商家智库 · 风格（多对多，style_id 引用 knowledge/styles.json 的 S_* 主风格 id）
CREATE TABLE IF NOT EXISTS shop_styles (
    shop_id  TEXT NOT NULL,                     -- -> shops.id
    style_id TEXT NOT NULL,                     -- S_KOREAN / S_NORDIC / ...
    level    INTEGER NOT NULL DEFAULT 1,        -- 1=主打 2=次要
    PRIMARY KEY (shop_id, style_id)
);

-- 商家智库 · 场景（多对多，scene_id 引用 knowledge/scenes.json 的 SC_* 场景 id）
CREATE TABLE IF NOT EXISTS shop_scenes (
    shop_id  TEXT NOT NULL,                     -- -> shops.id
    scene_id TEXT NOT NULL,                     -- SC_VALENTINE / SC_WEDDING / ...
    level    INTEGER NOT NULL DEFAULT 1,        -- 1=擅长 2=可做
    PRIMARY KEY (shop_id, scene_id)
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
    expires_at     TEXT,                          -- 支付超时时间（created/pending_payment 过期自动取消）
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

-- 评价（商家可回复：reply/reply_at；管理后台可隐藏：status）
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
    status     TEXT NOT NULL DEFAULT 'visible'  -- visible | hidden（管理后台审核）
);

-- 售后单（M4：用户发起退款/退货/换货，管理员审核并触发 sandbox 退款）
CREATE TABLE IF NOT EXISTS aftersales (
    id            TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    shop_id       TEXT,
    type          TEXT NOT NULL DEFAULT 'refund',   -- refund|return|exchange
    reason        TEXT,
    description   TEXT,
    evidence_imgs TEXT,                             -- JSON 数组（图片路径）
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|refunded|closed
    refund_amount REAL,
    review_note   TEXT,                             -- 审核备注（拒绝原因等）
    handled_by    TEXT,
    handled_at    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- 商家入驻申请（M5：用户提交执照等，管理员审核通过后提权并创建店铺）
CREATE TABLE IF NOT EXISTS merchant_applications (
    id                TEXT PRIMARY KEY,
    applicant_user_id TEXT NOT NULL,                -- 申请人 users.id
    shop_name         TEXT NOT NULL,
    contact_name      TEXT,
    contact_phone     TEXT,
    license_no        TEXT,
    license_img       TEXT,                         -- 执照图片路径
    address           TEXT,
    intro             TEXT,
    status            TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected
    review_note       TEXT,
    reviewed_by       TEXT,
    reviewed_at       TEXT,
    created_at        TEXT NOT NULL
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

-- 收货地址（按用户隔离；仅一个默认地址）
CREATE TABLE IF NOT EXISTS addresses (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,                 -- 收货人
    phone      TEXT NOT NULL,
    address    TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,    -- 1=默认（同用户仅一条）
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 收藏（方案收藏，按用户隔离；user+plan 唯一）
CREATE TABLE IF NOT EXISTS favorites (
    user_id    TEXT NOT NULL,
    plan_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, plan_id)
);

-- 优惠券（按用户隔离；下单时抵扣，status: unused|used）
CREATE TABLE IF NOT EXISTS coupons (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    title      TEXT NOT NULL,
    discount   REAL NOT NULL,                    -- 抵扣金额（元）
    min_spend  REAL NOT NULL DEFAULT 0,          -- 满减门槛（0 表示无门槛）
    status     TEXT NOT NULL DEFAULT 'unused',   -- unused|used
    offer_id   TEXT,                             -- 来源（领券中心 offer，可选）
    order_id   TEXT,                             -- 使用后关联的订单
    created_at TEXT NOT NULL,
    used_at    TEXT
);

-- 领券中心 / 积分商城：可领取/可兑换的券模板
CREATE TABLE IF NOT EXISTS coupon_offers (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    discount    REAL NOT NULL,                   -- 抵扣金额（元）
    min_spend   REAL NOT NULL DEFAULT 0,         -- 满减门槛
    points_cost INTEGER NOT NULL DEFAULT 0,      -- 0=免费领取；>0=积分兑换
    stock       INTEGER NOT NULL DEFAULT 0,      -- 剩余库存（-1=不限）
    active      INTEGER NOT NULL DEFAULT 1,      -- 是否上架
    created_at  TEXT NOT NULL
);

-- 积分账户 + 流水（支付成功按金额 1:1 发放，如 ¥99 → 99 分）
CREATE TABLE IF NOT EXISTS user_points (
    user_id      TEXT PRIMARY KEY,
    balance      INTEGER NOT NULL DEFAULT 0,
    total_earned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS point_records (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    delta      INTEGER NOT NULL,                 -- 正=获得 负=消费
    reason     TEXT NOT NULL,
    order_id   TEXT,
    created_at TEXT NOT NULL
);

-- 商家-顾客会话（按店铺+顾客唯一；未读数分侧维护）
CREATE TABLE IF NOT EXISTS shop_chats (
    id             TEXT PRIMARY KEY,
    shop_id        TEXT NOT NULL,                -- -> shops.id
    user_id        TEXT NOT NULL,                -- -> users.id（顾客）
    last_msg       TEXT,                         -- 最后一条消息摘要（会话列表展示）
    last_at        TEXT,                         -- 最后消息时间
    unread_user    INTEGER NOT NULL DEFAULT 0,   -- 顾客侧未读数（商家回复后 +1）
    unread_merchant INTEGER NOT NULL DEFAULT 0,  -- 商家侧未读数（顾客发言后 +1）
    created_at     TEXT NOT NULL,
    UNIQUE (shop_id, user_id)
);

-- 会话消息（sender: user=顾客 | merchant=商家）
CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    chat_id    TEXT NOT NULL,                    -- -> shop_chats.id
    sender     TEXT NOT NULL,                    -- user|merchant
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
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
"""

#: 旧库增量迁移：给已存在的表补缺失列（仅开发期存量数据需要）
_ALTERS = [
    # users: 账号密码体系（非微信注册/登录）
    ("users", "username", "ALTER TABLE users ADD COLUMN username TEXT"),
    ("users", "password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT"),
    # users: 角色权限（user | merchant | admin）
    ("users", "role", "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"),
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
    # orders: 优惠券抵扣
    ("orders", "coupon_id", "ALTER TABLE orders ADD COLUMN coupon_id TEXT"),
    ("orders", "discount", "ALTER TABLE orders ADD COLUMN discount REAL NOT NULL DEFAULT 0"),
    # orders: 支付超时（懒过期自动取消）
    ("orders", "expires_at", "ALTER TABLE orders ADD COLUMN expires_at TEXT"),
    # coupons: 领券中心来源标记
    ("coupons", "offer_id", "ALTER TABLE coupons ADD COLUMN offer_id TEXT"),
    # shop_plans: 店铺内商品上下架（商家端管理；C 端仅展示 on）
    (
        "shop_plans",
        "status",
        "ALTER TABLE shop_plans ADD COLUMN status TEXT NOT NULL DEFAULT 'on'",
    ),
    # shops: 商家上传的店铺图片（/uploads/...）
    ("shops", "image", "ALTER TABLE shops ADD COLUMN image TEXT"),
    # plans: 评分/已售（种子演示值，上线前可清空；正式由订单统计）
    ("plans", "rating", "ALTER TABLE plans ADD COLUMN rating REAL NOT NULL DEFAULT 4.8"),
    ("plans", "sold", "ALTER TABLE plans ADD COLUMN sold INTEGER NOT NULL DEFAULT 0"),
    # plans: 推荐理由（详情页 aiReason 展示，种子/商家后台维护）
    ("plans", "ai_reason", "ALTER TABLE plans ADD COLUMN ai_reason TEXT"),
    # shops: 经营信息（月售/起送/配送费/营业时间/地址/公告）
    ("shops", "sales", "ALTER TABLE shops ADD COLUMN sales INTEGER NOT NULL DEFAULT 0"),
    ("shops", "min_delivery", "ALTER TABLE shops ADD COLUMN min_delivery REAL NOT NULL DEFAULT 30"),
    ("shops", "delivery_fee", "ALTER TABLE shops ADD COLUMN delivery_fee REAL NOT NULL DEFAULT 5"),
    ("shops", "hours", "ALTER TABLE shops ADD COLUMN hours TEXT NOT NULL DEFAULT '09:00 - 21:00'"),
    ("shops", "delivery_time", "ALTER TABLE shops ADD COLUMN delivery_time TEXT NOT NULL DEFAULT '30分钟'"),
    ("shops", "address", "ALTER TABLE shops ADD COLUMN address TEXT"),
    ("shops", "notice", "ALTER TABLE shops ADD COLUMN notice TEXT"),
    # shops: 店铺装修（封面横幅 / Logo，商家端上传，/uploads/...）
    ("shops", "cover", "ALTER TABLE shops ADD COLUMN cover TEXT"),
    ("shops", "logo", "ALTER TABLE shops ADD COLUMN logo TEXT"),
    # reviews: 商家回复评价（商家中心新增能力）
    ("reviews", "reply", "ALTER TABLE reviews ADD COLUMN reply TEXT"),
    ("reviews", "reply_at", "ALTER TABLE reviews ADD COLUMN reply_at TEXT"),
    # users: 管理后台禁用（active|banned）
    ("users", "status", "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"),
    # reviews: 管理后台隐藏（visible|hidden）
    ("reviews", "status", "ALTER TABLE reviews ADD COLUMN status TEXT NOT NULL DEFAULT 'visible'"),
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
