# 知识库内容清单模板（Knowledge Base Template）

> 用途：把 `knowledge/` 下的通用花艺骨架，替换成**你们自己的真实业务数据**。
> 原则：**只改 JSON 数据，不动代码**。`store.py` 会在启动时自动加载，改完重启服务即生效。
> 当前已有 6 个知识域，下面逐文件说明字段含义、示例行与填写规则。

---

## 0. 总体替换步骤（照做即可）

1. 确认服务已停（改 JSON 不会热更新，需重启 `uvicorn api:app`）。
2. 逐文件对照下表，把通用样例**替换或追加**为你家的真实数据。
   - 直接改现有条目的值，或按相同结构新增条目都可以。
   - `id` 必须全局唯一（建议前缀 `F_`/`S_`/`SC_`/`P_`/`T`/`PK_` 之类），同名花材的各字段要保持一致。
3. 重启服务，`POST /chat` 或单测 `tests/test_knowledge.py` 验证检索是否命中你的新数据。
4. 若需校验设计函数是否用上了新数据：`tests/test_diy_design.py` 跑一遍。

> ⚠️ 字段名（key）**务必保持英文、拼写一致**，否则检索/设计管线读不到。
> 中文内容（name、description、recommendation 等）随意填你们的表达习惯。

---

## 1. `flowers.json` — 花材库（最核心，先填这个）

每个元素代表一种花材：

| 字段 | 类型 | 含义 | 填写规则 / 示例 |
|------|------|------|----------------|
| `id` | str | 唯一标识 | `"F_ROSE"`（前缀 `F_`） |
| `name` | str | 花材名 | `"玫瑰"` |
| `aliases` | list[str] | 别名/俗称 | `"红玫瑰"`、`"粉玫瑰"`、`"香槟玫瑰"` 都写进来，便于用户口语命中 |
| `flower_language` | list[str] | 花语/寓意 | `["爱情","热烈","浪漫","尊敬"]` |
| `colors` | list[str] | 常见花色 | `["红","粉","白","香槟","紫","橙","黄"]`（色名自由定义，但后续 `styles.json`/`scenes.json` 的色板要能对应上） |
| `season` | list[str] | 上市季节 | `["四季"]` / `["春"]` / `["夏","秋"]` |
| `price_tier` | str | 价格档 | `"低"` / `"中"` / `"高"`（三档即可，影响预算映射时的 `suggested_flowers`） |
| `freshness` | str | 保鲜难度 | `"低"` / `"中"` / `"高"`（高=易蔫，设计时会提示） |
| `category` | str | 在方案中的角色 | `"主花"` / `"配材"` / `"填充"` / `"叶材"`（设计函数据此分配主/配/叶） |
| `pairing_notes` | str | 搭配经验 | 人类可读的搭配建议，如「百搭主花，配满天星/尤加利最经典」 |
| `tags` | list[str] | 检索标签 | `["经典","主花","浪漫","爱情"]`（自由词，会被关键词检索命中） |

**填写建议**：把你们常用的花材都建进来，重点维护 `aliases`（用户怎么叫它）、`price_tier`（决定预算档能选它）、`category`（决定它在方案里当主角还是配角）。

---

## 2. `styles.json` — 风格体系（含子风格）

顶层风格 + `substyles` 子风格两层。设计函数先定大类、再选子风格。

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `id` | str | 唯一标识 | `"S_KOREAN"`（前缀 `S_`） |
| `name` | str | 风格名 | `"韩式"` |
| `description` | str | 风格描述 | 给模型看的理解文本 |
| `typical_flowers` | list[str] | 典型花材（**必须能在 `flowers.json` 的 name/aliases 命中**） | `["洋桔梗","玫瑰","尤加利","小雏菊"]` |
| `color_palette` | list[str] | 色板 | `["粉白","香槟","浅紫","雾蓝"]` |
| `packaging` | str | 包装方式 | `"雾面韩素纸 + 雪纺带，螺旋扎松散自然"` |
| `vibe` | list[str] | 氛围词 | `["温柔","高级","清新","ins风"]` |
| `tags` | list[str] | 检索标签 | `["韩式","清新","温柔"]` |
| `substyles` | list[obj] | 子风格数组（结构同顶层，可省略 `substyles` 字段） | 见下 |

**子风格对象字段**：`id` / `name` / `description` / `typical_flowers` / `color_palette` / `packaging` / `vibe`（与顶层一致，不带 `tags` 和 `substyles`）。

**填写建议**：你们家主打几种风格就建几种；子风格用于「韩式甜美 vs 韩式高级」这种细分。用户说「高级点」会命中 `vibe` 含「高级」的子风格。

---

## 3. `scenes.json` — 场景 / 节日模板（让设计「懂场合」）

