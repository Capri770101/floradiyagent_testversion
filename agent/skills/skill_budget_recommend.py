"""skills/skill_budget_recommend.py —— 预算推荐技能。

根据用户预算推荐性价比最高的花材搭配方案。
"""
from __future__ import annotations

from typing import Any


# ---- 预算推荐技能指令 ----

BUDGET_RECOMMEND_SKILL = """
## 预算推荐专业技能

当你需要根据用户预算推荐花材时，遵循以下原则：

### 1. 预算分级

**经济型（50-100元）**
- 3-5枝主花 + 简单配花 + 基础包装
- 推荐花材：康乃馨、雏菊、向日葵
- 特点：实惠、温馨、适合日常

**标准型（100-200元）**
- 7-11枝主花 + 适量配花 + 精美包装
- 推荐花材：玫瑰、百合、康乃馨
- 特点：品质、美观、适合送礼

**品质型（200-500元）**
- 11-19枝主花 + 丰富配花 + 高档包装
- 推荐花材：玫瑰、百合、绣球
- 特点：精致、大气、适合重要场合

**奢华型（500元以上）**
- 19枝以上主花 + 大量配花 + 定制包装
- 推荐花材：进口玫瑰、芍药、绣球
- 特点：奢华、独特、适合特殊场合

### 2. 性价比原则

**高性价比花材**
- 康乃馨：价格低，数量足，适合铺量
- 向日葵：价格适中，花型大，视觉冲击力强
- 洋桔梗：价格适中，花期长，保鲜久

**中等性价比花材**
- 玫瑰：经典，但单价较高
- 百合：高雅，但气味较浓

**低性价比花材**
- 绣球：单价高，但视觉效果好
- 芍药：季节性花材，价格波动大

### 3. 预算分配建议

**100元预算分配**
- 主花：60元（约10枝康乃馨）
- 配花：20元（满天星）
- 包装：20元

**200元预算分配**
- 主花：120元（约8枝玫瑰）
- 配花：40元（洋桔梗+满天星）
- 包装：40元

**300元预算分配**
- 主花：180元（约12枝玫瑰）
- 配花：60元（洋桔梗+满天星+尤加利叶）
- 包装：60元

**500元预算分配**
- 主花：300元（约15枝玫瑰+3枝百合）
- 配花：100元（绣球+洋桔梗+满天星）
- 包装：100元

### 4. 省钱技巧

- 选择当季花材，价格更实惠
- 减少主花数量，增加配花填充
- 选择简约包装，降低包装成本
- 避开节日高峰期，价格更稳定
"""


def get_budget_recommend_prompt() -> str:
    """返回预算推荐技能指令。"""
    return BUDGET_RECOMMEND_SKILL


# ---- 预算推荐函数 ----

def recommend_by_budget(
    budget: float,
    occasion: str = '通用',
    recipient: str = '朋友'
) -> dict[str, Any]:
    """根据预算推荐花材搭配方案。"""
    
    # 预算分级
    if budget < 100:
        level = '经济型'
        main_flowers = ['康乃馨', '雏菊']
        main_count = 5
        support_flowers = ['满天星']
        packaging = '简约包装'
        description = '温馨实惠，适合日常送礼'
    elif budget < 200:
        level = '标准型'
        main_flowers = ['玫瑰', '康乃馨']
        main_count = 11
        support_flowers = ['洋桔梗', '满天星']
        packaging = '精美包装'
        description = '品质美观，适合生日、纪念日'
    elif budget < 500:
        level = '品质型'
        main_flowers = ['玫瑰', '百合']
        main_count = 15
        support_flowers = ['绣球', '洋桔梗', '满天星']
        packaging = '高档包装'
        description = '精致大气，适合重要场合'
    else:
        level = '奢华型'
        main_flowers = ['进口玫瑰', '芍药', '百合']
        main_count = 19
        support_flowers = ['绣球', '洋桔梗', '满天星', '尤加利叶']
        packaging = '定制包装'
        description = '奢华独特，适合特殊场合'
    
    # 根据场合调整
    occasion_adjustments = {
        '母亲节': {'main_flowers': ['康乃馨', '百合'], 'note': '母亲节首选康乃馨'},
        '情人节': {'main_flowers': ['红玫瑰'], 'note': '情人节经典选择红玫瑰'},
        '生日': {'main_flowers': ['向日葵', '玫瑰'], 'note': '生日推荐向日葵，阳光活力'},
        '探病': {'main_flowers': ['百合', '康乃馨'], 'note': '探病选择香气淡雅的花材'},
        '婚礼': {'main_flowers': ['白玫瑰', '百合'], 'note': '婚礼以白色为主，象征纯洁'}
    }
    
    if occasion in occasion_adjustments:
        adjustment = occasion_adjustments[occasion]
        main_flowers = adjustment['main_flowers']
        note = adjustment['note']
    else:
        note = description
    
    # 构建推荐方案
    recommendation = {
        'budget': budget,
        'level': level,
        'occasion': occasion,
        'recipient': recipient,
        'arrangement': {
            'main_flowers': main_flowers,
            'main_count': main_count,
            'support_flowers': support_flowers,
            'packaging': packaging
        },
        'note': note,
        'estimated_price': budget * 0.85  # 预估价格为预算的85%
    }
    
    # 计算价格明细
    price_reference = {
        '康乃馨': 3,
        '雏菊': 3,
        '向日葵': 6,
        '玫瑰': 5,
        '百合': 8,
        '洋桔梗': 5,
        '满天星': 15,
        '绣球': 25,
        '尤加利叶': 5
    }
    
    total = 0
    price_details = []
    for flower in main_flowers:
        price = price_reference.get(flower, 5)
        cost = price * main_count
        total += cost
        price_details.append({'name': flower, 'price': price, 'count': main_count, 'total': cost})
    
    for flower in support_flowers:
        price = price_reference.get(flower, 5)
        count = 2
        cost = price * count
        total += cost
        price_details.append({'name': flower, 'price': price, 'count': count, 'total': cost})
    
    recommendation['price_details'] = price_details
    recommendation['total_price'] = total
    
    return recommendation
