"""tools_enhanced.py —— 增强工具集：搜索、天气、节日、价格查询。

为花卉智能体提供外部信息获取能力，类似 OpenCode 的 websearch/webfetch。
这些工具让智能体能够获取实时信息，做出更精准的推荐。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from agent.tools import register_tool

logger = logging.getLogger('tools_enhanced')

# ---- 花卉知识搜索工具 ----

@register_tool(
    name='search_flower_knowledge',
    description='搜索花卉知识库：花期、花语、养护方法、搭配建议。支持按名称、花语、场合搜索。',
    parameters={
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': '搜索关键词（如：玫瑰花语、母亲节送什么花、百合养护）'},
            'search_type': {'type': 'string', 'enum': ['name', 'language', 'occasion', 'care'], 'description': '搜索类型：name=按名称, language=按花语, occasion=按场合, care=按养护方法'}
        },
        'required': ['query']
    }
)
def search_flower_knowledge(query: str, search_type: str = 'name') -> list[dict]:
    """搜索花卉知识库，返回匹配的花卉信息。"""
    from agent.knowledge.store import query_knowledge
    
    try:
        # 使用现有的知识库查询
        result = query_knowledge(domain='flower', query=query)
        results = result.get('results', [])
        
        # 根据搜索类型过滤和排序
        filtered = []
        for flower in results:
            score = 0
            if search_type == 'name' and query.lower() in flower.get('name', '').lower():
                score += 10
            elif search_type == 'language' and any(query in lang for lang in flower.get('flower_language', [])):
                score += 10
            elif search_type == 'occasion' and query in flower.get('tags', []):
                score += 10
            elif search_type == 'care' and query in flower.get('pairing_notes', ''):
                score += 10
            
            # 基础匹配分数
            if query.lower() in flower.get('name', '').lower() or \
               any(query in alias for alias in flower.get('aliases', [])):
                score += 5
            
            if score > 0:
                filtered.append((score, flower))
        
        # 按分数排序
        filtered.sort(key=lambda x: x[0], reverse=True)
        
        return [flower for _, flower in filtered[:5]]
    
    except Exception as e:
        logger.error(f'花卉知识搜索失败: {e}')
        return []


# ---- 天气查询工具 ----

@register_tool(
    name='get_weather',
    description='获取当前天气信息，用于推荐适合的花卉（如雨天推荐室内花，夏天推荐耐热花）。支持主要城市。',
    parameters={
        'type': 'object',
        'properties': {
            'city': {'type': 'string', 'description': '城市名（如：北京、上海、广州）'}
        },
        'required': []
    }
)
def get_weather(city: str = '北京') -> dict:
    """获取天气信息，返回天气状况和花卉推荐建议。"""
    try:
        # 使用 wttr.in 免费天气 API
        url = f'https://wttr.in/{city}?format=j1'
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = loop.run_in_executor(pool, lambda: httpx.get(url, timeout=10))
        except RuntimeError:
            response = httpx.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        current = data.get('current_condition', [{}])[0]
        
        weather_info = {
            'city': city,
            'temp_c': current.get('temp_C', '未知'),
            'weather': current.get('weatherDesc', [{}])[0].get('value', '未知'),
            'humidity': current.get('humidity', '未知'),
            'wind_speed': current.get('windspeedKmph', '未知'),
            'flower_suggestions': []
        }
        
        # 根据天气给出花卉推荐建议
        temp = int(current.get('temp_C', 20))
        humidity = int(current.get('humidity', 50))
        weather_desc = current.get('weatherDesc', [{}])[0].get('value', '').lower()
        
        if temp > 30:
            weather_info['flower_suggestions'].append('天气炎热，推荐耐热花材：向日葵、非洲菊、康乃馨')
        elif temp < 10:
            weather_info['flower_suggestions'].append('天气较冷，推荐室内摆放：百合、郁金香、洋桔梗')
        
        if 'rain' in weather_desc or '雨' in weather_desc:
            weather_info['flower_suggestions'].append('下雨天，推荐室内花束，避免鲜花淋雨')
        
        if humidity > 80:
            weather_info['flower_suggestions'].append('湿度较高，鲜花保鲜期较长，可选择花瓣较多的花材')
        elif humidity < 30:
            weather_info['flower_suggestions'].append('天气干燥，建议选择耐旱花材，并注意勤换水')
        
        if not weather_info['flower_suggestions']:
            weather_info['flower_suggestions'].append('天气适宜，大多数花材都适合')
        
        return weather_info
    
    except Exception as e:
        logger.error(f'天气查询失败: {e}')
        return {
            'city': city,
            'temp_c': '未知',
            'weather': '未知',
            'flower_suggestions': ['无法获取天气信息，推荐经典花材：玫瑰、百合、康乃馨']
        }


# ---- 节日日历工具 ----

# 中国常见节日和纪念日
HOLIDAYS = [
    # 公历节日
    {'name': '元旦', 'date': '01-01', 'tags': ['新年', '祝福'], 'suggested_flowers': ['百合', '向日葵', '玫瑰']},
    {'name': '情人节', 'date': '02-14', 'tags': ['爱情', '浪漫'], 'suggested_flowers': ['红玫瑰', '满天星', '勿忘我']},
    {'name': '妇女节', 'date': '03-08', 'tags': ['女性', '感恩'], 'suggested_flowers': ['康乃馨', '百合', '郁金香']},
    {'name': '白色情人节', 'date': '03-14', 'tags': ['爱情', '纯洁'], 'suggested_flowers': ['白玫瑰', '百合', '满天星']},
    {'name': '母亲节', 'date': '05-10', 'tags': ['母亲', '感恩'], 'suggested_flowers': ['康乃馨', '百合', '洋桔梗']},
    {'name': '儿童节', 'date': '06-01', 'tags': ['童真', '快乐'], 'suggested_flowers': ['向日葵', '雏菊', '非洲菊']},
    {'name': '父亲节', 'date': '06-21', 'tags': ['父亲', '感恩'], 'suggested_flowers': ['向日葵', '玫瑰', '绿萝']},
    {'name': '七夕节', 'date': '08-22', 'tags': ['爱情', '浪漫'], 'suggested_flowers': ['红玫瑰', '满天星', '勿忘我']},
    {'name': '教师节', 'date': '09-10', 'tags': ['教师', '感恩'], 'suggested_flowers': ['康乃馨', '百合', '向日葵']},
    {'name': '国庆节', 'date': '10-01', 'tags': ['国庆', '祝福'], 'suggested_flowers': ['向日葵', '百合', '红玫瑰']},
    {'name': '万圣节', 'date': '10-31', 'tags': ['万圣节', '神秘'], 'suggested_flowers': ['橙色非洲菊', '紫色玫瑰', '向日葵']},
    {'name': '双十一', 'date': '11-11', 'tags': ['购物', '单身'], 'suggested_flowers': ['向日葵', '雏菊', '非洲菊']},
    {'name': '感恩节', 'date': '11-26', 'tags': ['感恩', '祝福'], 'suggested_flowers': ['百合', '康乃馨', '向日葵']},
    {'name': '圣诞节', 'date': '12-25', 'tags': ['圣诞', '祝福'], 'suggested_flowers': ['圣诞红', '百合', '松枝']},
    
    # 农历节日（2026年日期）
    {'name': '春节', 'date': '02-17', 'tags': ['新年', '团圆'], 'suggested_flowers': ['百合', '水仙', '桃花', '银柳']},
    {'name': '元宵节', 'date': '03-03', 'tags': ['团圆', '祝福'], 'suggested_flowers': ['百合', '水仙', '郁金香']},
    {'name': '清明节', 'date': '04-05', 'tags': ['思念', '缅怀'], 'suggested_flowers': ['菊花', '百合', '满天星']},
    {'name': '端午节', 'date': '06-19', 'tags': ['传统', '安康'], 'suggested_flowers': ['艾草', '百合', '向日葵']},
    {'name': '中秋节', 'date': '09-27', 'tags': ['团圆', '思乡'], 'suggested_flowers': ['桂花', '百合', '向日葵']},
]

@register_tool(
    name='get_nearby_holidays',
    description='查询近期节日/纪念日，用于推荐送礼场景。返回未来指定天数内的节日列表。',
    parameters={
        'type': 'object',
        'properties': {
            'days': {'type': 'integer', 'description': '查询未来几天（默认30天）', 'default': 30}
        },
        'required': []
    }
)
def get_nearby_holidays(days: int = 30) -> list[dict]:
    """查询近期节日，返回节日信息和推荐花材。"""
    today = datetime.now()
    target_date = today + timedelta(days=days)
    
    nearby = []
    for holiday in HOLIDAYS:
        try:
            # 解析节日日期（假设是今年）
            month, day = map(int, holiday['date'].split('-'))
            holiday_date = datetime(today.year, month, day)
            
            # 如果节日已过，算明年
            if holiday_date < today:
                holiday_date = datetime(today.year + 1, month, day)
            
            # 检查是否在查询范围内
            if today <= holiday_date <= target_date:
                days_until = (holiday_date - today).days
                nearby.append({
                    'name': holiday['name'],
                    'date': holiday_date.strftime('%Y-%m-%d'),
                    'days_until': days_until,
                    'tags': holiday['tags'],
                    'suggested_flowers': holiday['suggested_flowers']
                })
        except Exception:
            continue
    
    # 按距离排序
    nearby.sort(key=lambda x: x['days_until'])
    
    return nearby


# ---- 价格查询工具 ----

# 花卉价格参考（元/枝）
FLOWER_PRICES = {
    '玫瑰': {'low': 3, 'mid': 5, 'high': 8, 'unit': '枝'},
    '百合': {'low': 5, 'mid': 8, 'high': 12, 'unit': '枝'},
    '康乃馨': {'low': 2, 'mid': 3, 'high': 5, 'unit': '枝'},
    '向日葵': {'low': 4, 'mid': 6, 'high': 10, 'unit': '枝'},
    '郁金香': {'low': 4, 'mid': 6, 'high': 10, 'unit': '枝'},
    '满天星': {'low': 10, 'mid': 15, 'high': 25, 'unit': '扎'},
    '勿忘我': {'low': 8, 'mid': 12, 'high': 20, 'unit': '扎'},
    '洋桔梗': {'low': 3, 'mid': 5, 'high': 8, 'unit': '枝'},
    '绣球花': {'low': 15, 'mid': 25, 'high': 40, 'unit': '枝'},
    '非洲菊': {'low': 3, 'mid': 5, 'high': 8, 'unit': '枝'},
    '雏菊': {'low': 2, 'mid': 3, 'high': 5, 'unit': '枝'},
    '尤加利叶': {'low': 3, 'mid': 5, 'high': 8, 'unit': '枝'},
}

@register_tool(
    name='get_flower_prices',
    description='查询花卉价格参考，用于预算推荐和方案设计。返回指定花材的价格区间。',
    parameters={
        'type': 'object',
        'properties': {
            'flower_names': {'type': 'array', 'items': {'type': 'string'}, 'description': '花材名称列表（如：["玫瑰", "百合"]）'},
            'budget': {'type': 'number', 'description': '预算金额（可选，用于推荐性价比搭配）'}
        },
        'required': ['flower_names']
    }
)
def get_flower_prices(flower_names: list[str], budget: float = 0) -> list[dict]:
    """查询花卉价格，返回价格信息和性价比建议。"""
    results = []
    
    for name in flower_names:
        # 模糊匹配
        matched = None
        for flower_name, prices in FLOWER_PRICES.items():
            if name in flower_name or flower_name in name:
                matched = prices
                break
        
        if matched:
            results.append({
                'name': name,
                'prices': matched,
                'budget_suggestion': None
            })
        else:
            results.append({
                'name': name,
                'prices': None,
                'note': f'未找到 {name} 的价格信息'
            })
    
    # 如果有预算，给出搭配建议
    if budget > 0 and results:
        total_low = sum(r['prices']['low'] for r in results if r.get('prices'))
        total_high = sum(r['prices']['high'] for r in results if r.get('prices'))
        
        if budget < total_low * 3:
            suggestion = f'预算 {budget} 元较紧张，建议选择价格较低的花材或减少数量'
        elif budget > total_high * 5:
            suggestion = f'预算 {budget} 元充足，可以选择高品质花材或增加配花'
        else:
            suggestion = f'预算 {budget} 元适中，建议主花 3-5 枝 + 配花 + 包装'
        
        for r in results:
            if r.get('prices'):
                r['budget_suggestion'] = suggestion
    
    return results


# ---- 用户偏好学习工具 ----

@register_tool(
    name='learn_from_feedback',
    description='从用户反馈中学习偏好，优化后续推荐。记录用户喜欢/不喜欢的花材、风格、场合等。',
    parameters={
        'type': 'object',
        'properties': {
            'feedback_type': {'type': 'string', 'enum': ['like', 'dislike', 'neutral'], 'description': '反馈类型：like=喜欢, dislike=不喜欢, neutral=中立'},
            'item_type': {'type': 'string', 'enum': ['flower', 'style', 'occasion', 'price_range'], 'description': '反馈对象类型：flower=花材, style=风格, occasion=场合, price_range=价格区间'},
            'item_value': {'type': 'string', 'description': '反馈对象值（如：玫瑰、韩式风格、母亲节、100-200元）'}
        },
        'required': ['feedback_type', 'item_type', 'item_value']
    },
    inject_context=True
)
def learn_from_feedback(feedback_type: str, item_type: str, item_value: str, _context: dict | None = None) -> bool:
    """学习用户偏好，更新长期记忆。"""
    if not _context:
        return False
    
    user_id = _context.get('user_id', '')
    if not user_id:
        return False
    
    try:
        from backend.storage import memory as mem_store
        
        # 构建偏好键名
        pref_key = f'pref_{item_type}'
        
        # 获取现有偏好（同步 DB 查询避免嵌套事件循环）
        from backend.storage import db as _db
        conn = _db.get_conn()
        row = conn.execute(
            'SELECT value FROM memories WHERE user_id=? AND key=?',
            (user_id, pref_key)
        ).fetchone()
        existing = row['value'] if row else ''
        prefs = [p.strip() for p in existing.split(',') if p.strip()]
        
        # 根据反馈类型更新
        if feedback_type == 'like':
            if item_value not in prefs:
                prefs.append(item_value)
        elif feedback_type == 'dislike':
            if item_value in prefs:
                prefs.remove(item_value)
        # neutral 不修改
        
        # 保存更新后的偏好
        new_prefs = ','.join(prefs)
        conn.execute(
            'INSERT OR REPLACE INTO memories(user_id, key, value, created_at) VALUES(?,?,?,?)',
            (user_id, pref_key, new_prefs, datetime.now(UTC).isoformat())
        )
        conn.commit()
        
        logger.info(f'学习用户偏好: user={user_id}, type={item_type}, value={item_value}, action={feedback_type}')
        return True
    
    except Exception as e:
        logger.error(f'学习用户偏好失败: {e}')
        return False


# ---- 配送范围查询工具 ----

@register_tool(
    name='get_delivery_info',
    description='查询配送范围和配送费，用于推荐店铺和计算总价。',
    parameters={
        'type': 'object',
        'properties': {
            'location': {'type': 'object', 'description': '用户位置 {lat: 纬度, lng: 经度}', 'properties': {'lat': {'type': 'number'}, 'lng': {'type': 'number'}}}
        },
        'required': []
    },
    inject_context=True
)
def get_delivery_info(location: dict | None = None, _context: dict | None = None) -> dict:
    """查询配送范围和费用。"""
    try:
        from backend.storage import config as config_store
        
        # 获取配送配置
        delivery_radius = float(config_store.get_config('delivery_radius_km', 5.0))
        shipping_fee = float(config_store.get_config('shipping_fee', 5.0))
        free_shipping_threshold = float(config_store.get_config('free_shipping_threshold', 100))
        
        return {
            'delivery_radius_km': delivery_radius,
            'shipping_fee': shipping_fee,
            'free_shipping_threshold': free_shipping_threshold,
            'location': location
        }
    
    except Exception as e:
        logger.error(f'查询配送信息失败: {e}')
        return {
            'delivery_radius_km': 5.0,
            'shipping_fee': 5.0,
            'free_shipping_threshold': 100
        }
