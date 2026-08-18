# 前后端字段契约（FIELD CONTRACT）

> 版本：2026-08-18（计划书阶段0产出，随代码演进更新）
> 口径（计划书红线2）：前端每处展示字段必须有真实后端数据来源；禁止前端硬编码业务数据。后端序列化器缺失字段可兜底默认值（DB 缺省/兼容 Mock 数据源），前端不做业务兜底。
> 本文档同时作为「阶段4 契约走查」的验收标尺：逐条核对，任一「前端写死」出现即判不通过。

---

## 0. 全局约定

| 项 | 约定 |
|---|---|
| 后端基址 | `http://localhost:8080/api`（H5 经 vite 代理 `/api`，见 `H5/vite.config.js`） |
| 鉴权 | JWT（`Authorization: Bearer`）；dev 模式 `auth=dev`，未登录 401 由前端 `handleAuthFailure` 清会话 |
| 数据源 | 配置 `data_source=mock` 时商品/店铺列表走内存种子，DIY 资产库与订单等业务数据一律走 SQLite `data/agent_service.db` |
| 序列化器 | 列表卡 `_plan_card` / `_shop_card`，详情 `_plan_full` / `_shop_full`（`routers/common.py`）；DIY 资产 `storage/diy.py::_row_to_plan` |
| 状态机 | 订单状态：`created → pending_payment → paid → shipped → done`，任意态可 `canceled`；徽章样式统一走 `H5/src/utils/status.js` |
| 金额 | 一律后端数值，前端 `fmtMoney` 格式化展示，不参与计算推导 |

---

## 1. 商品与店铺（`routers/catalog.py`）

### 1.1 方案列表卡 `_plan_card`（GET `/plans`，`H5/src/api/shop.js::listPlans`）

| 前端字段 | 后端来源 | 备注 |
|---|---|---|
| id / name / price | `plans.id / name / price` | |
| merchant_name | `plans.merchant_name` | 购物车/下单/展示商家名唯一来源 |
| shop_id | `plan_shop_id(plan_id)`（`shop_plans` 关联） | 跳店铺页 |
| label | `_plan_label`（DB desc/价格推导角标） | 展示角标 |
| rating / sold | `plans.rating / plans.sold` | 缺失兜底 4.8 / 0 |
| tags / desc / style | `plans.tags(JSON) / desc / style` | |
| image | 恒 `null`，前端占位色块 | 契约允许（UI 设计如此） |

### 1.2 方案详情 `_plan_full`（GET `/plans/{plan_id}`，`getPlan`）

| 前端字段 | 后端来源 | 备注 |
|---|---|---|
| 全部 `_plan_card` 字段 | 同上 | |
| detail | `plans.desc` | |
| aiReason | **`plans.ai_reason`（DB，T1-3 后）** | 缺失兜底：模板句（见 `common.py`） |
| main_flowers | `plans.main_flowers` | 缺失兜底：从 desc 首句解析（`_derive_flowers`） |
| packaging | `plans.packaging` | 缺失兜底：按商品名推导（`_derive_packaging`） |
| effect_image_url / style | `plans.effect_image_url / style` | |

### 1.3 店铺列表卡 `_shop_card`（GET `/shops`，`listShops`）

| 前端字段 | 后端来源 | 备注 |
|---|---|---|
| id / name / rating | `shops.id / name / rating` | |
| dist | 定位时 `distance_km()` 经纬度实算，否则 `shops.distance_km` | 展示 `{x.x}km` |
| eta | 常量「配送约30分钟」（后端字段） | 与 `delivery_time` 同源待统一（T1-2 后由 DB 列覆盖） |
| price_range / min_delivery / delivery_fee | `shops.price_range / min_delivery / delivery_fee` | 缺失兜底按价位档/距离推导 |
| image | `shops.image` | 商家上传 |

### 1.4 店铺详情 `_shop_full`（GET `/shops/{shop_id}`，`getShop`）

| 前端字段 | 后端来源 | 备注 |
|---|---|---|
| id / name / rating / status | `shops.*` | status 常量「营业中」（DB 列） |
| dist | `shops.distance_km`（T2-1 后前端读 `distance_km`） | |
| intro / sales / min_delivery / delivery_fee | `shops.intro / sales / min_delivery / delivery_fee` | |
| delivery_time | **`shops.delivery_time`（T1-2 后）** | 缺失兜底「30分钟」 |
| hours / address / notice | `shops.hours / address / notice` | |
| image / cover / logo | `shops.image / cover / logo` | 商家上传 |
| menu | 按 `categories` 排序分组 `shop_plans` 在售商品（`_shop_menu_item`） | 分类/商品项字段见 1.5 |
| recommend | `shop_plans` 关联方案 id/name/price | |

