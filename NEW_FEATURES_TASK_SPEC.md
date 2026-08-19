# 新功能任务书（AI 执行版）

> ⚠️ **STATUS：本任务书描述的三大模块均已实现，本文档现为「已实现功能存档 / 验收清单」，不再作为建造任务书。**
> 2026-08-19 二次复核确认：消息通知（routers/notify.py + storage/notify.py + H5/src/api/notify.js + H5/src/pages/Notifications.jsx + 订单·评价·售后埋点 + tests/test_notifications.py）、DIY 卡片扩充（diy_plans 迁移列 db.py:543-548 + tools.py design_with_llm 产出 950-987 + DiyPlanCard.jsx 渲染 50-55/285/346 + seed_demo.py:209-214 灌值）、个性化推荐（routers/recommend.py + storage/recommend.py + Home/ShopDetail/DiyDetail 三处推荐位 + tests/test_recommend.py）**全部已落地**。若需改动，请先 `git log`/`grep` 确认真实代码状态，勿按"从零新建"理解本文件。
> 历史教训：本项目多次出现「按功能不存在的假设写建造任务书，实际早已实现」（M4/M5 售后·入驻、admin 账号、ShopDetail menu、本任务书三模块均中招）。**写/执行任务书前，必须 grep 确认文件与功能是否已存在。**

> 本文档供执行 AI 直接消费：含系统提示、硬约束、三大模块的实现规格（数据表 / 接口 / 前端 / 验收）。
> 本期范围由用户 2026-08-19 拍板：**消息通知中心 + DIY 卡片内容扩充 + 个性化推荐打磨**。
> **明确排除**：会员体系、全站搜索页（用户认为无必要）、真实微信/支付宝支付、真实物流 API、微信登录（均属"等外部接入"）。

---

## 0. SYSTEM PROMPT（执行 AI 可直接采用）

```
你是 flora_diy_agent 的全栈开发工程师。本项目是花卉 DIY 智能体：FastAPI 后端（api.py + routers/ + storage/）
+ React18 H5 前端（H5/src/）。你正在实现三期新功能：消息通知中心、DIY 卡片内容扩充、个性化推荐打磨。

铁律：
1. 不信任 grep 快照或旧报告判断"功能是否存在"——改任何文件前，必须先 Read 完整函数体/组件逐行确认现状。
2. 前端每一处展示字段都必须有真实后端来源（来自 DB/接口），禁止前端硬编码假数据/写死常量。
3. 暂无真实数据/外部接口时，标准 DB 结构先建好，缺数据用 seed 假数据填充（上线可清空重灌）。
4. 改库结构必须同步更新 seed 脚本与前端字段契约；字段改名必须前后端同步。
5. 不动 WorkBuddy 内置的微信支付 MCP 进程；不碰生产密钥。
6. 完成一个模块即补最小必要测试（后端 pytest / 前端按现有测试风格）。
```

---

## 1. 硬约束（复述用户两条红线）

- **红线1（完成标准）**：功能按可上线标准做。无真实数据/接口 → 建标准 DB 结构 + seed 假数据填充，不允许留空壳、不允许写死占位。
- **红线2（数据纪律）**：前端每一处展示字段都有真实后端来源（DB/接口），禁止前端硬编码假数据/写死常量；前后端就字段建立契约，逐页审计对齐；seed 只填充，不替代 schema。
- **架构纪律**：新功能沿用现有分层（api/ 调 routers/ → storage/ → db）；前端沿用 `H5/src/api/` 统一封装 + `maison-*` 设计 token；不引入与现有栈冲突的新依赖，确需新依赖先征得确认。

---

## 2. 模块一：消息通知中心

### 2.1 实现形式设计（用户特别要求"先想好实现形式"）

经调研，消息通知有三种实现形式，对比与取舍如下：

