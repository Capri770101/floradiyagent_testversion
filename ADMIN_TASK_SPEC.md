# 管理员界面 任务书（AI 实现版 / Prompt Spec）

> 文档性质：给**执行 AI（含本智能体）**直接消费的实现任务书，非人类阅读报告。
> 配套文档：`DEVELOPMENT_PLAN.md`（通用前端缺口计划）、`MEMORY.md`（项目红线与约定）。
> 生成日期：2026-08-18 · 状态：待评审 · 范围：**仅当前阶段可独立完成部分**（不含真实支付网关/快递 API/微信登录/千问平台）。

---

## 0. SYSTEM PROMPT（执行 AI 请采用此身份）

```
你正在实现 flora_diy_agent（花卉 DIY 智能体电商平台）的【平台管理员后台】。
技术栈：后端 FastAPI + Pydantic v2 + SQLite（storage/*）；前端独立桌面 SPA = Vite + React + TypeScript + Ant Design 5。
你必须：
1. 严格遵守下方「硬约束」与「两条红线」，违反即返工。
2. 每个模块按「后端接口 → 数据表 → 前端组件 → 验收」四步交付，不跳步。
3. 改任何 DB schema 必须同步更新 seed 脚本与字段契约，禁止破坏现有数据。
4. 所有新增管理员端点必须用 `_require_admin` 守护（role=admin 才放行）。
5. 优先复用现有代码（routers/admin.py / routers/common.py / storage/db.py / storage/catalog.py / METRICS 单例），不重复造轮子。
6. 不引入未经授权的第三方依赖；UI 组件优先 Ant Design 标准件（Table/Form/Modal/Drawer/Statistic）。
7. 真实数据驱动，缺失数据用 seed 假数据填充（上线前可清空重灌），禁止前端写死或 mock。
8. 交付时附带最小 pytest（后端）+ 渲染测试（前端），并跑通 ruff/eslint。
```

---

## 1. 硬约束（必读，违反即返工）

- **红线1（完成标准）**：所有功能按**可上线**标准做。暂无真实接口/平台时，UI 做完整 + 标准 DB 结构先建 + 缺数据用 seed 填充（上线前整体清空重灌）。**不允许留空壳或写死占位**。
- **红线2（数据纪律）**：前端**每一处展示字段都必须有真实后端来源**，禁止前端硬编码假数据/写死常量；前后端就字段建立契约，逐页审计对齐。
- **架构隔离**：管理员后台是**独立 `admin/` 桌面 SPA**，**不复用 H5 bundle、不把 admin 入口/逻辑打进公开移动端**。理由：用户明确担忧"扩 H5 有域名/入口暴露风险"——独立部署（建议独立子域或 `/admin` 独立路径 + 独立构建）可隔离攻击面。后端仍复用同一 FastAPI 实例的 `/admin/*` 端点。
- **鉴权复用**：登录走现有 `/auth/login` + JWT；admin SPA 仅在携带 `role=admin` 的 JWT 时渲染管理界面。后端 `_require_admin`（`routers/common.py:456`）已就位，只需确保有 admin 账号。
- **幂等建表**：所有新表用 `CREATE TABLE IF NOT EXISTS`，新增列用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（SQLite 兼容写法），并同步更新 `scripts/seed_*.py`。
- **外部依赖**：真实微信/支付宝退款、快递 API、微信登录、千问平台**不在本阶段**——对应功能仅做 UI + sandbox/seed 验证，明确标注"生产接 XXX"。

---

## 2. 架构与部署形态

```
flora_diy_agent/
├── api.py / routers/          # 现有 FastAPI 后端，新增 /admin/* 端点
├── storage/                   # db.py(建表) / catalog.py / commerce.py / common.py
├── scripts/                   # seed_*.py（含新增 seed_admin.py / seed_merchant_app.py）
├── H5/                        # 现有移动端（不动其 admin 入口，仅保留只读快捷查看可选）
└── admin/                     # 【新建】独立桌面管理后台 SPA
    ├── package.json           # vite + react + ts + antd + axios
    ├── src/
    │   ├── main.tsx / App.tsx # 路由 + Antd ConfigProvider（中文 zhCN）
    │   ├── auth/              # login + token 存储 + 路由守卫（无 admin JWT → /login）
    │   ├── api/               # 封装 /admin/* 调用（统一 axios 实例 + Bearer）
    │   ├── layout/            # 左侧菜单 + 顶栏（Antd Layout/Sider/Menu）
    │   └── modules/           # 各模块页面（见 §4）
    └── vite.config.ts         # 代理 /api → 后端，独立 devServer 端口
```