### 1.5 菜单项 `_shop_menu_item`（店铺详情内）

id / name / price / desc / tags / style / image / label / sales ← `plans.*`（image=effect_image_url，sales=sold）。

### 1.6 DIY 方案（`storage/diy.py::_row_to_plan`，GET `/plans/{plan_id}` 回落）

| 前端字段 | 后端来源 |
|---|---|
| id / name / requirement / recipient / occasion / style / budget | `diy_plans.*` |
| color_scheme / flowers / packaging / meaning / diy_steps / care_tips / card_message / budget_breakdown / effect_image_url | `diy_plans.*`（JSON 反序列化） |
| effect_prompt / design / main_flowers | 由行内花材/色系/包装合成（T1-3 评估后可选落列） |
| status / order_count | `diy_plans.status / order_count` |

> 注意：DIY 方案**不走 `_plan_full`**（会丢弃 DIY 专属字段）；详情直链与「确认方案」入参结构一致（前端 `DiyDetail.normalizePlan` 直接消费）。

---

## 2. 认证与会话（`routers/auth.py` / `chat.py`）

| 页面 | 端点 | 关键字段与来源 |
|---|---|---|
| 登录/注册 | `POST /auth/login` / `/auth/register` / `/auth/phone-login` | 返回 `{token, user}`；`user` = users 表（id/username/nickname/phone/role/avatar） |
| 我的（信息） | `GET /auth/me` | `{user}`；未登录 200 `{user:null}`（非 401） |
| Agent 会话 | `GET/POST /conversations`、`GET /conversations/{id}/messages`、`PATCH /conversations/{id}`、`DELETE /conversations/{id}` | messages.ui / messages.data 为回放结构化字段 |
| 对话 | `POST /chat` | LLM 编排，返回消息流；`request_timeout=180s`（配置 `config.py`） |
| 效果图 | `POST /image/generate` + `GET /tasks/{task_id}` | 生成任务轮询（image_mode=live） |

---

## 3. 交易链路（`routers/commerce.py`）

| 页面 | 端点 | 关键字段与来源 |
|---|---|---|
| 购物车 | `GET/POST /cart`、`PUT/DELETE /cart/{item_id}`、`POST /cart/merge` | 行项目：plan_id/name/price/shop/image/plan_type；`items` JSON |
| 下单 | `POST /orders` | 入参 `{items, recipient, delivery, note, coupon_id}`；shop 由入参透传（DIY 方案为空串→落库 NULL，展示处条件渲染） |
| 订单列表/详情 | `GET /orders`、`GET /orders/{order_id}` | order_id/user_id/status/paid/items/total_price/recipient_*/delivery_time/note/expires_at/logistics（`order_logistics` 时间线 seq/text/created_at） |
| 订单操作 | `POST /orders/{order_id}/action` | cancel/pay 等状态机动作 |
| 支付 | `POST /pay`（沙箱）、`POST /pay/notify/{provider}`、`GET /pay/{order_id}/status` | 支付记录 payments 表；沙箱页展示 |
| 优惠券 | `GET /coupons`、`GET /coupon-offers`、`POST /coupon-offers/{offer_id}/claim` | coupons/offers 表 |
| 积分 | `GET /points` | 用户积分 |
| 地址 | `GET/POST /addresses`、`PUT/DELETE /addresses/{addr_id}` | 收货人/电话/地址 |
| 收藏 | `GET/POST /favorites`、`DELETE /favorites/{plan_id}`、`GET /favorites/{plan_id}/status` | 未登录 `{favorited:false}`（200） |
| 评价 | `POST /reviews`、`GET /reviews?plan_id=` | 评分/内容/追评 |

### 3.1 配送时段（T2-3 过渡态）

- `OrderConfirm` 配送时段选项当前集中定义于 `H5/src/config/shop.js`（`DELIVERY_OPTIONS`），**计划书批准为临时集中常量**，注释标注待后端「配送配置接口」后迁移；
- 订单保存的 `delivery_time` 已落库（`orders.delivery_time`），物流页回显，非前端写死。

---

## 4. 商家端（`routers/merchant.py`）

