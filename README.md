# 跳舞兰 · 花卉 DIY 设计智能体服务

> **Atelier de Fleurs** · 轻奢花艺 · 法式极简视觉

一个面向**花卉 DIY 定制**的完整电商 + 智能体系统：用户用自然语言描述需求，AI 基于领域知识库设计结构化花艺方案（花材 / 配比 / 色彩 / 寓意 / 包装 / 预算），实时 AI 生图预览效果，自动推荐同城花店，一键下单并走支付闭环。

平台由 **顾客端 / 商家端 / 管理端** 三套独立前端 + 单一 FastAPI 后端组成，覆盖从设计、下单、履约（发货/物流/售后）到内容治理（机审 / 举报）的完整业务链。

---

## ✨ 核心能力

| 模块 | 说明 |
|---|---|
| **AI 花艺设计** | ReAct 主循环 + skill 编排；意图解析 → 维度抽取 → 知识库检索（TF-IDF + n-gram 向量 RAG）→ 结构化方案生成 |
| **AI 生图** | 多 provider 可切换（`mock` / 通义万相 dashscope / 智谱 CogView / api2img 中转），SSRF 防护 + 落盘托管 |
| **会话式购物** | 对话内选品、改方案、比价、下单；长期记忆 + 会话回放（UI 协议） |
| **完整电商** | 商品/分类/店铺、购物车、优惠券+积分、订单状态机（创建→支付→发货→签收→评价）、支付超时懒过期、物流时间线 |
| **商家自治** | 独立商家工作台：经营看板、订单履约、客户 IM、售后、商品/店铺管理、评价回复 |
| **管理后台** | 用户/商品/店铺/订单全量管理、售后审核、商家入驻审核、运营公告、FAQ/分类内容管理 |
| **内容治理** | 受控装修组件（无 raw HTML/JS）+ 机审开关挂载点 + C 端举报入口 + 后台处理（下架/封禁联动） |
| **通知中心** | 订单/物流/评价回复/售后/公告站内信，未读红点 |
| **安全设计** | 三端令牌隔离、手机号全局唯一、订单归属校验、服务端取价防篡改、限流防刷、启动 fail-fast 断言 |

---

## 🏗 三端独立架构

三套前端**同仓多 entry**，共享同一后端与数据库，令牌互不干扰：

| 端 | 构建入口 | 路由前缀 | 令牌键 | 登录接口 |
|---|---|---|---|---|
| **C 端（顾客）** | `index.html` + `H5/src/` | `/` | `floradiy_token` | `/auth/login` `/auth/phone-login` |
| **商家端** | `merchant.html` + `H5/src/merchant/` | `/merchant` | `floradiy_merchant_token` | `/auth/merchant-login` `/auth/merchant-register` |
| **管理端** | `admin.html` + `H5/src/admin/` | `/admin` | `floradiy_admin_token` | `/auth/admin-login` |

- **角色隔离**：C 端登录拒绝 merchant/admin 角色；商家/管理登录要求对应角色（403 兜底）。
- **手机号全局唯一**：同一手机号不可在任意角色间重复注册（`users.phone` 部分唯一索引兜底）。
- 本地开发期三端同源（`localhost:5173` 路径区分）；Docker 部署后映射三端口（5173/5174/5175）等价三域名。

---

## 🧱 技术栈

- **后端**：Python + FastAPI + SQLite（单文件共享主库）· pydantic-settings 配置 · 线程池化数据层
- **前端**：React 18 + Vite 5 + Tailwind CSS · react-router · 独立入口三端打包
- **智能体**：自研 ReAct 主循环 + 工具注册表 + 领域知识库（JSON + 轻量向量检索，纯 Python 零依赖）
- **测试**：pytest（后端 263 用例）+ Vitest（前端 22 用例）+ ruff / ESLint

---

## 📁 目录结构

```
flora_diy_agent/
├─ agent/                  # 智能体（ReAct 主循环 / 工具 / 知识库 RAG / 专属测试）
├─ backend/                # FastAPI 后端（路由 / 存储层 / 安全 / 内容机审 / 种子脚本）
│  ├─ api.py               #   装配层（CORS / 异常 / lifespan / 路由挂载）
│  ├─ config.py            #   全部配置（读 misc/.env，pydantic-settings）
│  ├─ security.py          #   JWT / 账号密码 / 手机号验证码 / 商家注册
│  ├─ review.py            #   内容机审（开关预留 + 真实 API 挂载点）
│  ├─ routers/             #   auth / catalog / commerce / chat / merchant / admin / notify / report / recommend
│  └─ storage/             #   db / 各业务数据层（与智能体共享 memory / diy / tasks）
├─ H5/                     # React + Vite 前端（三端三入口）
│  ├─ src/                 #   C 端（顾客端）
│  ├─ src/merchant/        #   商家端
│  └─ src/admin/           #   管理端
├─ tests/                  # 后端业务测试（25 文件）
├─ data/                   # 运行时落盘（SQLite / 生图 / 上传，gitignore）
└─ misc/                   # 工程文件（.env.example / Dockerfile / docker-compose / nginx / 任务书 / 文档）
```