每个元素是一个场景/节日，设计函数识别关键词后会注入整组偏好。

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `id` | str | 唯一标识 | `"SC_MOTHER"`（前缀 `SC_`） |
| `name` | str | 场景名 | `"母亲节"` |
| `keywords` | list[str] | 触发关键词（用户口语命中） | `["母亲节"]`、`["生日","庆祝","过生日"]` |
| `recommended_style` | str | 推荐风格 id | `"S_KOREAN"` |
| `recommended_substyle` | str | 推荐子风格 id | `"S_KOREAN_LUXE"` |
| `color_tone` | list[str] | 推荐色调 | `["粉白","香槟","浅紫"]` |
| `main_flower_preference` | list[str] | 主花倾向（**要能在 `flowers.json` 命中**） | `["康乃馨","玫瑰","百合"]` |
| `meaning_tone` | str | 寓意基调 | `"感恩母爱、温柔祝福"` |
| `budget_anchor` | str | 预算锚点（对应 `budget.json` 的 `tier`） | `"T2"` |
| `notes` | str | 设计备注 | 给模型看的场景化建议 |

**填写建议**：覆盖你们常接的节日/场景，越细越好。关键词要写全用户可能的说法（如「过生日」「庆生」都算生日）。

---

## 4. `pairings.json` — 搭配规则（色彩 / 形态 / 场合 / 对象）

通用搭配经验库，按 `type` 分四类：`color`（色彩）/ `shape`（形态）/ `occasion`（场合）/ `recipient`（对象）。

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `id` | str | 唯一标识 | `"P_OCC_MOTHER"`（前缀 `P_`） |
| `type` | str | 规则类别 | `"color"`/`shape`/`occasion`/`recipient` |
| `condition` | str | 触发条件描述 | `"送母亲 / 母亲节"` |
| `recommendation` | str | 推荐内容（**若提到具体花名，必须能在 `flowers.json` 命中，设计函数会据此优选花材**） | `"首选康乃馨，配玫瑰+满天星；色调温馨粉白，寓意感恩母爱。"` |

**填写建议**：把你们压箱底的搭配经验写成一条条规则。重点：`recommendation` 里写清楚花名，设计函数会优先采用。

---

## 5. `budget.json` — 预算 → 配置映射

三档即可，决定某预算下「该用多少支、什么配置、推什么花」。

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `tier` | str | 档位 id | `"T1"` / `"T2"` / `"T3"` |
| `range` | [int, int] | 预算区间（闭区间，元） | `[0, 200]` |
| `label` | str | 档位名 | `"入门 / 日常"` |
| `main_count` | str | 主花支数建议 | `"5-7 支主花"` |
| `config` | str | 配置描述 | `"1 种主花 + 1-2 种平价配材 + 基础包装"` |
| `suggested_flowers` | list[str] | 该档推荐花材（**要能在 `flowers.json` 命中**） | `["康乃馨","非洲菊","向日葵","满天星","小雏菊"]` |

**填写建议**：按你们真实定价改 `range` 和 `suggested_flowers`。设计函数未识别到预算时，默认用 `T2` 档。

---

## 6. `packaging.json` — 包装 / 器型库

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `id` | str | 唯一标识 | `"PK_BOUQUET"`（前缀 `PK_`） |
| `name` | str | 包装名 | `"花束（螺旋扎）"` |
| `suitable_for` | list[str] | 适用场景 | `["送礼","手持","拍照"]` |
| `description` | str | 描述 | `"经典螺旋手法扎制……"` |

**填写建议**：列出你们提供的包装/器型选项即可。设计函数目前默认按场景选「花束」或高档「礼盒」，可在此扩展。

---

## 7. 新增一个知识域（进阶，需要改代码）

若现有 6 个域不够（比如你想加「花器库」「贺卡文案库」），需要：
1. 在 `knowledge/` 下新建 `xxx.json`（数组结构，元素含 `id`/`name` 等）；
2. 在 `knowledge/store.py` 的 `_DOMAINS` 字典加一行 `"xxx": "xxx.json"`；
3. （可选）在 `tools.py` 的设计函数里调用 `query_knowledge("xxx", ...)` 使用它。

> 一般业务数据扩展**不需要**这一步，把内容塞进现有 6 个域就够了。

---

## 8. 校验清单（填完后自测）

- [ ] 所有 `flowers.json` 里被 `styles`/`scenes`/`pairings`/`budget` 引用的花名，都能在 `flowers.json` 的 `name` 或 `aliases` 命中（否则设计函数会漏掉它）。
- [ ] 色名在 `flowers.colors` / `styles.color_palette` / `scenes.color_tone` 间保持一致（如都用「香槟」而非有时写「香槟色」）。
- [ ] `scenes.keywords` 覆盖了用户常见说法。
- [ ] JSON 语法合法（可用 `python -m json.tool xxx.json` 校验）。
- [ ] 重启服务后，用一条真实需求测 `POST /chat`，确认方案用的是你们的数据。