前端调用约定：admin SPA 用独立 axios 实例，所有请求带 `Authorization: Bearer <admin_jwt>`；后端返回 401/403 时前端跳登录。

---

## 3. 模块清单与执行顺序

| Phase | 模块 | 说明 | 是否用户点名 |
|-------|------|------|--------------|
| P0 | **M0 账号与权限** | seed admin 账号 + 角色提升工具（blocker：否则后台登不进） | — |
| P1 | **M1 目录管理补全** | plan/shop CRUD 已有；补 `menu` 聚合、`ai_reason` 等 | — |
| P2 | **M2 用户管理** | 列表/查看/禁用/提权（需 `users.status` 列） | — |
| P2 | **M7 运营配置** | 配送选项/分类/运费/优惠券后端化（灭前端写死） | — |
| P3 | **M3 订单管理** | admin 全局订单视角 + 状态干预 | — |
| P3 | **M4 售后** ★ | aftersales 表 + 审核/退款（用户点名） | ✅ |
| P4 | **M5 商家入驻办理审核** ★ | merchant_applications 表 + 审核流（用户点名） | ✅ |
| P5 | **M6 评价审核** | 列表/隐藏/显示/删除（需 `reviews.status` 列） | — |
| P5 | **M9 内容管理** | FAQ/公告后端化（灭前端写死） | — |
| P6 | **M8 数据看板** | 复用 `METRICS` 单例 | — |

---

## 4. 模块详细规格（后端接口 / 数据表 / 前端组件 / 验收）

### M0 账号与权限（P0 · blocker）

**目标**：让管理员能登进后台；提供角色提升能力。

**后端**：
- 复用 `/auth/login`、`/auth/me`（已有）。admin 校验靠 `_require_admin`。
- 新增端点：`POST /admin/users/{user_id}/role` → body `{role: "user"|"merchant"|"admin"}`，改 `users.role`；守护 `_require_admin`。

**数据表**：`users` 表**新增列**（db.py:40 附近）：
```sql
ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active';  -- active | banned
```
（`role` 列已存在，默认 'user'；`status` 用于禁用。）

**Seed / 工具**：
- 新建 `scripts/seed_admin.py`：用 env `ADMIN_USERNAME`/`ADMIN_PASSWORD`（默认演示 `admin`/`admin123456`，**仅演示、上线前改 env**）创建 admin 用户（走现有用户注册/密码哈希逻辑）。幂等（已存在则跳过）。
- 新建 `scripts/promote.py --user <uid> --role admin`：CLI 提权，便于把任意账号设为 admin。

**前端（admin/）**：`auth/Login.tsx`（账号密码 → `/auth/login` → 存 JWT → 路由守卫 `auth/Guard.tsx` 校验 `role===admin` 否则跳登录）+ `layout/` 顶栏显示当前管理员。

**验收**：seed 后 `admin/admin123456` 能登录并看到后台骨架；普通用户 `capri_demo` 访问 `/admin/*` 返回 403。

---

### M1 目录管理补全（P1）

**目标**：补全 ShopDetail "进店无商品" 真空壳 + 字段对齐。

**后端**：
- `catalog.py` 的 `get_shop`（`_row_to_shop`）**聚合返回 `menu`**：结构 `[{category, items:[{id,name,price,desc,image}...]}]`，来源 `shop_plans` 关联 `plans` + `categories`。
- `distance_km` 已返回；`delivery_time` 列已存在（db.py:122）且 `_row_to_shop` 已返回——**无需加列**。
- 注意：`ShopDetail.jsx` 前端读 `shop.dist`（错）应改读 `shop.distance_km`（属于 H5 侧修复，见 `DEVELOPMENT_PLAN.md` R2-1，不在 admin SPA 范围）。

**前端（admin/）**：`modules/Catalog/PlanList.tsx`、`ShopList.tsx`（复用现有 `Admin.jsx` 的 PlanForm/ShopForm 逻辑迁移到 antd Form）。

**验收**：`GET /admin/shops/{id}` 返回含 `menu`；admin 可增删改方案/店铺。

---

### M2 用户管理（P2）

**后端**：
- `GET /admin/users` → 分页 + 筛选 `?role=&keyword=&status=`
- `GET /admin/users/{user_id}`
- `POST /admin/users/{user_id}/ban` → `users.status='banned'`
- `POST /admin/users/{user_id}/unban` → `users.status='active'`
- （`POST /admin/users/{user_id}/role` 已在 M0 定义）

