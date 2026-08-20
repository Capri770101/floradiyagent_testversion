# 三端独立域名架构 · 任务书（Agent 执行规格）

> 状态：⚠️ 已拍板（2026-08-19），规划文档。本文档供 agent 阅读理解后按阶段执行，**执行前仍须先 grep 确认目标文件/端点/表是否已存在**（任务书纪律），严禁基于"应该没做"假设起造。
>
> 决策：C 端、商家端、管理端做成**三个独立域名**。后端共享同一套 FastAPI（CORS 多源放行三个前端 origin）；前端采用**同仓多 entry、三独立产物、三独立域名部署**形态（不拆三个 git 仓库，工程复用、部署隔离）。

---

## 0. 目标架构

```
                        ┌─────────────────────────────┐
   浏览器三标签页/三设备  │       FastAPI 后端 (共享)    │
   ┌──────────┐         │  /chat /catalog /commerce   │
   │ C端域名   │─CORS────▶ /auth/* /merchant/* /admin/*│
   │ c.xxx.com│         │  /notify /recommend         │
   └──────────┘         └─────────────────────────────┘
   ┌──────────┐                ▲
   │商家端域名 │─CORS───────────┘
   │merchant  │
   └──────────┘
   ┌──────────┐
   │管理端域名 │─CORS────（同上）
   │admin     │
   └──────────┘

前端：H5 仓库内三个 entry（index.html=C端 / admin.html=管理端 / merchant.html=商家端）
     各自独立构建产物，部署到三个独立域名（独立 nginx/容器/证书）。
认证：JWT Bearer Token（放 Authorization 头 + 前端 localStorage），非 cookie。
     三域名 localStorage 按 origin 隔离，可同时登录互不影响。
```

**关键约束（红线延续）**
- 每个前端页面的展示字段必须有真实后端来源（禁写死业务数据）。
- 所有功能按可上线标准完成；暂无真实数据先 seed 假数据，上线可清空。
- 认证用 Bearer Token 模式，**不要用 cookie 跨域**（避免 SameSite/Domain 坑）。

---

## 1. 现状核查事实表（本轮回查，2026-08-19）