| 页面 | 端点 | 说明 |
|---|---|---|
| 概览统计 | `GET /merchant/stats` | 订单统计/收入 |
| 店铺 | `GET /merchant/shops`、`PUT /merchant/shop/{shop_id}` | 商家绑定店铺（`merchant_shops` 权限隔离） |
| 订单 | `GET /merchant/orders`、`GET /merchant/orders/{order_id}`、`POST .../ship`、`POST .../logistics` | 商家发货/追加物流节点 |
| 商品 | `GET/POST /merchant/plans`、`PUT /merchant/plans/{id}`、`POST /merchant/plans/{id}/toggle`、`DELETE /merchant/plans/{id}` | 上下架（`shop_plans.status`） |
| 分类 | `GET/POST /merchant/categories`、`PUT/DELETE /merchant/categories/{id}` | **Admin 端分类下拉同源复用（T2-4）** |
| 评价 | `GET /merchant/reviews`、`POST /merchant/reviews/{id}/reply` | 店铺评价列表；回复写 `reviews.reply / reply_at`（商家中心 T1-3） |
| 会话 | `GET /merchant/chats`、`GET/POST /merchant/chats/{id}/messages` | 商家-顾客会话（`shop_chats`/`chat_messages` 表）；商家读取即清 `unread_merchant`，发送写 `unread_user+1` |
| 上传 | `POST /merchant/upload` | 图片上传 |

### 4.1 商家-顾客会话（商家中心新增，`routers/chats.py` + `merchant.py`）

| 前端字段 | 后端来源 | 备注 |
|---|---|---|
| 会话列表（商家侧） | `GET /merchant/chats` | id/shop_id/shop_name/nickname/avatar/last_msg/last_at/unread_merchant；按绑定店铺隔离，`last_at` 倒序 |
| 会话列表（顾客侧） | `GET /chats/shop/{shop_id}` | 取或建会话（店铺+顾客唯一），返回 chat/messages/shop_name |
| 消息 | `chat_messages.content/created_at/sender` | sender: `user`(顾客)/`merchant`(商家)；读取即清本侧未读 |
| 发送 | `POST /chats/{chat_id}/messages`（顾客）、`POST /merchant/chats/{chat_id}/messages`（商家） | 请求体 `{content}`，1-1000 字 |
| 评价回复 | `reviews.reply / reviews.reply_at` | `POST /merchant/reviews/{id}/reply` 写入；评价列表回显 |

## 5. 管理后台（`routers/admin.py`）

| 端点 | 说明 |
|---|---|
| `GET/POST /admin/plans`、`PUT/DELETE /admin/plans/{id}` | 商品管理 |
| `GET/POST /admin/shops`、`PUT/DELETE /admin/shops/{id}` | 店铺管理 |
| 权限 | 非 admin 角色 403；前端预检 `getProfile` 角色后**不发请求** |

---

## 6. 当前例外与历史修正

| 项 | 状态 | 说明 |
|---|---|---|
| DIY 直链 `/plans/DIY_*` | ✅ 已修 | 回落 `diy_plans` 原样返回，不过 `_plan_full` |
| DIY 生成 504 | ✅ 已修 | `request_timeout=180s` + 前端 504 友好文案 |
| 未登录 `/auth/me`、收藏状态 | ✅ 已修 | 200 + 空值（非 401） |
| 前端 401 噪音 | ✅ 已修 | `handleAuthFailure` 统一清会话 |
| 商家/管理端权限预检 | ✅ 已修 | 无权限不发请求 |
| 商家名兜底字面量（`'跳舞兰'`） | ✅ 已修（T2-2） | 读 `merchant_name`；DIY 无关联店铺传空 |
| `shops.delivery_time` / `plans.ai_reason` 列 | ✅ 已补（T1-2/T1-3） | 迁移 + seed + 序列化器优先读 DB |
| 距离字段 | ✅ 已统一（T2-1） | 后端 `_shop_full` 返回 `distance_km`，前端读数值 |
| 订单状态徽章 | ✅ 已统一（T2-5） | `H5/src/utils/status.js` 共享 |
| 死代码 | ✅ 已删（T2-6） | `PlanCard.jsx`、`merchantShops` |
| 商家中心 C 端跳转 | ✅ 已修（商家中心 T2-1/T2-2） | `Merchant.jsx` 已移除 `nav('/shop/`、`nav('/logistics/`；店铺/物流改商家内部预览（店铺设置 Tab / 物流 Tab 展开该单） |
| 商家-顾客会话 | ✅ 已修（商家中心 T1-3/T1-4） | `shop_chats`/`chat_messages` 表 + 双侧端点 + 商家中心「会话」Tab（列表/未读/消息气泡/发送）已接入 |
| 评价回复 | ✅ 已修（商家中心 T1-1/T1-3） | `reviews.reply/reply_at` 列 + `POST /merchant/reviews/{id}/reply` + 评价管理 Tab 回复 UI（发布/回显）已接入 |

---

## 7. 走查验收口径

1. 逐页 grep 前端：`跳舞兰|Capri|约30分钟|DELIVERY_OPTIONS|CATEGORIES` 等业务字面量 → 只允许出现在契约指定的集中常量/工具文件；
2. 逐字段核对本文档表格；后端序列化器字段缺失即记「字段缺口」；
3. 前端 mock 路径（`data_source=mock`）与 DB 路径行为一致（兜底仅在后端层）。