**数据**：`users.status` 列（M0 已加）。

**前端**：`modules/Users/UserList.tsx`（antd Table：昵称/手机/角色/状态/注册时间 + 操作下拉：禁用/启用/提权）。

**验收**：列表可筛选；禁用后该用户登录被拒（需在 `/auth/login` 或 resolver 中校验 `status==='banned'` → 401）。

---

### M3 订单管理（P3 · admin 全局视角）

**后端**：
- `GET /admin/orders` → 全部订单，筛选 `?status=&user_id=&shop_id=&date_from=&date_to=`，分页
- `GET /admin/orders/{order_id}`
- `POST /admin/orders/{order_id}/status` → body `{status}`，admin 干预改 `orders.status`（绕过商家/用户流程）
- （可选）`GET /admin/orders/export` → CSV

**数据**：复用 `orders` 表（现状：order_id,user_id,plan_id,shop_id,items,total_price,status,paid,paid_at,expires_at,recipient_*,delivery_time,note）。**无需新表**。

**前端**：`modules/Orders/OrderList.tsx` + `OrderDetail.tsx`（Drawer 展示 items/收货人/支付/物流）+ 状态修改 Modal。

**验收**：admin 能看到全平台订单；可强行改状态且落库。

---

### M4 售后（P3 · ★用户点名）

**目标**：用户发起售后（退款/退货/换货），管理员审核并触发退款。