| 形式 | 机制 | 存储 | 触发方式 | 优点 | 缺点 / 依赖 | 是否符合本期 |
|------|------|------|---------|------|------------|------------|
| **A. 站内消息收件箱（In-app Inbox）** | 新建 `notifications` 表，事件发生时由后端写入；前端消息中心页拉取 | DB `notifications` | 后端在业务动作（下单/发货/签收/评价回复/售后/公告）后调用 `create_notification()` | 自包含、不依赖外部、**现在就能完整做完**、seed 可演示、符合红线1/2 | 用户需主动打开才看到 | ✅ 推荐主方案 |
| **B. 微信订阅消息推送** | 用户授权 `subscribeMessage` 后，后端调微信模板消息接口主动推送到微信服务通知 | 微信侧 + 本地记录 | 业务动作 → 微信 API | 主动触达、体验好 | **需 `WECHAT_APPID` + 模板资质 + 用户授权流程**（外部依赖，本期无）；localhost 无法真测 | ❌ 本期不做，仅留接口占位 |
| **C. 站内为主 + 推送占位（推荐落地形态）** | 以 A 为完整实现；在 `create_notification()` 中预留 `push_channel` 字段与 `should_push` 开关，B 接入时只需补一个推送适配器 | DB `notifications`（含 `push_channel`） | A 的机制 + B 未来启用 | 既现在可上线，又为微信推送留干净扩展点 | 实现略多一字段 | ✅ 采用 |

**结论：采用形式 C**——完整实现站内收件箱（A），并在数据层预留推送扩展点（B 的占位），不接真实微信推送。

### 2.2 数据表（新建 `notifications`）

```sql
CREATE TABLE IF NOT EXISTS notifications (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT    NOT NULL,                 -- 接收用户（users.openid / id）
  type         TEXT    NOT NULL,                 -- order_status | logistics | review_reply | aftersale | announcement | system
  title        TEXT    NOT NULL,
  body         TEXT    NOT NULL,
  ref_type     TEXT,                              -- plan | order | shop | aftersale | null
  ref_id       TEXT,                              -- 关联业务 id，点击跳转用
  push_channel TEXT    DEFAULT 'inbox',           -- inbox | wechat（预留，本期仅 inbox）
  is_read      INTEGER DEFAULT 0,                 -- 0/1
  created_at   TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read, created_at DESC);
```

> 注：`users` 表**已有** `status` 列（`active|banned`，db.py:47，管理后台禁用用），本期消息通知不依赖该列，不擅自扩列。

### 2.3 后端接口（新增 `routers/notify.py`，复用 `_require_user` 鉴权）

| Method | Path | 说明 | 守护 |
|--------|------|------|------|
| GET | `/notifications?type=&is_read=&limit=&offset=` | 当前用户消息列表（分页+过滤） | `_require_user` |
| GET | `/notifications/unread-count` | 未读总数（TabBar 红点用） | `_require_user` |
| POST | `/notifications/mark-read` | body `{ids?: [], all?: bool}` 标记已读 | `_require_user` |
| POST | `/admin/notifications` | 运营发平台公告/系统消息（写全部用户或指定群体） | `_require_admin` |

**写入触发点（在现有业务路由里埋点，调用 `storage/notify.py:create_notification()`）**：
- `commerce.py` 订单支付成功 / 发货 / 签收 → `order_status`
- `storage/catalog.py` 或物流写节点 `order_logistics` 新增时 → `logistics`
- `routers/merchant.py` 商家回复评价时 → `review_reply`（通知评价作者）
- `storage/admin.py` 售后状态变更（通过/拒绝/退款）时 → `aftersale`
- 运营在 `/admin/notifications` 发公告 → `announcement`

> 写入逻辑包在 try/except 内，通知失败**不影响主业务**（不抛异常、记 logger）。

### 2.4 前端（H5）

