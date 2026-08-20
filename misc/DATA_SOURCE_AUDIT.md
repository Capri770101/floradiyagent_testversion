# 前端展示字段数据来源审计（2026-08-19）

> 目标：确认**前端每个页面的每个展示字段**都有**真实后端数据来源**（api→路由→storage→DB）+ **真实 seed 数据**，符合木木红线②（每处展示都有真实来源）。
> 方法：Explore 广度扫描 + 执行 AI **逐行 Read 复核 18+ 页面函数体**（吸取前几轮"凭 grep 快照把已实现当缺失"的误判教训，不信任快照）。

## 一、整体结论

**展示层数据纪律整体达标。** 绝大多数页面展示字段均来自 api 调用 → 后端路由 → storage 读 DB；**无前端写死业务数组/价格/实体名单**；seed 关键字段均有真实值。

## 二、真缺口清单（经逐行复核确认，非误判）

| # | 优先级 | 位置 | 问题 | 红线违反 | 修复方向 |
|---|--------|------|------|----------|----------|
| 1 | 🔴 P1 | `H5/src/utils/price.js:7` + `storage/config.py:24` + `OrderConfirm.jsx` + `Pay.jsx:113` | **运费双真理源**：`price.js` 写死 `SHIPPING_FEE=20`，后端 seed 默认 `shipping_fee=5`。OrderConfirm 行项显¥5，但 `total=calcPayable`（引 price.js）内部 +20 → 页内自相矛盾；Pay 页显¥20 | 红线② 单一数据源 | 删 `price.js` 写死，统一从 `publicConfig().shipping_fee` 取（OrderConfirm 已这样取，Pay/calcPayable 跟进） |
| 2 | 🟡 P2 | `Profile.jsx:506` | 会员卡"金牌会员"写死，无真实后端来源（会员体系已被木木排除，属未建功能占位） | 红线② | 隐藏该展示，或接真实等级字段 |
| 3 | 🟡 P2 | `ShopDetail.jsx:81` | 公告展开追加固定文案"本店花材每日现采，支持同城速递…"（接在真公告 `shop.notice` 后，非业务字段替代） | 轻微 | 可保留（补充说明）或后端化进配置 |
| 4 | 🟡 P2 | `Logistics.jsx` | 状态徽章配色全为同一粉色（文案正确：待付款/待发货/配送中/已完成/已取消，但视觉无区分） | 视觉瑕疵 | 按状态分色（参考 Orders.jsx 多色映射） |
| 5 | ⚪ 代码瑕疵 | `ShopDetail.jsx:184-191` 与 `217-224` | 重复声明 `useRecommend`（recShops/recState 声明两次，后者覆盖前者） | 非数据 | 删其中一处重复声明 |

## 三、已达标证据（防止重复之前误判）

- **所有页面展示字段 API 驱动**：Home/ShopDetail/Merchant/ProductDetail/Cart/Category/CouponCenter/Favorites/Addresses/Settings/About/Notifications/MyAftersales/MerchantApply/OrderConfirm/Pay/Profile/Service/Logistics/Orders 均通过 `getX()/listX()` 取数，无写死业务数组。
- **ShopDetail 全字段有源 + seed 真实**：`get_shop` 返回 `name/rating/sales/distance_km/status/min_delivery/delivery_fee/delivery_time/notice/hours/address/logo/menu`，seed 主路径 `catalog.py:688-714` **完整灌入**所有字段真实演示值（sales=200+hash%800、min_delivery 按价格推导、delivery_fee 按距离 3/5/8、hours=09:00-21:00、address=深圳市盐田区海景路X号、notice=真实文案）。
- **plans 关键字段 seed 真实**：`ai_reason`/`rating`/`sold` 经 `catalog.py:676-731` 兜底（无值则生成真实文案/确定性数值）。
- **三大"新功能"（通知/DIY卡片/推荐）早已实现且前端接好**，非本审计范围重复项。

## 四、修复优先级建议

1. **先做 #1（P1 运费冲突）**：唯一确实的"数据不一致"真 bug，踩红线②单一数据源，且用户体感直接（看到三个不同运费）。修复低风险（删写死+统一取后端值）。
2. **#4（Logistics 配色）**：纯前端视觉，低风险。
3. **#2/#3（P2 写死）**：会员体系已排除，建议隐藏占位或后端化，不阻塞。
4. **#5（代码瑕疵）**：顺手清理。

## 五、备注

- `catalog.py:1233` 的 `create_shop` INSERT 仅插 10 字段（缺经营信息列）——那是**商家入驻新建店铺**路径，非 seed 主路径；演示数据完整性不受影响（seed 走 688-714 完整路径）。
- 本审计仅覆盖"前端展示字段来源"，不含后端内部逻辑/性能/安全（那些是另一维度）。
