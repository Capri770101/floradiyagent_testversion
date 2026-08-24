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

## 🤖 智能体模块（agent/）

系统的心脏是自研的**花卉导购智能体**，不依赖外部 Agent 框架，纯 Python 实现（ReAct + 技能编排 + 领域知识库 RAG）。

### 分层架构

```
agent/
├─ agent.py            # 智能体主类：ReAct 主循环 + 会话状态机驱动
├─ tools.py            # 工具注册表 TOOL_REGISTRY + 内建工具（装饰器自动注册）
├─ requirements.py     # 意图解析 / 需求维度抽取 / 搜索诚实化
├─ cli.py              # 本地调试 CLI（typer）：design / revise / knowledge / chat / tools
├─ engine/
│  ├─ llm.py           #   LLM 封装（OpenAI 兼容，function calling，live-only）
│  ├─ state.py         #   会话焦点枚举（仅 UI 高亮，不参与流程闸门）
│  └─ ui_protocol.py   #   前端渲染契约（ChatResponse / UIType / ToolCallRecord）
├─ skills/
│  └─ skill_order.py   #   下单技能：组装订单 → 写库 → 返回 pay_jump（自注册）
├─ knowledge/          #   领域知识库：flowers / styles / pairings / budget / packaging / scenes
│  └─ store.py         #   向量混合检索（TF-IDF + n-gram + 余弦；关键词命中保底 ∪ 语义召回）
├─ mcp_servers/
│  └─ vision_server.py #   本地 MCP server：智谱 GLM-4V 读图 → 文字描述（stdio）
└─ tests/              #   13 个专项测试文件（设计引擎 / 知识库 / 生图 / 记忆 / 意图解析…）
```

### ReAct 主循环

1. 载入**短期记忆**（历史消息）+ **长期记忆**（用户偏好），拼成 system prompt；
2. 进入「思考 → 行动 → 观察」循环：`call_llm` → 解析工具调用 → 执行工具 → 回填结果 → 再思考，直到模型给出最终回复或达到 `max_iterations`；
3. 根据本轮工具产出推导 UI 焦点并输出结构化 UI（`plan_card` / `shop_card` / `pay_jump` …）。

> 流程**不再由状态机硬锁**：自「skill 编排」重构后，用户可随时调用任一技能（设计 / 改设计 / 生图 / 看店 / 下单），工具产物依赖自然驱动流程。

### 工具注册表

- 每个工具用 `@register_tool` 装饰，自动写入 `TOOL_REGISTRY`（名称 / 中文描述 / 参数 JSON Schema / 实现）；
- agent 从注册表自动生成**工具说明书**注入 system prompt，并生成 OpenAI function-calling 定义；
- **新增工具只需写一个带装饰器的函数**，agent 与提示词零改动；
- 需要用户上下文的工具加 `inject_context=True`，执行时自动注入 `user_id` 等。

内建工具包括：`search_plans`（搜现有方案）、`get_plan_detail`、`retrieve_knowledge`（知识库检索）、`generate_diy_plan`（DIY 设计）、`revise_diy_plan`（按反馈改方案）、`generate_effect_image`（AI 生图）、`search_shops`（同城店铺推荐）、`create_order`（下单技能）、`save_memory`（记忆沉淀）。

### 知识库 RAG

- 六类领域 JSON 域（花材 / 风格 / 搭配 / 预算 / 包装 / 场景）+ **商家智库域**（数据来自 DB 的 `shop_profiles`，支持「韩式花店」「能做婚礼布置的店」等自然语言召回）；
- 检索升级为「向量空间模型（TF-IDF + 字符 n-gram 切词）+ 余弦相似度」的语义检索，采用**关键词命中保底 ∪ 向量语义召回**的混合策略——精确查询零退化，长自然语句提升召回；
- 对外接口 `query_knowledge(domain, query)` 签名稳定，上层零改动。

### UI 渲染契约

所有 `/chat` 响应统一包成 `ChatResponse`，`ui` 字段决定前端如何渲染 `data`：

| UIType | 渲染 | 示例 |
|---|---|---|
| `text` | 纯文本（已清洗 markdown 噪声） | 寒暄 / 说明 |
| `dialog_options` | 二选一/多选弹层 | 「现有方案 or DIY」 |
| `plan_card` | 花艺方案卡（花材/配比/包装/预算） | DIY 设计结果 |
| `shop_card` | 推荐店铺卡（评分/距离/起送） | 同城花店 |
| `order_card` / `pay_jump` | 订单卡 / 支付跳转 | 下单成功 |
| `image_task` | 生图结果（同步给 URL / 异步轮询） | 效果图 |

### 会话记忆

- **短期**：本会话历史消息，每次载入最近 `history_limit` 条；
- **长期**：用户偏好沉淀（`save_memory` 工具），跨会话复用；
- **DIY 资产库**：确认方案指纹去重入库 → 成交升级（ordered + order_count）→ 个人复用 + 平台学习。

### 本地调试

```bash
python agent/cli.py design "母亲节给妈妈买束花，预算两三百"
python agent/cli.py knowledge -d pairing -q "看望生病住院的朋友"
python agent/cli.py revise -p plan.json -f "便宜点"
python agent/cli.py chat --message "帮我设计一束送妈妈的生日花"
python agent/cli.py tools
```

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
|---|---|
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