- **新建 `H5/src/pages/Notifications.jsx`**：消息列表（按 type 分组/筛选 tab：全部/订单/物流/评价/售后/公告），未读高亮，点击进入详情（按 `ref_type/ref_id` 跳 `/order`、`/logistics/:id`、`/my-aftersales`、`/product/:id` 等），"全部已读"按钮调 `mark-read`。
- **`H5/src/api/notify.js`**：`listNotifications()` / `unreadCount()` / `markRead()` / `markAllRead()`，沿用 `api/` 统一封装（超时/Bearer/错误友好化）。
- **`H5/src/components/TabBar.jsx`**：消息入口（或 Profile 内入口）+ 未读红点（启动时拉 `unreadCount()`）。
- **`Settings.jsx`**：原"新订单通知"开关（`Settings.jsx:56`）改为"接收消息推送"偏好（仅控制预留的 `push_channel`，本期始终 inbox，开关仅 UI 占位，不写死行为）。
- **状态处理**：列表须有 loading / empty（"暂无消息"）/ error 三态，不裸渲染 undefined。

### 2.5 验收（消息通知）

- [ ] 后端 `notifications` 表随 DB 初始化创建（幂等 `CREATE TABLE IF NOT EXISTS`，已存在不报错）。
- [ ] seed 脚本灌入 ≥5 条演示通知（覆盖 order_status/logistics/review_reply/aftersale/announcement，关联真实存在的 order_id/plan_id）。
- [ ] 触发任一订单状态变更，DB 新增对应 notification；`/notifications` 返回该用户消息；`unread-count` 正确。
- [ ] 前端消息中心展示、筛选、标记已读、红点联动、详情跳转均通。
- [ ] 通知写入失败不影响主业务（mock `create_notification` 抛错，主流程仍成功）。
- [ ] 无前端写死消息内容（全部来自接口）。

---

## 3. 模块二：DIY 卡片内容扩充

### 3.1 现状（已逐行确认 `H5/src/components/DiyPlanCard.jsx`）

卡片当前展示：`花卉组成`（花材+角色+花语）/ `配色方案`（色块）/ `花语寓意` / `包装形式` / `DIY 操作步骤` / `养护建议` / `预算明细` / `贺卡寄语` + 头部（方案名/价格/风格/收礼人）+ 效果图。

`normalizePlan` 已从 `plan.design` 取字段，但以下**已有字段未显式展示**：`occasion`（场景/节日，仅头部副标题隐含）。

### 3.2 扩充字段（均须真实后端来源，禁止前端写死）

| 新字段 | 含义 | 来源 | 卡片展示形式 |
|--------|------|------|------------|
| `occasion` | 适用场景/节日（生日/告白/探病/母亲节…） | LLM 设计产出（已有字段，UI 补展示） | 头部副标题 + 场景标签 chip |
| `difficulty` | 制作难度（入门/进阶/高手） | LLM 设计新增产出 | 难度条/标签 |
| `est_time` | 预计耗时（分钟） | LLM 设计新增产出 | "约 30 分钟" |
| `shelf_life` | 保鲜期 / 花期（收到后养几天） | LLM 设计新增产出 | 文字 + 图标 |
| `suitable_for` | 适宜人群（如长辈/恋人/同事） | LLM 设计新增产出 | 标签组 |
| `caution` | 禁忌/提醒（如花粉过敏慎选、勿暴晒） | LLM 设计新增产出 | 警示小卡（与贺卡寄语同款样式） |
| `mood_tags` | 情绪标签（治愈/热烈/宁静，文字版） | LLM 设计新增产出 | 配合已有 `colorScheme` 色块的文字说明 |

### 3.3 后端改造

- **`diy_plans` 表**（db.py:79）或方案 JSON 列扩展：新增 `difficulty / est_time / shelf_life / suitable_for / caution / mood_tags` 列（或并入现有设计 JSON 字段，二选一，选前者更易索引/seed）。迁移走 `db.py` 的 `MIGRATIONS` 幂等 `ALTER TABLE ADD COLUMN` 模式（参考现有 messages 迁移写法）。
- **`design_with_llm` 输出 schema**：在 JSON mode 的 prompt 中要求 LLM 输出上述新字段（中英均可，前端 `normalizePlan` 归一化）。
- **`normalizePlan`（DiyPlanCard.jsx:23）**：扩展映射，缺字段回退 `null`（卡片展示 `—`），不因 LLM 漏输出而崩。
- **seed 脚本**：为演示方案（P001…P00N）填充这些字段的示例值（可上线清空）。

### 3.4 前端改造（`DiyPlanCard.jsx`）

