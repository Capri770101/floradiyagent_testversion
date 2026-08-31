# 花卉知识库使用指南

## 知识库结构

知识库已从 JSON 文件升级为 SQLite 数据库，包含以下表：

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| `flowers` | 花材信息 | id, name, aliases, flower_language, colors, season, price_tier, category, care_tips, pairing_notes, tags |
| `pairings` | 搭配方案 | id, name, description, occasion_ids, style_ids, budget_min, budget_max, season, tags |
| `pairing_flowers` | 搭配花材关系 | pairing_id, flower_id, flower_type, quantity_min, quantity_max, is_required |
| `occasions` | 场景信息 | id, name, description, keywords, suggested_flowers, tags |
| `styles` | 风格信息 | id, name, description, color_scheme, flower_types, keywords, tags |

## 检索方式

### 1. 关键词检索
```python
from agent.knowledge.store import query_knowledge

# 精确匹配
result = query_knowledge(domain='flower', query='玫瑰')
```

### 2. 语义检索（向量混合检索）
```python
# 多 token 或长自然语句会自动启用语义检索
result = query_knowledge(domain='all', query='适合送给母亲的花')
```

### 3. 按 ID 查询
```python
from agent.knowledge.store import get_by_id

flower = get_by_id('flower', 'F_ROSE_RED')
```

## 花材分类

- **主花**：玫瑰、百合、康乃馨、绣球等（视觉焦点）
- **配花**：洋桔梗、满天星、雏菊等（填充丰富）
- **叶材**：尤加利、银叶菊等（勾边线条）

## 价格档位

- **低**：≤2元/枝
- **中**：2-5元/枝
- **高**：≥5元/枝

## 搭配原则

1. **色彩和谐**：同色系/邻近色为主，对比色需降饱和
2. **主次分明**：1-2种主花做焦点，配材围绕
3. **线条感**：加入线条花材（尤加利枝、银叶菊）拉开层次
4. **场景适配**：根据场合选择合适的花材和寓意

## 场景推荐

- **母亲节**：康乃馨 + 玫瑰 + 满天星（温馨粉白）
- **生日**：向日葵/非洲菊/郁金香（明亮活泼）
- **恋人**：红/粉玫瑰 + 洋桔梗（浪漫精致）
- **探病**：百合 + 康乃馨（清新祝福）

## API 接口

### 工具函数
- `search_flower_knowledge(query)` - 搜索花材知识
- `get_flower_prices(flower_name)` - 获取花材价格
- `get_nearby_holidays()` - 获取近期节日推荐

### 后台接口
- `GET /api/knowledge/flowers` - 花材列表
- `GET /api/knowledge/pairings` - 搭配方案列表
- `GET /api/knowledge/occasions` - 场景列表
- `GET /api/knowledge/stats` - 知识库统计
