# 改进建议清单（IMPROVEMENT_PROPOSAL）

> 范围：基于实际代码审查（非功能缺失排查；功能完整度已由 `DATA_SOURCE_AUDIT.md` 锁定）。
> 审查日期：2026-08-19 ｜ 木木（Capri）要求"先不 commit，继续检查优化 + 改进建议"。
> 优先级：P0 上线前必修 ｜ P1 重要 ｜ P2 锦上添花/技术债。

## ✅ 本次已顺手修复（未 commit）

| # | 级别 | 问题 | 修复点 |
|---|------|------|--------|
| 1 | **P0 安全** | 购物车 `PUT/DELETE /cart/{item_id}` 不鉴权、存储层按 `item_id` 裸查 → 任意登录用户可改/删他人购物车（IDOR 越权） | `routers/commerce.py:83-95` 接入 `resolve_uid`；`storage/commerce.py` 的 `update_cart_item`/`remove_cart_item` 增加 `user_id` 归属校验（`WHERE item_id=? AND user_id=?`），缺失 `user_id` 直接拒绝；`del_cart` 不存在返回 404 |
| 2 | **P1 金额一致性** | Agent 会话"订单已创建"卡片 `calcPayable(total, discount)` 漏传运费，却写"含配送费"，与支付页口径不一致 | `H5/src/pages/Agent.jsx` 的 `OrderCard` 改从 `publicConfig().shipping_fee` 取运费传入 `calcPayable`，与 `Pay.jsx`/`OrderConfirm.jsx` 同源 |

---

## P0 — 上线前必须修

### [安全] 购物车越权（已修，见上）
`routers/commerce.py` 的 `put_cart`/`del_cart` 此前是整套购物车接口里**唯一**不调 `resolve_uid` 的两个端点，属典型 IDOR。已修复。

---

## P1 — 重要（建议本迭代处理）

### [真实 bug] Agent 运费漏算（已修，见上）
`Agent.jsx:OrderCard` 显示金额比支付页少一笔运费，文案却声称含运费。已修复。

### [安全] 生产鉴权默认关闭 + JWT 密钥空默认
`config.py:101,103`：`auth_required: bool = False`、`jwt_secret: str = ""`。上线若忘配会"裸奔"或令牌跨实例失效。
**建议**：启动期做 fail-fast 断言——`ENV=='prod'` 时强制 `jwt_secret` 非空且 `auth_required==True`，否则 `raise` 拒绝启动。改动量：小（config/startup 加校验）。

### [性能] 推荐算法 N+1 查询
`storage/recommend.py:158,168-171,221,231-234,252`：`SELECT * FROM plans` 全表载入后，循环内对每个 plan 单独查 `shops`（经纬度）+ `shop_plans`，方案数增长即线性放大 DB 往返。
**建议**：一次性 `JOIN`/`IN (...)` 批量取 `shop_id→(lat,lng)` 与 `plan_id→shop_id` 映射，Python 侧 dict 查表；距离计算所需坐标随 plans 一并查出。改动量：中（重写两个推荐函数取数部分）。

### [性能] 商家订单搜索框无防抖
`H5/src/pages/Merchant.jsx:1888`：`onChange` 直接 `setKeyword` → 进 `load()` 依赖数组 → 每敲一字发一次完整订单查询。
**建议**：`keyword`/`dateFrom`/`dateTo` 做 300ms 防抖（或 `onBlur`/搜索按钮触发）。改动量：小。

### [性能] 首页收藏状态串行 N 次请求
`H5/src/pages/Home.jsx:86-107`：对推荐卡片逐个 `await favoriteStatus(p.id)`，N 张卡 = N 次串行往返，且无批量接口。
**建议**：后端新增 `GET /favorites/status?plan_ids=a,b,c` 批量接口，前端一次取 `{plan_id: bool}`；或至少 `Promise.all` 并发。改动量：中（后端+前端）。

---

## P2 — 技术债 / 健壮性（按需）

### [UX] 购物车页加载失败无错误态
`H5/src/pages/Cart.jsx:22`：失败仅 `console.error`，页面停留 loading/空白无重试；金额直接 `{total}` 未 `toFixed(2)`。
**建议**：加 `error` 态 + 重试按钮；金额统一 `fmtMoney`/`toFixed(2)`。改动量：小。

### [技术债] `Merchant.jsx` 巨型单文件组件
约 2239 行 / ~48 个 `useState`，商家端订单/DIY 制作卡/统计全塞一起，维护与热更新成本高。
**建议**：按业务拆 `MerchantOrders`/`MerchantDiy`/`MerchantStats` 子路由，共用 hook 抽离取数。改动量：大（重构，建议单独排期）。

### [技术债] `fmtMoney` 多处重复定义
`Merchant.jsx:56` / `Orders.jsx:21` / `Logistics.jsx:10` / `admin/Orders.jsx:16` 各自实现同逻辑副本。
**建议**：抽到 `H5/src/utils/format.js` 统一导出全站引用。改动量：小。

### [技术债] `DiyPlanCard` 命名冲突
`Merchant.jsx:59`（商家本地版）vs `H5/src/components/DiyPlanCard.jsx:87`（共享顾客版）同名不同实现。
**建议**：商家版改名 `MerchantDiyPlanCard` 或挪 `Merchant/` 子目录，明确区分。改动量：小。

### [性能/安全] `reviews` 表缺索引
`storage/db.py:285-296`：`reviews` 有 `user_id`/`plan_id`/`order_id`/`status` 但建表/索引列表未覆盖，`getReviews`/后台审核/个人中心查询数据增长后全表扫描。
**建议**：补 `idx_reviews_plan`/`idx_reviews_order`/`idx_reviews_user`/`idx_reviews_status`（或组合 `(status, created_at)`）。改动量：小（加索引 + 迁移注释）。

---

## 已排除的伪问题（避免误报）
- **CORS 通配符 + credentials**：`api.py` 中 `if "*" in cors_origins: _allow_credentials=False` 是合规处理，非缺陷。
- **前端 `console.log` 残留**：`H5/src` 仅 `console.error/warn`（合理），无需清理。
- **XSS 向量**：全库无 `dangerouslySetInnerHTML`/`innerHTML`/`eval(`，无直接注入面。
- 红线②（前端写死）：本迭代前一轮已修运费双源/Profile 昵称/ShopDetail 公告三处，本次未发现新写死。

## 建议落地顺序
1. 本迭代收尾：P1 的「生产鉴权 fail-fast」「搜索防抖」「首页收藏批量接口」——成本低、收益高。
2. 下迭代：推荐 N+1、reviews 索引、fmtMoney 收敛、Cart 错误态。
3. 单独排期：Merchant 巨型组件拆分、DiyPlanCard 重命名。

> 注：所有代码改动均**未 commit**（按木木要求）。审查未改动文件：仅 `routers/commerce.py` / `storage/commerce.py` / `H5/src/pages/Agent.jsx` 三处。