- 头部副标题补 `occasion` 场景标签。
- 新增区块（复用现有 `Section` 组件样式）：`制作难度` + `预计耗时`（并排）、`保鲜期`、`适宜人群`、`禁忌提醒`（警示样式）、`情绪标签`。
- 编辑面板（`editMode`）**不**强求支持改这些新字段（属展现增强，非可编辑项），保持"调整方案"仅管预算/风格/花材。

### 3.5 验收（DIY 卡片）

- [ ] 新字段在 `diy_plans` 表存在，seed 有值；旧方案无该字段时卡片不崩（显示 `—`）。
- [ ] `normalizePlan` 覆盖全部新字段且类型稳健。
- [ ] 卡片渲染新区块，无写死文本；视觉延续 paper 文艺风（沿用 `Section`/`border-gold` 等 token）。
- [ ] 后端 pytest 覆盖 `normalizePlan` 归一化 + LLM 输出含新字段的解析。

---

## 4. 模块三：个性化推荐打磨（位置 + 用户定位）

### 4.1 现状（已核实）

- 前端 `H5/src/utils/location.js`：`getLocation()` 返回 `{name, lat, lng}`（用户从深圳各区预设选，或浏览器 Geolocation），持久化 localStorage。
- 后端 `storage/catalog.py:33 _haversine(lat1,lng1,lat2,lng2)` 真实距离算法已就绪；`shops` 表有 `lat/lng/distance_km`（db.py:112-115）；店铺列表已按定位做 haversine 排序（catalog.py:9）。
- 前端收藏 API 齐全：`listFavorites()` / `addFavorite()` / `removeFavorite()` / `favoriteStatus()`（shop.js:173-191）→ 个性化偏好的数据源已具备。
- 现有推荐仅：**Agent 对话内"为你推荐店铺"**（Agent.jsx:37）。

### 4.2 打磨方向

不止"按距离排序"，而是**多信号融合的规则推荐**（可解释、可 seed、不依赖外部 ML 服务，符合红线1）：

1. **位置信号**：前端把 `getLocation()` 的 `lat/lng` 传给后端推荐/列表接口；后端用 `_haversine` 算真实距离，近者加权。
2. **偏好信号**：基于用户 `favorites`（收藏的方案/店铺）、历史 `orders` 的 `style`/`occasion`/`shop`，提取偏好标签（风格、场景、价位带）。
3. **热度信号**：店铺 `rating`/`monthly_sales`、方案被收藏数。
4. **融合排序**：`score = w1*距离分 + w2*偏好匹配分 + w3*热度分`（权重常量放 config，便于运营调参）。

### 4.3 后端接口（新增 `routers/recommend.py` 或并入 catalog）

| Method | Path | 说明 | 守护 |
|--------|------|------|------|
| GET | `/recommend/plans?lat=&lng=&limit=` | 个性化方案推荐（定位+偏好） | `_require_user`（匿名可传定位降级） |
| GET | `/recommend/shops?lat=&lng=&limit=` | 附近同类店铺推荐 | 可选登录 |

- 内部调用 `storage/recommend.py`：读 favorites/orders 提偏好 → 与 plans/shops 算融合分 → 返回排序列表（复用现有 `_plan_card` / `_shop_card` 序列化，确保字段契约一致）。
- 无定位/无偏好时回退"热门/精选"（现有 Category 精选逻辑可复用），不报错。

### 4.4 前端改造（新增推荐位，沿用现有卡片组件）

- **首页 `Home.jsx`**：顶部定位区下方加"猜你喜欢"区块（调 `/recommend/plans`，渲染 `PlanCard` 横滑）。
- **店铺详情 `ShopDetail.jsx`**：底部加"附近同类店铺"区块（调 `/recommend/shops`，渲染 `ShopCard`）。
- **DIY 详情 `DiyDetail.jsx`**：相关推荐加"同风格方案"（按 `style` 相似 + 定位）。
- 所有推荐位：loading/empty（"暂无推荐，去看看精选"）/error 三态；传 `getLocation()` 坐标。
- 推荐位数据**全部来自 `/recommend/*`**，不前端写死列表。