**数据表**（新建，`storage/db.py`）：
```sql
CREATE TABLE IF NOT EXISTS aftersales (
    id            TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    shop_id       TEXT,
    type          TEXT NOT NULL DEFAULT 'refund',   -- refund|return|exchange
    reason        TEXT,
    description   TEXT,
    evidence_imgs TEXT,                              -- JSON 数组（图片路径）
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending|approved|rejected|refunded|closed
    refund_amount REAL,
    handled_by    TEXT,
    handled_at    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

**后端**：
- 用户侧（在 `routers/commerce.py` 或 orders 域）：`POST /orders/{order_id}/aftersale` → 创建售后单（需登录 + 订单归属本人）；`GET /orders/{order_id}/aftersales`；`GET /me/aftersales`
- 管理侧（`routers/admin.py`）：
  - `GET /admin/aftersales` → 筛选 `?status=`
  - `GET /admin/aftersales/{id}`
  - `POST /admin/aftersales/{id}/approve` → `status='approved'`
  - `POST /admin/aftersales/{id}/reject` → body `{note}`，`status='rejected'`
  - `POST /admin/aftersales/{id}/refund` → `status='refunded'`，并联动：`payments.status='refunded'`（sandbox 模拟；真实网关接 wechat/alipay 退款 API 时再接）、订单可按需标记

**前端**：`modules/Aftersales/AftersaleList.tsx` + 审核 Drawer（查看证据图、通过/拒绝/退款按钮）。

**验收**：用户创单 → admin 列表可见 → 审核通过/拒绝/退款后状态与 payments 联动落库。

---

### M5 商家入驻办理审核（P4 · ★用户点名）

**目标**：商家提交入驻申请（执照等），管理员审核通过后成为 merchant 并绑定/创建店铺。

**数据表**（新建）：
```sql
CREATE TABLE IF NOT EXISTS merchant_applications (
    id                TEXT PRIMARY KEY,
    applicant_user_id TEXT NOT NULL,                -- 申请人 users.id（提交时可为 role=user）
    shop_name         TEXT NOT NULL,
    contact_name      TEXT,
    contact_phone     TEXT,
    license_no        TEXT,
    license_img       TEXT,                          -- 执照图片路径
    address           TEXT,
    intro             TEXT,
    status            TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected
    review_note       TEXT,
    reviewed_by       TEXT,
    reviewed_at       TEXT,
    created_at        TEXT NOT NULL
);
```

**后端**：
- 申请侧（公开/登录即可，在 `routers/merchant.py` 或新 `routers/merchant_apply.py`）：`POST /merchant/apply` → body 含上述字段（需登录；申请人角色不限 user）
- 管理侧（`routers/admin.py`）：
  - `GET /admin/merchant-applications` → 筛选 `?status=`
  - `GET /admin/merchant-applications/{id}`
  - `POST /admin/merchant-applications/{id}/approve` → `status='approved'`；**副作用**：把 `applicant_user_id` 的 `role` 改为 `merchant`，并创建/绑定 `shops` 记录 + `merchant_shops` 绑定（shop 名取 `shop_name`，其余经营信息给默认值，后续商家后台补全）
  - `POST /admin/merchant-applications/{id}/reject` → body `{note}`，`status='rejected'`
  - `GET /admin/merchants` → 已入驻商家列表（来自 `merchant_shops` 关联）

**前端**：`modules/MerchantApply/ApplicationList.tsx` + 审核 Drawer（查看执照图、通过/拒绝带备注）。

**验收**：提交申请 → admin 列表待审 → 通过后该用户 `role=merchant` 且出现在其商家后台；拒绝带备注落库。

---

### M6 评价审核（P5）

**后端**：
- `GET /admin/reviews` → 筛选 `?status=visible|hidden`
- `POST /admin/reviews/{id}/hide` → `reviews.status='hidden'`
- `POST /admin/reviews/{id}/show` → `reviews.status='visible'`
- `DELETE /admin/reviews/{id}`

**数据**：`reviews` 表（db.py:277）**新增列**：
```sql
ALTER TABLE reviews ADD COLUMN status TEXT NOT NULL DEFAULT 'visible';  -- visible | hidden
```

**前端**：`modules/Reviews/ReviewList.tsx`（Table + 隐藏/显示/删除）。

**验收**：隐藏后该评价在前端详情页不再展示（H5 侧评价列表需按 `status='visible'` 过滤，属 H5 修复，不在 admin SPA 但需约定）。

---

### M7 运营配置（P2 · 灭前端写死）

**目标**：把前端写死的 `DELIVERY_OPTIONS`/`CATEGORIES`/运费等搬后端，统一来源（红线2）。

**数据表**（新建 key-value）：
```sql
CREATE TABLE IF NOT EXISTS operations_config (
    key   TEXT PRIMARY KEY,     -- e.g. shipping_fee | delivery_options | coupon_rules
    value TEXT                  -- JSON 字符串
);
```

**后端**：
- `GET /admin/config` / `PUT /admin/config` → body `{shipping_fee, delivery_options[], coupon_rules{}}`，读写 `operations_config`
- `GET/POST/PUT/DELETE /admin/categories` → 分类 CRUD（与商家端 `merchantCategories` 同源；`categories` 表已存在 db.py:52）

**前端**：`modules/Config/ConfigForm.tsx`（运费输入、配送时段动态增删、优惠券规则）+ `Categories.tsx`（分类 CRUD Table）。

**验收**：admin 改配送时段后，H5 `OrderConfirm` 的 `DELIVERY_OPTIONS` 改为读此配置（H5 侧修复，红线2）。

---

### M8 数据看板（P6）

**后端**：`GET /admin/dashboard` → 返回
```json
{
  "gmv": 0, "order_count": 0, "user_count": 0, "new_users_today": 0,
  "top_plans": [{"plan_id":"","name":"","sold":0}],
  "top_shops": [{"shop_id":"","name":"","sales":0}],
  "order_trend": [{"date":"","count":0,"amount":0}]
}
```
实现复用 `routers/common.py` 已导入的 `METRICS` 单例（若其方法不足，在 storage 层补聚合查询，不重复造）。

**前端**：`modules/Dashboard/index.tsx`（antd `Statistic` 卡片 + `Line`/`Bar` 图，可用 `@ant-design/charts` 或轻量 `recharts`）。

**验收**：看板数字与 DB 聚合一致；seed 多订单后趋势图有数据。

---

### M9 内容管理（P5 · 灭前端写死）

**目标**：FAQ、公告后端化（替代 H5 写死的 `FAQS`/公告文案）。

**数据**：复用 `operations_config`，键 `faqs`(JSON 数组)、`announcements`(JSON 数组)；或独立 `content` 表。

**后端**：`GET/PUT /admin/content/faqs`、`GET/PUT /admin/content/announcements`。

**前端**：`modules/Content/FaqEditor.tsx`（可增删 FAQ 条目）、`AnnouncementEditor.tsx`。

**验收**：admin 改 FAQ 后，H5 `Service` 页 FAQ 区改为读后端（H5 侧修复，红线2）。

---

## 5. 接口总表（REST 速查，全部 `_require_admin` 守护除非注明）

| Method | Path | 模块 | 守护 |
|--------|------|------|------|
| POST | `/auth/login` | 登录（复用） | 公开 |
| GET | `/auth/me` | 当前用户（复用） | 登录 |
| GET/POST/PUT/DELETE | `/admin/plans...` `/admin/shops...` | M1 目录（已有） | admin |
| POST | `/admin/users/{id}/role` | M0/M2 提权 | admin |
| GET | `/admin/users` | M2 用户列表 | admin |
| GET | `/admin/users/{id}` | M2 用户详情 | admin |
| POST | `/admin/users/{id}/ban` `/unban` | M2 禁用/启用 | admin |
| GET | `/admin/orders` | M3 订单列表 | admin |
| GET | `/admin/orders/{id}` | M3 订单详情 | admin |
| POST | `/admin/orders/{id}/status` | M3 状态干预 | admin |
| POST | `/orders/{id}/aftersale` | M4 用户创单 | 登录(本人) |
| GET | `/me/aftersales` | M4 我的售后 | 登录 |
| GET | `/admin/aftersales` | M4 售后列表 | admin |
| GET | `/admin/aftersales/{id}` | M4 售后详情 | admin |
| POST | `/admin/aftersales/{id}/approve` `/reject` `/refund` | M4 审核/退款 | admin |
| POST | `/merchant/apply` | M5 提交入驻 | 登录 |
| GET | `/admin/merchant-applications` | M5 申请列表 | admin |
| GET | `/admin/merchant-applications/{id}` | M5 申请详情 | admin |
| POST | `/admin/merchant-applications/{id}/approve` `/reject` | M5 审核 | admin |
| GET | `/admin/merchants` | M5 已入驻 | admin |
| GET | `/admin/reviews` | M6 评价列表 | admin |
| POST | `/admin/reviews/{id}/hide` `/show` | M6 隐藏/显示 | admin |
| DELETE | `/admin/reviews/{id}` | M6 删除 | admin |
| GET/PUT | `/admin/config` | M7 运营配置 | admin |
| GET/POST/PUT/DELETE | `/admin/categories` | M7 分类 | admin |
| GET | `/admin/dashboard` | M8 看板 | admin |
| GET/PUT | `/admin/content/faqs` `/announcements` | M9 内容 | admin |

---

## 6. 红线验收门禁（每模块合并前必须全绿）

1. **红线1**：该模块 UI 完整、DB 结构标准、seed 有演示数据、无空壳/占位。
2. **红线2**：前端展示字段 100% 来自 `/admin/*` 真实返回；全仓库 grep 无该模块业务数据写死；H5 侧需联动的（M1 dist→distance_km、M6 评价过滤、M7 配置、M9 FAQ）同步修复且走契约。
3. **测试**：后端 `pytest`（新增端点覆盖）；admin SPA 渲染测试（页面挂载 + 列表/表单交互）；`ruff` + `eslint` 0 error。
4. **迁移纪律**：任何 `ALTER TABLE` 同步更新 `scripts/seed_*.py` 与 `DEVELOPMENT_PLAN.md` 字段契约。

---

## 7. 不在本阶段范围（等外部接入，仅做 UI + sandbox/seed）

- 真实微信 v3 / 支付宝退款（M4 的 `/refund` 仅 sandbox 翻 `payments.status`，真实网关接退款 API 时再接）
- 物流实时位置（M3 物流时间线仍 seed/手动）
- 微信登录 / 微信订阅消息
- 千问开放平台接入（此前决策：先观望）
- 图片上云 OSS/COS（当前落本地）

---

## 8. 执行 AI 必读文件

- `routers/admin.py`（现有 admin 端点范式）
- `routers/common.py`（`_require_admin` / `_require_merchant` / `METRICS` / Request 模型）
- `storage/db.py`（建表，新增表/列在此）
- `storage/catalog.py`（`get_shop`/`_row_to_shop`/`list_plans` 范式）
- `storage/commerce.py`（订单/支付逻辑，售后联动参考）
- `H5/src/pages/Admin.jsx` + `H5/src/api/shop.js`（现有 admin 前端范式，可迁移到 antd）
- `DEVELOPMENT_PLAN.md`（通用前端缺口，含 M1 的 `dist→distance_km` 修复约定）
- `MEMORY.md`（项目红线与约定）

---

## 9. 交付检查清单（Done 定义）

- [ ] P0：seed admin 账号可用，`admin/admin123456` 能登进独立 admin SPA
- [ ] P1：ShopDetail `menu` 聚合返回，admin 可管 plan/shop
- [ ] P2：用户管理（禁用/提权）+ 运营配置（配送/分类后端化）
- [ ] P3：订单全局管理 + 售后全流程（创单→审核→退款联动）
- [ ] P4：商家入驻申请→审核→成为 merchant 闭环
- [ ] P5：评价审核 + 内容管理（FAQ/公告后端化）
- [ ] P6：数据看板（复用 METRICS）
- [ ] 全部：pytest + 前端渲染测试 + ruff/eslint 通过；seed 可重灌