| 项 | 现状 | 位置 | STATUS |
|----|------|------|--------|
| CORS 多源 | `cors_origins: list[str]`，默认空；`cors_allow_credentials=False`（Bearer 模式正确） | `config.py:40-41` / `api.py:79-86` | ✅ 已就绪，只需配三个域名 |
| C 端前端 | `index.html` + `H5/src/`（React18+Tailwind），vite entry `main` | `H5/vite.config.js:18` | ✅ 已存在 |
| 管理端前端 | `admin.html` + `H5/src/admin/`（独立 SPA：main/App/api.js + 10 个 pages 含 MerchantApply 入驻审核） | `H5/src/admin/**`；`vite.config.js:20` entry `admin` | ✅ 已存在（独立 entry） |
| 商家端前端 | **无独立 entry**；仅 `H5/src/pages/Merchant.jsx`（C 端内页面，约 2239 行巨型组件） | `H5/src/pages/Merchant.jsx` | ❌ 待建（需抽独立 entry + 拆分） |
| 商家后端接口 | 40+ 端点：stats/shops/orders(+ship/logistics)/reviews(+reply)/plans(CRUD/toggle)/categories(CRUD)/shop/update/chats(IM)/**apply(入驻)** | `routers/merchant.py` | ✅ 基本齐全 |
| C 端认证端点 | `/auth/wx-login` `/auth/phone-login` `/auth/login` `/auth/register` `/auth/me` `/auth/admin-login` | `routers/auth.py` | ✅ 已存在 |
| 商家认证端点 | **缺** `/auth/merchant-register` 与 `/auth/merchant-login`；merchant 现借 C 端 `/auth/login`（只 reject admin，不拦 merchant） | `routers/auth.py` | ❌ 待建 |
| 商家入驻流程 | `/merchant/apply`（申请）+ admin `MerchantApply` 页审核 + `set_user_role(uid,'merchant')` | `routers/merchant.py:453` / `security.set_user_role` | ✅ 已存在（但注册入口未独立） |
| 手机号全局唯一 | **无**。注册商家时未校验手机号是否已被其他角色（user/merchant/admin）占用 | `security.register_user` / `phone_login_user` | ❌ 待建（点1 硬约束） |
| 内容审核（点3） | 后端有下架/隐藏能力（reviews.status=hidden、shop_plans.status=on/off、users.status=banned）；**缺**机审接入 + 受控装修组件 + C 端举报入口 | 分散 | ⚠️ 部分（需补机审+受控模板+举报） |
| 部署配置 | 单 `Dockerfile` + `docker-compose.yml`（未区分三前端）；无 nginx 模板 | 根目录 | ⚠️ 待扩展为三套 |
| 销量字段（待改） | `plans.sold`(db.py:72)/`shops.sales`(db.py:126) 现种子演示值，待改正式版（订单统计） | `storage/db.py` | ❌ 待改（详见 DATABASE_ARCHITECTURE §3） |
| 智能体授权调用（待改） | `skills/skill_order.py:79-93` 直接 `INSERT INTO orders` 裸写业务库，违反授权调用约束 | `skills/skill_order.py` | ❌ 待改走 storage service（详见 DATABASE_ARCHITECTURE §4） |

> agent 执行任何子任务前，先用 Grep/Read 复核上表对应项，避免重复造已实现功能。

---

## 2. 任务分解（按阶段，带文件/动作/验收）

### 阶段 1：后端 CORS 多源 + 环境配置分离
- **目标**：允许三个前端域名调用同一后端。
- **动作**：
  1. `.env` 设 `CORS_ORIGINS=[\"https://c.xxx.com\",\"https://merchant.xxx.com\",\"https://admin.xxx.com\"]`（开发期可临时加 `http://localhost:5173/5174/5175`）。
  2. 确认 `api.py:85` `allow_origins=settings.cors_origins` 已生效（已就绪，无需改代码）。
  3. 后端 `AUTH_REQUIRED` 上线置 `true` + 配 `JWT_SECRET`（加启动断言：缺密钥且 auth_required=true 则 fail-fast，见 IMPROVEMENT_PROPOSAL P1）。
- **验收**：三个 origin 各发 OPTIONS 预检 + 带 Bearer 的 GET 请求均 200；`*` 通配符在生产被禁止。
- **STATUS**：✅ 完成（CORS 三源 + APP_ENV 分离 + prod fail-fast 断言）。

### 阶段 2：商家独立认证（点1）
- **目标**：商家走独立、严格的注册/登录流程；手机号全局唯一。
- **动作**：
  1. 新增 `routers/auth.py`：`POST /auth/merchant-register`（手机号唯一校验 + 营业执照/实名等认证字段 + 自动建 user 并 `set_user_role(uid,'merchant')` 或置待审核）、`POST /auth/merchant-login`（校验凭据 + 要求 `role=merchant`，否则 403）。
  2. 在 `security.register_user` / `phone_login_user` 加"手机号是否被任何 users 行占用"校验——若已绑定 merchant/admin，拒绝 C 端注册/登录并引导去对应后台。
  3. `users.phone` 加唯一索引兜底（见 `db.py` 迁移区）。
  4. 现有 `/merchant/apply` 入驻申请流程保留，与新注册端点协同（注册后初始 role=merchant 或 pending，由审核策略定）。
- **验收**：用 merchant 手机号走 `/auth/merchant-login` 成功且拿 JWT；用该手机号走 C 端 `/auth/register` 被拒；admin 账号走 `/auth/merchant-login` 被拒（403）。
- **STATUS**：✅ 完成（merchant-register/login + 手机号全局唯一 + users.phone 部分唯一索引 + 角色隔离测试）。

### 阶段 3：商家端前端独立（核心改造）
- **目标**：从 C 端挖出商家能力，建成独立 entry `merchant.html` + `H5/src/merchant/`，不复用 C 端 bundle。
- **动作**：
  1. 新增 `H5/merchant.html` + `H5/src/merchant/main.jsx`（参照 `H5/src/admin/main.jsx` 结构，技术栈对齐 admin：Ant Design）。
  2. `H5/vite.config.js` 的 `build.rollupOptions.input` 增加 `merchant: 'merchant.html'`（形成三 entry）。
  3. 把 `H5/src/pages/Merchant.jsx`（2239 行）按模块**重构拆分**到 `H5/src/merchant/pages/`：`Dashboard`(营业概览) / `Orders` / `Logistics`(配送) / `Customers`(IM 沟通) / `Aftersale`(售后) / `Products`(商品与店铺装修) / `Profile`(商家资料与认证)。
  4. 新建 `H5/src/merchant/api.js`，对接 `routers/merchant.py` 现有端点（**不要新造后端接口**，后端已齐）。
  5. 登录走 `/auth/merchant-login`；登录后按 role 进商家面板（与 admin 同理）。
  6. 装修模块用**受控组件**（拖拽模块/传图/填文案），**禁止 raw HTML/JS 输入**（呼应红线，防 XSS + 非法内容）。
- **验收**：`npm run build` 产出三个独立 html；商家端独立域名可登录、各模块数据来自真实接口、C 端 bundle 不再含商家代码。
- **STATUS**：✅ 完成（merchant entry + 6 页独立实现对接真实接口；C 端已剥离商家工作台与导航，bundle 缩减约 56KB）。

### 阶段 4：C 端 / 管理端独立域名部署确认
- **目标**：两者已有独立 entry，确认独立域名部署配置。
- **动作**：
  1. C 端：`index.html` 已就绪，部署到 `c.xxx.com`，`VITE_API_BASE` 指向后端。
  2. 管理端：`admin.html` + `H5/src/admin/` 已就绪，部署到 `admin.xxx.com`。
  3. 两者 `vite build` 各自产物独立（已支持），部署层分别配域名 + 反代 `/api` → 后端。
- **验收**：两域名独立可访问、调同一后端 CORS 放行。
- **STATUS**：✅ 代码就绪，仅部署配置（阶段 6 一并处理）。

### 阶段 5：内容审核体系（点3）
- **目标**：商家自治 + 机审兜底 + 举报巡查 + 分级预审，规避"全量人工审"冗余。
- **动作**：
  1. 受控装修组件（阶段 3 已含）：禁止 raw HTML/JS。
  2. 机审接入：商品/店铺图上架时过内容安全（可接现有智谱/千问或第三方内容安全 API），违规拦截。预留 `settings` 开关（dev 放行、prod 开启）。
  3. C 端举报入口（`routers/notify` 或新增 `routers/report.py`）+ 管理后台举报处理页（admin `Content` 页扩）。
  4. 新商家首店/首屏轻量预审，成熟后转巡查（复用 `/merchant/apply` 审核能力）。
- **验收**：违规图被机审拦；C 端可举报；admin 可下架/封禁。
- **STATUS**：✅ 完成（受控组件无 raw HTML/JS + 机审开关/挂载点 + C 端商品/店铺举报 + admin 举报处理页（下架/封禁联动））。

### 阶段 6：部署预留（开发期规划，上线前真配）
- **目标**：三套独立部署（域名/DNS/HTTPS/容器/反代）。
- **动作**：
  1. `docker-compose.yml` 拆为三前端 service + 一后端 service；各自 Dockerfile 或 multi-stage。
  2. nginx 模板：三域名各自 server 块，静态托管前端产物 + 反代 `/api` `/uploads` 到后端容器。
  3. DNS + HTTPS 证书规划（开发期用 localhost 多端口模拟，上线再买域名）。
  4. `.env` 按环境分离（dev/staging/prod 的 CORS_ORIGINS、AUTH_REQUIRED、机审开关）。
- **验收**：三域名生产配置就绪可部署（开发期用 localhost:5173/5174/5175 验证等价）。
- **STATUS**：✅ 完成（docker-compose 一后端 + 一前端容器（nginx 三端口=三入口）+ nginx 模板 + 文档更新）。

---

## 3. 测试清单（联调用）

**三套独立测试账号**（因 role 限制，一个账号不能三端通吃；点1 手机号唯一，需不同手机号）：
- 顾客：`capri_demo / 123456`（role=user）
- 商家：`merchant_demo / 123456`（role=merchant，关联一 shop）
- 管理员：`admin / admin123456`（role=admin）

**seed 数据串联要求**（联调前确认齐）：
- merchant 账号 ↔ `shops` 行绑定（商家端能看到自己店铺）
- 顾客账号下有订单（user_id / shop_id 对应），商家端可见、admin 端可审
- 聊天/评价/售后示例数据存在，验证 IM/售后模块

**联调路径验证**：顾客 C 端下单 → 商家端（独立域名登录）看到订单 → 发货/处理 → 管理员端审核/下架。三端独立登录互不干扰（不同 origin localStorage）。

---

## 4. 执行顺序建议（agent 排期）

```
阶段1 CORS/环境配置   (0.5d, 配置为主)
阶段2 商家认证端点    (1d, 含手机号唯一)
阶段3 商家端前端独立  (大头, 按模块迭代: 先 Orders/Products, 再 IM/看板)
阶段5 内容审核        (穿插: 受控模板→机审→举报)
阶段4 C端/Admin部署确认 (0.5d, 配置)
阶段6 部署预留        (收尾, 上线前真配)
```

> 阶段 3 是工作量主体，建议拆成子任务逐个页面迁移并对接真实接口（禁写死）。

---

## 5. 红线与坑提醒
- ❌ 前端禁止 `dangerouslySetInnerHTML` 写死 / 写死业务数据（每个字段要有真实接口来源）。
- ❌ 商家端禁止用 cookie 跨域认证，保持 Bearer Token 模式。
- ❌ 不重复造 `routers/merchant.py` 已存在的接口（先 Grep 确认）。
- ⚠️ `allowedHosts: true`（vite.config）上线前改回具体域名白名单。
- ⚠️ `AUTH_REQUIRED=false` 仅开发期；上线必须置 true + JWT_SECRET + 启动断言。

---

## 6. 数据库分域架构基线（另见专项文档）

> 数据库"单库 + 逻辑分域 + RBAC 隔离，物理不分库"的完整基线已落到 **`DATABASE_ARCHITECTURE.md`**，本任务书只在此引用关键结论，避免两份文档重复维护。

**核心结论：**
- 单库 `agent_service.db` 为共享真相源，三前端域名共享；隔离靠 RBAC（应用层），不按角色物理分库。
- 四域：用户域（C端）/ 商家域（店铺单位）/ 管理域（全量+编辑，轻档排版）/ 智能体私有域（独立，业务库授权调用）。
- `users` 三角色同表，商家独立注册靠 `role` 升级 + 手机号全局唯一约束（同表才能实现跨角色校验）。
- 销量字段（`plans.sold`/`shops.sales`）改正式版：由 `mark_order_paid`(storage/commerce.py:1315) 实时 + 幂等更新，定时任务兜底。
- 智能体授权调用：禁用 LLM 裸写 SQL；`skill_order.py:79-93` 改调 `storage.commerce.create_order`(896)。

**执行数据库相关改造前，必须 Read `DATABASE_ARCHITECTURE.md` 全文 + Grep 确认现状，严禁凭"应该没做"假设起造。**