### 4.5 验收（个性化推荐）

- [ ] 传 `lat/lng` 后推荐结果距离近者靠前；无定位时回退热门不崩。
- [ ] 收藏某风格方案后，"猜你喜欢"该风格权重上升（可用 seed 用户 `capri_demo` 验证）。
- [ ] 推荐接口返回字段与现有卡片组件契约一致（无 undefined）。
- [ ] 三个推荐位（首页/店铺页/DIY 详情）均渲染、三态完备。
- [ ] 后端 pytest：偏好提取 + 融合排序函数单测（含空偏好/空定位降级）。

---

## 5. 红线验收门禁（通用）

1. 每个新展示字段在后端有真实来源（DB 列或接口返回），前端无写死常量/假数组。
2. 新 DB 列/表随初始化幂等创建，seed 灌演示数据；上线前可整体清空重灌。
3. 每个页面/组件有 loading/empty/error 三态，不裸渲染 undefined。
4. 改动 DB 结构同步更新 seed 与前端字段契约；字段改名前后端同步。
5. 完成即补最小测试（后端 pytest 覆盖核心函数；前端沿用现有测试风格补充关键渲染）。

---

## 6. 不在本期范围（明确排除）

- 会员体系（用户 2026-08-19 明确"先别做"）。
- 全站搜索页 `/search`（用户认为无必要）。
- 真实微信订阅消息推送（形式 B，仅留 `push_channel` 占位，等 `WECHAT_APPID` 接入）。
- 真实微信/支付宝支付、真实物流 API、微信登录（等外部接入，本期仅 UI/seed 占位）。
- 管理员桌面后台独立工程（已存在于 `H5/src/admin/`，本期不扩展）。

---

## 7. 必读文件（执行前先 Read 完整内容）

后端：
- `storage/db.py`（表结构 + MIGRATIONS 幂等迁移写法，db.py:40/79/108/112-115/365/470-472）
- `storage/catalog.py`（`_haversine` catalog.py:33、`_shop_card`/`_plan_card` 序列化、店铺距离排序 catalog.py:9）
- `routers/commerce.py`（订单状态变更埋点位置）、`routers/merchant.py`（评价回复）、`routers/admin.py`（售后/公告）
- `storage/notify.py`（待新建，参考 `storage/admin.py` 写法）

前端：
- `H5/src/components/DiyPlanCard.jsx`（现有卡片 + `normalizePlan`，DiyPlanCard.jsx:23）
- `H5/src/utils/location.js`（`getLocation()` 返回 `{name,lat,lng}`）
- `H5/src/api/shop.js`（收藏 API shop.js:173-191、统一封装）
- `H5/src/pages/Settings.jsx`（通知开关占位 Settings.jsx:56）、`H5/src/components/TabBar.jsx`
- `H5/src/pages/Home.jsx` / `ShopDetail.jsx` / `DiyDetail.jsx`（推荐位植入点）

---

## 8. 交付清单（执行完成后应存在）

- [ ] `storage/db.py`：`notifications` 表 + DIY 新字段列 + 幂等迁移
- [ ] `storage/notify.py`：`create_notification()` + 列表/未读查询
- [ ] `routers/notify.py`：4 个通知端点 + 业务埋点（commerce/merchant/admin 内调用）
- [ ] `routers/recommend.py`（或并入 catalog）：2 个推荐端点
- [ ] `storage/recommend.py`：偏好提取 + 融合排序
- [ ] `H5/src/api/notify.js` + `H5/src/pages/Notifications.jsx`
- [ ] `DiyPlanCard.jsx` 扩充渲染 + `normalizePlan` 扩展
- [ ] `Home/ShopDetail/DiyDetail` 推荐位 + `TabBar` 红点
- [ ] seed 脚本：演示通知 + DIY 新字段值
- [ ] 测试：notify/recommend 后端 pytest + DiyPlanCard 归一化/通知页渲染前端测试
- [ ] 更新 `DEVELOPMENT_PLAN.md`（移除已完成的本期项，标注三模块状态）
