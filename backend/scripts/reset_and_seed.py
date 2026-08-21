"""scripts/reset_and_seed.py —— 彻底重置数据库并注入最小演示数据集。

用法（先停后端 uvicorn 再执行）：
    python scripts/reset_and_seed.py          # 交互确认
    python scripts/reset_and_seed.py --yes    # 跳过确认

清理范围：全部业务表 DELETE（保留表结构与索引），含 users / sessions /
orders / diy_plans / reports 等所有数据；operations_config 一并清空
（读取侧有 DEFAULTS 兜底，接口行为不变）。

注入内容：
- 三类演示账号各一（与 AGENTS.md 一致）：
  - admin         / admin123456   role=admin    平台管理员
  - capri_demo    / 123456        role=merchant 绑定店铺 S001
  - customer_demo / 123456        role=user     C 端顾客
- 店铺 1 家：S001「跳舞兰·花艺工坊」（cover 占位图 + 商家智库档案）
- 分类 3 个 + 基础商品 10 种（单支玫瑰等基础花材，全部挂 S001 在售）
- 商品/店铺占位图写入 data/generated/（IMAGE_PROVIDER=mock 同款占位 PNG）

注意：init_db 已改为仅 plans 为空时才灌默认种子，本脚本注入的数据重启后端不会被覆盖。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.security import register_user, set_user_role  # noqa: E402
from backend.storage import tasks  # noqa: E402
from backend.storage.db import get_conn, init_db  # noqa: E402

#: 演示账号（username / password / nickname / role）
DEMO_ACCOUNTS = [
    ("admin", "admin123456", "平台管理员", "admin"),
    ("capri_demo", "123456", "花漾主理人", "merchant"),
    ("customer_demo", "123456", "小柔", "user"),
]

#: 店铺（capri_demo 绑定）
SHOP = {
    "id": "S001",
    "name": "跳舞兰·花艺工坊",
    "rating": 4.8,
    "distance_km": 0.8,
    "price_range": "5-50",
    "lat": 22.554,
    "lng": 114.237,
    "status": "营业中",
    "intro": "专注基础花材与日常鲜花的工作室，单支可售、新鲜直供。",
    "sales": 0,
    "min_delivery": 20,
    "delivery_fee": 3,
    "hours": "09:00-21:00",
    "address": "深圳市盐田区海山大道 88 号",
    "notice": "新店开业，全场基础花材每日到货。",
}

#: 商家智库档案（Agent 店铺推荐维度）
SHOP_PROFILE = {
    "shop_id": SHOP["id"],
    "brand_story": "社区里的基础花材工作室，坚持单支可售、按枝计价，让日常鲜花像买菜一样简单。",
    "price_level": "经济",
    "packaging": "牛皮纸 + 麻绳简约手包，突出花材本身。",
    "services": ["同城速递", "散花零售", "每周一花订阅"],
    "strengths": "基础花材齐全、价格亲民、新鲜直供",
    "keywords": "单支玫瑰,基础花材,平价,日常鲜花,盐田",
    "styles": [("S_NATURAL", 1), ("S_KOREAN", 2)],
    "scenes": [("SC_SELF", 1), ("SC_VALENTINE", 2), ("SC_MOTHER", 2)],
}

#: 分类（id / name / sort）
CATEGORIES = [
    ("cat_single", "单支花材", 1),
    ("cat_bouquet", "小型花束", 2),
    ("cat_green", "绿植盆栽", 3),
]

#: 基础商品 10 种（id / name / price / category_id / tags / style / desc / ai_reason）
PLANS = [
    ("P001", "单支红玫瑰", 9.9, "cat_single", ["红玫瑰", "单支", "经典"], "浪漫风",
     "经典红玫瑰单支，花头饱满，表达最直接的爱意。",
     "红玫瑰是爱意的经典表达，单支购买轻负担，适合日常随手传递心意。"),
    ("P002", "单支粉玫瑰", 9.9, "cat_single", ["粉玫瑰", "单支", "温柔"], "浪漫风",
     "温柔粉玫瑰单支，色调柔和，适合初次表白与日常问候。",
     "粉色系温柔不张扬，单支入手即可点亮心情，适合送给心仪的人或自己。"),
    ("P003", "单支香槟玫瑰", 12.0, "cat_single", ["香槟玫瑰", "单支", "高级"], "简约风",
     "香槟色玫瑰单支，奶油质感，低调而有品位。",
     "香槟色自带高级感，比红玫瑰更内敛，适合职场送礼与优雅场合。"),
    ("P004", "单支向日葵", 12.0, "cat_single", ["向日葵", "单支", "阳光"], "自然风",
     "向阳而生的向日葵单支，明黄大花头，治愈感满分。",
     "向日葵寓意积极向上，一支就能撑起整个房间的元气，适合鼓励与祝福场景。"),
    ("P005", "单支康乃馨", 5.9, "cat_single", ["康乃馨", "单支", "感恩"], "温馨风",
     "经典康乃馨单支，花期长，感恩母亲与长辈的首选。",
     "康乃馨是感恩的代名词，花期耐久好打理，母亲节与探望长辈都合适。"),
    ("P006", "单支郁金香", 15.0, "cat_single", ["郁金香", "单支", "优雅"], "简约风",
     "挺括郁金香单支，杯状花型，简约优雅的代表。",
     "郁金香线条干净利落，插瓶即成景，适合喜欢极简美学的你。"),
    ("P007", "单支香水百合", 18.0, "cat_single", ["百合", "单支", "浓香"], "自然风",
     "香水百合单支，花开带浓香，一瓶即满室芬芳。",
     "百合香气浓郁持久，单支就有很强的存在感，适合客厅与玄关摆放。"),
    ("P008", "满天星小花束", 39.0, "cat_bouquet", ["满天星", "花束", "百搭"], "简约风",
     "满天星小花束，云雾般轻盈，百搭不抢戏。",
     "满天星价格亲民又出片，单独送或搭配主花都合适，日常花束入门首选。"),
    ("P009", "尤加利叶配草束", 29.0, "cat_bouquet", ["尤加利", "绿叶", "北欧"], "自然风",
     "尤加利叶配草束，灰绿低饱和，北欧风桌面点缀。",
     "尤加利的灰绿色调安静高级，无花香不易过敏，适合办公桌与卧室。"),
    ("P010", "多肉植物组盆", 49.0, "cat_green", ["多肉", "组盆", "治愈"], "自然风",
     "三株多肉组盆，懒人友好，治愈系桌面绿植。",
     "多肉组盆好养耐旱，造型可爱，是送给新手与上班族的零门槛绿植礼物。"),
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def clear_all(conn) -> None:
    """DELETE 全部业务表数据（保留表结构）。"""
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%'"
        )
    ]
    # 先清带外键语义的明细表再清主表（SQLite 默认不强校验，顺序仅为输出可读）
    with conn:
        for t in sorted(tables):
            n = conn.execute(f"DELETE FROM {t}").rowcount
            print(f"  - {t}: 清空 {n} 行")


def seed_accounts() -> dict[str, str]:
    """注入三类演示账号，返回 username -> user_id。"""
    ids: dict[str, str] = {}
    for username, password, nickname, role in DEMO_ACCOUNTS:
        uid, _ = register_user(username, password, nickname)
        set_user_role(uid, role)
        ids[username] = uid
        print(f"  + {username} ({role}) -> {uid}")
    return ids


def seed_catalog_data(conn, merchant_uid: str) -> None:
    """注入店铺 / 分类 / 商品 / 智库档案 / 占位图。"""
    now = _now()
    cover = f"/generated/shop_{SHOP['id']}_cover.png"
    with conn:
        conn.execute(
            """INSERT INTO shops
               (id, name, rating, distance_km, price_range, lat, lng, status, intro,
                created_at, image, sales, min_delivery, delivery_fee, hours,
                address, notice, cover, logo, delivery_time)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                SHOP["id"], SHOP["name"], SHOP["rating"], SHOP["distance_km"],
                SHOP["price_range"], SHOP["lat"], SHOP["lng"], SHOP["status"],
                SHOP["intro"], now, cover, SHOP["sales"], SHOP["min_delivery"],
                SHOP["delivery_fee"], SHOP["hours"], SHOP["address"], SHOP["notice"],
                cover, None, "约25分钟",
            ),
        )
        conn.execute(
            "INSERT INTO merchant_shops(user_id, shop_id, created_at) VALUES (?,?,?)",
            (merchant_uid, SHOP["id"], now),
        )
        for cid, name, sort in CATEGORIES:
            conn.execute(
                "INSERT INTO categories(id, name, sort, created_at) VALUES (?,?,?,?)",
                (cid, name, sort, now),
            )
        for pid, name, price, cat, tags, style, desc, reason in PLANS:
            img = f"/generated/plan_{pid}.png"
            conn.execute(
                """INSERT INTO plans
                   (id, name, price, desc, effect_image_url, merchant_name, tags,
                    style, category_id, created_at, rating, sold, ai_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, name, price, desc, img, SHOP["name"],
                 json.dumps(tags, ensure_ascii=False), style, cat, now, 4.9, 0, reason),
            )
            conn.execute(
                "INSERT INTO shop_plans(shop_id, plan_id, status) VALUES (?,?,'on')",
                (SHOP["id"], pid),
            )
        p = SHOP_PROFILE
        conn.execute(
            """INSERT INTO shop_profiles
               (shop_id, brand_story, price_level, packaging, services, strengths,
                keywords, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (p["shop_id"], p["brand_story"], p["price_level"], p["packaging"],
             json.dumps(p["services"], ensure_ascii=False), p["strengths"],
             p["keywords"], now, now),
        )
        for sid, level in p["styles"]:
            conn.execute(
                "INSERT INTO shop_styles(shop_id, style_id, level) VALUES (?,?,?)",
                (p["shop_id"], sid, level),
            )
        for scid, level in p["scenes"]:
            conn.execute(
                "INSERT INTO shop_scenes(shop_id, scene_id, level) VALUES (?,?,?)",
                (p["shop_id"], scid, level),
            )
    print(f"  + 店铺 {SHOP['id']} {SHOP['name']}（绑定 capri_demo）")
    print(f"  + 分类 {len(CATEGORIES)} 个 / 商品 {len(PLANS)} 种（全部 S001 在售）")
    print("  + 商家智库档案 x1（styles/scenes/profile）")


def seed_images() -> None:
    """生成商品与店铺占位图（mock provider 同款 PNG）。"""
    for pid, *_rest in PLANS:
        tasks._write_mock_placeholder(f"plan_{pid}")
    tasks._write_mock_placeholder(f"shop_{SHOP['id']}_cover")
    print(f"  + 占位图 {len(PLANS) + 1} 张 -> data/generated/")


def main() -> None:
    if "--yes" not in sys.argv:
        ans = input("将删除全部业务数据并注入最小演示集，继续？[y/N] ").strip().lower()
        if ans != "y":
            print("已取消")
            return
    init_db()  # 建表/迁移（幂等）；plans 非空时不会灌默认种子
    conn = get_conn()
    print("== 1/3 全部业务表清空 ==")
    clear_all(conn)
    print("== 2/3 注入演示账号 ==")
    ids = seed_accounts()
    print("== 3/3 注入目录与智库 ==")
    seed_catalog_data(conn, ids["capri_demo"])
    seed_images()
    print("\n完成。启动后端即可使用：python -m uvicorn backend.api:app --host 127.0.0.1 --port 8080")


if __name__ == "__main__":
    main()
