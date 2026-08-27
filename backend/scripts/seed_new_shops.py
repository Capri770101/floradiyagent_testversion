"""scripts/seed_new_shops.py —— 注入 2 家新店（S017/S018）与新商品（P027+），含全链路关联。

幂等：全部 INSERT OR IGNORE / 逐条判断存在，可重复执行。
注入后跑 `python scripts/generate_plan_images.py` 为新商品/新店生成真实图，
脚本会自动回写 effect_image_url 与 shops.cover/logo/image。
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from backend.storage.db import get_conn, init_db

NEW_SHOPS = [{'shop_id': 'S017', 'name': '云栖花集(南山店)', 'distance_km': 3.2, 'price_range': '120-380', 'rating': 4.9, 'lat': 22.533, 'lng': 113.93, 'intro': '主打设计感花艺与高品质鲜切花，擅长韩式与法式花束，花材从云南空运直达。', 'notice': '情人节等节日订单较多，建议提前一天预订。', 'profile': {'brand_story': '南山脚下的小众花艺工作室，坚持「一束花一个故事」，主理人出身花艺设计科班，每束花都用心对待。', 'price_level': '中高端', 'packaging': '法式牛皮纸 + 缎带，配专属手提袋与养护卡。', 'services': '["同城速递", "企业花艺", "每周一花订阅", "花艺课程"]', 'strengths': '设计感强、花材新鲜直供、包装精致', 'keywords': '韩式花束,法式花艺,设计感,南山,云南直供'}, 'styles': [('S_KOREAN', 1), ('S_JAPANESE', 2)], 'scenes': [('SC_BIRTHDAY', 1), ('SC_VALENTINE', 2), ('SC_CONFESS', 2)], 'plan_ids': ['P027', 'P028', 'P029', 'P030']}, {'shop_id': 'S018', 'name': '拾光花房(福田店)', 'distance_km': 5.1, 'price_range': '60-220', 'rating': 4.7, 'lat': 22.543, 'lng': 114.057, 'intro': '社区暖心花店，平价好花，主打日常陪伴与治愈系花束，绿植盆栽丰富。', 'notice': '营业至 22:00，支持夜间配送。', 'profile': {'brand_story': '开在社区转角的小花房，让鲜花成为普通人日常生活的一部分，平价但不敷衍。', 'price_level': '经济实惠', 'packaging': '简约牛皮纸 + 麻绳，环保可降解材料。', 'services': '["同城速递", "散花零售", "绿植养护", "夜间配送"]', 'strengths': '价格亲民、绿植丰富、营业时间长', 'keywords': '平价花束,日常鲜花,绿植,治愈系,福田'}, 'styles': [('S_NATURAL', 1), ('S_JAPANESE', 2)], 'scenes': [('SC_SELF', 1), ('SC_GETWELL', 2), ('SC_HOUSEWARMING', 2)], 'plan_ids': ['P031', 'P032', 'P033', 'P034']}]
NEW_PLANS = [{'plan_id': 'P027', 'name': '香槟玫瑰韩式手捧', 'price': 268.0, 'desc': '9 支香槟玫瑰配尤加利叶，韩式雾面纸螺旋手捧，低饱和高级感，适合告白与纪念日。', 'merchant_name': '云栖花集', 'tags': ['韩式', '香槟玫瑰', '告白', '高级'], 'style': '韩式', 'category_id': 'cat_bouquet', 'rating': 4.9, 'sold': 186, 'ai_reason': '低饱和香槟色系 + 韩式留白包装，是告白与纪念日不出错的高级之选。'}, {'plan_id': 'P028', 'name': '洋桔梗雪纺新娘束', 'price': 358.0, 'desc': '白色洋桔梗与多头玫瑰混搭，雪纺缎带包裹，法式浪漫质感，婚礼与订婚仪式首选。', 'merchant_name': '云栖花集', 'tags': ['法式', '洋桔梗', '婚礼', '浪漫'], 'style': '法式', 'category_id': 'cat_bouquet', 'rating': 5.0, 'sold': 92, 'ai_reason': '白色洋桔梗 + 雪纺缎带的法式浪漫，适合婚礼、订婚等重要时刻。'}, {'plan_id': 'P029', 'name': '蝴蝶兰雅致礼盒', 'price': 428.0, 'desc': '两株白色蝴蝶兰配绿植点缀，木质礼盒高端大气，乔迁、开业与长辈探望的体面之选。', 'merchant_name': '云栖花集', 'tags': ['蝴蝶兰', '礼盒', '高端', '乔迁'], 'style': '中式', 'category_id': 'cat_bouquet', 'rating': 4.8, 'sold': 67, 'ai_reason': '蝴蝶兰礼盒雅致贵气，木质包装适合乔迁、开业、探望长辈。'}, {'plan_id': 'P030', 'name': '云栖限定晨雾花束', 'price': 198.0, 'desc': '当季鲜花随机搭配的限定款，蓝紫色调如晨雾般温柔，每束都是独一无二的设计。', 'merchant_name': '云栖花集', 'tags': ['限定', '混搭', '设计感', '清新'], 'style': '法式', 'category_id': 'cat_bouquet', 'rating': 4.9, 'sold': 143, 'ai_reason': '当季花材混搭的限定设计，蓝紫晨雾色调独特，适合追求个性与新鲜感的你。'}, {'plan_id': 'P031', 'name': '向日葵阳光花束', 'price': 89.0, 'desc': '5 支明黄向日葵配绿铃草，暖色牛皮纸包装，元气满满的治愈系花束，日常自购首选。', 'merchant_name': '拾光花房', 'tags': ['向日葵', '阳光', '治愈', '平价'], 'style': '自然', 'category_id': 'cat_bouquet', 'rating': 4.8, 'sold': 321, 'ai_reason': '明黄向日葵元气治愈，平价又好搭，是日常送自己与他人的暖心之选。'}, {'plan_id': 'P032', 'name': '雏菊野趣小花束', 'price': 59.0, 'desc': '小雏菊与满天星搭配的迷你花束，野趣清新，书桌与办公桌的点睛装饰。', 'merchant_name': '拾光花房', 'tags': ['雏菊', '野趣', '小清新', '平价'], 'style': '自然', 'category_id': 'cat_bouquet', 'rating': 4.6, 'sold': 208, 'ai_reason': '小雏菊野趣清新、价格亲民，适合书桌点缀与日常小惊喜。'}, {'plan_id': 'P033', 'name': '薄荷绿萝桌面盆栽', 'price': 45.0, 'desc': '水培绿萝配透明玻璃瓶，薄荷般清新，好养易活，新家与办公室的绿色小确幸。', 'merchant_name': '拾光花房', 'tags': ['绿萝', '绿植', '水培', '桌面'], 'style': '自然', 'category_id': 'cat_green', 'rating': 4.7, 'sold': 456, 'ai_reason': '水培绿萝好养清新，是乔迁新居与办公桌的百搭绿意。'}, {'plan_id': 'P034', 'name': '康乃馨暖心花束', 'price': 99.0, 'desc': '8 支粉色康乃馨配满天星，粉色雾面纸，表达感恩与牵挂，母亲节与探病慰问的温暖之选。', 'merchant_name': '拾光花房', 'tags': ['康乃馨', '母亲节', '感恩', '温馨'], 'style': '韩式', 'category_id': 'cat_bouquet', 'rating': 4.9, 'sold': 274, 'ai_reason': '粉色康乃馨配满天星，感恩温馨，母亲节与慰问探病都很合适。'}]
PLAN_BY_ID = {p['plan_id']: p for p in NEW_PLANS}

def _now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds')

def seed() -> None:
    conn = get_conn()
    with conn:
        for p in NEW_PLANS:
            exists = conn.execute('SELECT 1 FROM plans WHERE id=?', (p['plan_id'],)).fetchone()
            if exists:
                print(f"  跳过已存在商品 {p['plan_id']}")
                continue
            conn.execute('INSERT INTO plans\n                   (id, name, price, desc, effect_image_url, merchant_name, tags, style,\n                    category_id, rating, sold, ai_reason, created_at)\n                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (p['plan_id'], p['name'], p['price'], p['desc'], '/generated/plan_' + p['plan_id'] + '.png', p['merchant_name'], _json(p['tags']), p['style'], p['category_id'], p['rating'], p['sold'], p['ai_reason'], _now()))
            print(f"  + 商品 {p['plan_id']} {p['name']}")
        for s in NEW_SHOPS:
            exists = conn.execute('SELECT 1 FROM shops WHERE id=?', (s['shop_id'],)).fetchone()
            if exists:
                print(f"  跳过已存在店铺 {s['shop_id']}")
            else:
                m = s['price_range'].split('-')
                lo = int(m[0]) if m and m[0].strip().lstrip('-').isdigit() else None
                min_delivery = int(lo) // 10 * 10 if lo else 30
                delivery_fee = 3 if s['distance_km'] <= 1 else 5 if s['distance_km'] <= 2.5 else 8
                addr = f"深圳市{(s['intro'][:0] or '南山' if '南山' in s['name'] else '福田')}区海景路 {8 + abs(hash(s['shop_id'])) % 88} 号（示例地址）"
                conn.execute('INSERT INTO shops\n                       (id, name, rating, distance_km, price_range, lat, lng, status, intro,\n                        sales, min_delivery, delivery_fee, hours, delivery_time, address, notice,\n                        cover, image, logo, created_at)\n                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (s['shop_id'], s['name'], s['rating'], s['distance_km'], s['price_range'], s['lat'], s['lng'], '营业中', s['intro'], 150 + abs(hash(s['shop_id'])) % 500, min_delivery, delivery_fee, '09:00 - 22:00', f"约{int(10 + s['distance_km'] * 4)}分钟", addr, s['notice'], '/generated/shop_' + s['shop_id'] + '_cover.png', '/generated/shop_' + s['shop_id'] + '_cover.png', '/generated/shop_' + s['shop_id'] + '_logo.png', _now()))
                print(f"  + 店铺 {s['shop_id']} {s['name']}")
            for pid in s['plan_ids']:
                conn.execute("INSERT OR IGNORE INTO shop_plans(shop_id, plan_id, status) VALUES (?,?,'on')", (s['shop_id'], pid))
            if not conn.execute('SELECT 1 FROM shop_profiles WHERE shop_id=?', (s['shop_id'],)).fetchone():
                pf = s['profile']
                conn.execute('INSERT INTO shop_profiles\n                       (shop_id, brand_story, price_level, packaging, services, strengths, keywords, created_at, updated_at)\n                       VALUES (?,?,?,?,?,?,?,?,?)', (s['shop_id'], pf['brand_story'], pf['price_level'], pf['packaging'], pf['services'], pf['strengths'], pf['keywords'], _now(), _now()))
            for style_id, level in s['styles']:
                conn.execute('INSERT OR IGNORE INTO shop_styles(shop_id, style_id, level) VALUES (?,?,?)', (s['shop_id'], style_id, level))
            for scene_id, level in s['scenes']:
                conn.execute('INSERT OR IGNORE INTO shop_scenes(shop_id, scene_id, level) VALUES (?,?,?)', (s['shop_id'], scene_id, level))
            print(f"  + 关联 shop_plans/profile/styles/scenes for {s['shop_id']}")
        merchant = conn.execute("SELECT id FROM users WHERE username='capri_demo'").fetchone()
        if merchant:
            for s in NEW_SHOPS:
                conn.execute('INSERT OR IGNORE INTO merchant_shops(user_id, shop_id, created_at) VALUES (?,?,?)', (merchant['id'], s['shop_id'], _now()))
            print('  + 商家 capri_demo 绑定 S017/S018')

def _json(arr: list[str]) -> str:
    import json as _j
    return _j.dumps(arr, ensure_ascii=False)
if __name__ == '__main__':
    init_db()
    seed()
    print('完成。接下来运行: python scripts/generate_plan_images.py 为新商品/新店生成真实图片')
