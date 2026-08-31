"""skills/skill_flower_matching.py —— 花材搭配技能。

为特定场景提供专业花材搭配指令，类似 OpenCode 的 skill 系统。
这个技能模块为智能体提供花材搭配的专业知识和规则。
"""
from __future__ import annotations

from typing import Any

# ---- 花材搭配技能指令 ----

FLOWER_MATCHING_SKILL = """
## 花材搭配专业技能

当你需要为用户推荐花材搭配时，遵循以下专业原则：

### 1. 色彩搭配原则

**同色系搭配（温柔和谐）**
- 粉色系：粉玫瑰 + 百合 + 满天星 → 温柔甜美
- 白色系：白玫瑰 + 百合 + 洋桔梗 → 纯洁高雅
- 紫色系：紫玫瑰 + 洋桔梗 + 勿忘我 → 神秘高贵

**对比色搭配（活力醒目）**
- 红 + 绿：红玫瑰 + 尤加利叶 → 经典活力
- 黄 + 紫：向日葵 + 紫玫瑰 → 高贵明亮
- 橙 + 蓝：非洲菊 + 蓝色绣球 → 热情奔放

**避免原则**
- 不超过 3 种主色
- 避免颜色过于杂乱（如红+黄+紫+绿）
- 深色花材配浅色包装，浅色花材配深色包装

### 2. 花语搭配原则

**爱情场景**
- 红玫瑰 + 满天星 + 勿忘我 → 热恋
- 白玫瑰 + 洋桔梗 → 纯洁的爱
- 粉玫瑰 + 百合 → 甜蜜温馨

**友谊场景**
- 向日葵 + 雏菊 + 黄莺 → 阳光友谊
- 黄玫瑰 + 洋桔梗 → 友谊长存

**祝福场景**
- 百合 + 康乃馨 + 洋桔梗 → 祝福健康
- 向日葵 + 玫瑰 + 绣球 → 前程似锦

**感恩场景**
- 康乃馨 + 满天星 → 母爱感恩
- 百合 + 康乃馨 → 健康感恩

### 3. 场景搭配原则

**婚礼**
- 白玫瑰 + 满天星 + 尤加利叶 → 圣洁浪漫
- 百合 + 绣球 + 洋桔梗 → 高雅大气

**生日**
- 向日葵 + 玫瑰 + 绣球 → 阳光活力
- 郁金香 + 洋桔梗 → 温馨祝福

**探病**
- 百合 + 康乃馨 + 绿萝 → 祝福康复
- 郁金香 + 洋桔梗 → 温馨关怀

**母亲节**
- 康乃馨 + 满天星 → 经典母爱
- 百合 + 康乃馨 + 洋桔梗 → 健康温馨

### 4. 预算搭配原则

**100元以内（3-5枝主花）**
- 3枝玫瑰 + 满天星 + 包装
- 5枝康乃馨 + 满天星 + 包装

**100-300元（7-11枝主花）**
- 11枝玫瑰 + 满天星 + 尤加利叶 + 精美包装
- 7枝百合 + 洋桔梗 + 包装

**300元以上（11枝以上+配花+包装）**
- 19枝玫瑰 + 满天星 + 尤加利叶 + 高档包装
- 混合花束：玫瑰 + 百合 + 绣球 + 洋桔梗 + 包装

### 5. 搭配禁忌

- 百合气味浓，不宜与香味强的花材搭配
- 玫瑰有刺，探病花束避免使用
- 菊花主要用于祭奠，不适合送礼
- 水仙有毒，不适合有小孩的家庭
"""


def get_flower_matching_prompt() -> str:
    """返回花材搭配技能指令。"""
    return FLOWER_MATCHING_SKILL


# ---- 搭配推荐函数 ----

def recommend_arrangement(
    occasion: str,
    recipient: str,
    budget: float,
    style: str = '经典',
    colors: list[str] | None = None
) -> dict[str, Any]:
    """根据场景、对象、预算推荐花材搭配方案。"""
    
    # 场景-花材映射
    occasion_flowers = {
        '爱情': {
            '主花': ['红玫瑰', '粉玫瑰', '白玫瑰'],
            '配花': ['满天星', '勿忘我', '洋桔梗'],
            '配叶': ['尤加利叶', '绿萝']
        },
        '友谊': {
            '主花': ['向日葵', '雏菊', '非洲菊'],
            '配花': ['洋桔梗', '黄莺'],
            '配叶': ['尤加利叶', '绿萝']
        },
        '祝福': {
            '主花': ['百合', '康乃馨', '向日葵'],
            '配花': ['洋桔梗', '满天星'],
            '配叶': ['尤加利叶', '绿萝']
        },
        '感恩': {
            '主花': ['康乃馨', '百合'],
            '配花': ['满天星', '洋桔梗'],
            '配叶': ['尤加利叶', '绿萝']
        },
        '探病': {
            '主花': ['百合', '康乃馨', '郁金香'],
            '配花': ['洋桔梗', '绿萝'],
            '配叶': ['尤加利叶']
        },
        '生日': {
            '主花': ['向日葵', '玫瑰', '绣球'],
            '配花': ['洋桔梗', '满天星'],
            '配叶': ['尤加利叶', '绿萝']
        },
        '婚礼': {
            '主花': ['白玫瑰', '百合', '绣球'],
            '配花': ['满天星', '洋桔梗'],
            '配叶': ['尤加利叶']
        }
    }
    
    # 获取场景搭配建议
    matching = occasion_flowers.get(occasion, occasion_flowers['祝福'])
    
    # 根据预算调整
    if budget < 100:
        main_count = 3
        support_count = 1
        packaging = '简约包装'
    elif budget < 300:
        main_count = 7
        support_count = 2
        packaging = '精美包装'
    else:
        main_count = 11
        support_count = 3
        packaging = '高档包装'
    
    # 构建推荐方案
    recommendation = {
        'occasion': occasion,
        'recipient': recipient,
        'budget': budget,
        'style': style,
        'arrangement': {
            'main_flowers': matching['主花'][:min(2, len(matching['主花']))],
            'main_count': main_count,
            'support_flowers': matching['配花'][:min(2, len(matching['配花']))],
            'support_count': support_count,
            'leaves': matching['配叶'][:1],
            'packaging': packaging
        },
        'flower_language': [],
        'estimated_price': budget * 0.7  # 预估价格为预算的70%
    }
    
    # 添加花语
    flower_languages = {
        '红玫瑰': '爱情、热烈',
        '粉玫瑰': '初恋、甜蜜',
        '白玫瑰': '纯洁、尊敬',
        '百合': '纯洁、祝福、百年好合',
        '康乃馨': '母爱、温馨、感恩',
        '向日葵': '阳光、积极、希望',
        '满天星': '思念、配角、甘愿',
        '洋桔梗': '真诚、纯洁',
        '尤加利叶': '恩赐、回忆',
        '绣球': '希望、美满',
        '郁金香': '高贵、告白'
    }
    
    for flower in recommendation['arrangement']['main_flowers']:
        if flower in flower_languages:
            recommendation['flower_language'].append(f'{flower}：{flower_languages[flower]}')
    
    return recommendation