---

## 🚀 快速开始

### 后端

```bash
# 1. 配置（复制示例并填入密钥）
cp misc/.env.example misc/.env
#   必填：LLM_API_KEY（AI 设计对话，live 模式）；可选 IMAGE_PROVIDER / 支付渠道等

# 2. 启动（项目根目录）
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8080

# 3. 探活
curl http://localhost:8080/health
```

> dev 模式零配置即可启动（生图走 mock、支付走 sandbox、短信走固定验证码）。首次启动自动建表 + 灌入种子商品/店铺数据。

### 前端（三端）

```bash
cd H5
npm install
npm run dev            # 开发：http://localhost:5173（Vite 代理 /api → 后端 8080）
npm run build          # 生产：产出 index.html / admin.html / merchant.html 三入口
```

本地开发期三端访问（同一 dev server，路径区分）：

| 端 | 地址 |
|---|---|
| C 端 | http://localhost:5173/ |
| 管理端 | http://localhost:5173/admin.html |
| 商家端 | http://localhost:5173/merchant.html |

### 演示账号

| 端 | 账号 | 说明 |
|---|---|---|
| C 端 | `customer_demo / 123456` | 顾客，可完整下单 |
| 商家端 | `capri_demo / 123456` | 商家，绑定店铺 S001 / S4c8080 |
| 管理端 | `admin / admin123456` | 平台管理员 |

---

## ✅ 测试

```bash
# 后端全量（业务 25 文件 + 智能体 13 文件，263 用例）
python -m pytest -q -c misc/pyproject.toml

# 后端 lint
python -m ruff check --config misc/pyproject.toml .

# 前端（H5/ 目录）
npx eslint src
npx vitest run
npm run build
```

---

## 🐳 Docker 部署（三端三端口）

```bash
docker compose -f misc/docker-compose.yml up -d --build
```

| 端口 | 用途 |
|---|---|
| 5173 | C 端（顾客端） |
| 5174 | 管理端 |
| 5175 | 商家端 |
| 8000 | 后端 API |

- 前端镜像为 multi-stage（node 构建 → nginx 托管），`misc/nginx/frontends.conf` 内置三端口=三入口 + `/api`、`/uploads` 反代。
- 上线：三个 server 块改 `listen 80` + `server_name` 真实域名，配合 HTTPS 证书；`AUTH_REQUIRED=true` + 自设 `JWT_SECRET`（prod 启动强制断言）。

---

## 🛡 关键设计

- **不写死业务数据**：每个前端字段对应真实接口；装修组件为受控组件，禁止 raw HTML/JS（防 XSS）。
- **服务端权威**：订单价格由服务端按目录取值（防客户端篡改）；订单归属校验杜绝越权。
- **限流防刷**：内存滑动窗口限流（对话 / 生图 / 验证码 / 登录），多 worker 部署可换 Redis（接口不变）。
- **密钥安全**：密钥仅存 `misc/.env`（gitignore），日志不打印敏感字段。
- **内容治理**：上传图片过机审（prod 开启）；C 端举报 → 后台处理（banned 联动下架商品/店铺、隐藏评价）。

---

## 📚 文档索引

- `misc/README.md` — 运维级说明（配置、验收、部署细节）
- `misc/STRUCTURE.md` — 目录结构详解
- `misc/DATABASE_ARCHITECTURE.md` — 数据库四域划分与表设计
- `misc/MULTI_DOMAIN_TASK_SPEC.md` — 三端独立架构任务书（阶段分解）
- `misc/IMPROVEMENT_PROPOSAL.md` — 安全与健壮性改进清单
- `misc/NEW_FEATURES_TASK_SPEC.md` — 新增功能任务书（通知/积分/优惠券等）
- `misc/maison-flora-design-prompt.md` — 「跳舞兰」品牌视觉规范

---

*跳舞兰 · Atelier de Fleurs · 轻奢花艺 · 2026*