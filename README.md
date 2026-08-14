# Flora Agent Service · 花卉 DIY 设计智能体后端

基于 Python 的智能体后端服务，通过 FastAPI 提供 HTTP 接口，供**微信小程序**与 **H5 网页前端**调用（H5 设计规范见 `DESIGN_SPEC_H5.md`）。
核心能力为**花卉 DIY 设计**：理解用户表达 → 基于知识库设计出一份结构化的专属花艺方案
（花材 / 配比 / 色彩 / 寓意 / 包装 / 预算）→ 可 AI 生图看效果 → 推荐店铺 → 组装订单引导支付。
店铺与下单是把「设计」落地的承接环节，而非核心卖点。同时支持日常闲聊与多轮上下文。

> 本期只实现**普通用户**完整流程，商家 / 管理员接口与权限钩子已预留（见 `api.py:is_allowed`）。

---

## 一、项目定位

- **角色**：普通用户（user）/ 商家（merchant）/ 管理员（admin）。本期仅放行 `user`。
- **接入点**：`/chat` 接受 `openid` 或 `user_id`。dev 模式下 `user_id` 可为任意字符串（测试用）；正式环境由小程序 `wx.login` 换 `openid` 后，经 `POST /auth/wx-login` 签发 JWT，后续请求携带 `Authorization: Bearer <token>`（`security.py` 负责校验）。
- **模式**：ReAct（思考-行动-观察）主循环 + skill 编排（**无状态机**：流程由 ReAct 循环与工具产物依赖驱动，不再有阶段邻接锁）。

---

## 二、目录结构

```
flora_diy_agent/                       # 服务根（仓库根目录）
├─ agent.py              # 智能体主类：ReAct 主循环 + skill 编排（respond_to_user 终结工具 + session_flags 生图守卫）
├─ tools.py              # 工具注册表 TOOL_REGISTRY + 内建工具
├─ skills/
│  ├─ __init__.py        # 自动扫描并注册 skills/
│  └─ skill_order.py     # 下单技能（独立模块，自描述 + 自注册）
├─ engine/
│  ├─ llm.py             # call_llm：OpenAI 兼容封装（流式 / 非流式）
│  ├─ state.py           # SessionStage 焦点（Focus）枚举，仅 UI 高亮，不参与流程闸门
│  └─ ui_protocol.py     # UI 消息协议的 pydantic 模型定义
├─ storage/
│  ├─ db.py              # SQLite 连接与事务封装（线程安全）
│  ├─ memory.py          # 短期（消息历史）+ 长期（偏好 KV）记忆
│  ├─ repository.py      # 数据仓库抽象接口 + MockRepository 实现
│  └─ tasks.py           # 异步任务（AI 生图）管理与轮询
├─ api.py                # FastAPI：/auth/wx-login、/chat、/tasks、/chat/reset、健康检查、/generated 图片托管
├─ config.py             # 全部配置集中管理（微信/JWT/数据源/生图/支付页路径）
├─ security.py           # 微信 code2session 换 openid + PyJWT 签发/校验 + 鉴权依赖
├─ Dockerfile            # python:3.12-slim + uvicorn 生产镜像
├─ docker-compose.yml    # env_file 注入 + ./data 卷持久化 + 自动重启
├─ .dockerignore
├─ requirements.txt
├─ .env.example          # 含「真实小程序接入配置」分组
├─ .gitignore
├─ tests/                # 鉴权 + 远程仓库 + 知识库 + 向量检索 + 场景模板 + DIY 设计/迭代 + 维度抽取 + 结构化需求 FlowerRequirement + 检索诚实化 + 会话级方案解析 + 历史回放 schema 归一化 + 生图 provider 共 73 用例
├─ cli.py                # 本地调试 CLI（typer）：design / knowledge / revise / chat / tools
└─ README.md             # 本文件：设计契约
```

---

## 三、会话焦点（Focus）标识

> 早期版本用状态机（`_ALLOWED` 邻接表 + `can_transition()` 硬锁每一步流转）。自「skill 编排」重构后已**彻底移除状态机**：流程由 **ReAct 循环 + 工具产物依赖**驱动——模型可随时调用任一技能（设计 / 生图 / 搜店 / 改方案），不再受阶段邻接约束。详见 `engine/state.py` 头部说明。

会话按 `user_id` 隔离，当前焦点持久化到 SQLite，重启不丢。`SessionStage` 仅表示「用户当前在干嘛」的 **UI 高亮 / 进度标识**，**不参与任何流程闸门或流转校验**，模型也无需按固定顺序推进。

### SessionStage 枚举（值即小写字符串，直接存库、可作前端进度）
```
ANALYZE / SELECT_MODE / VIEW_PLAN / DIY_DESIGN /
IMAGE_GEN / PLAN_CONFIRM / SHOP_RECOMMEND / ORDER_CONFIRM / DONE
```

### 焦点语义（仅 UI 展示，非流程约束）
- `ANALYZE`：理解需求，提取预算 / 对象 / 偏好等。
- `SELECT_MODE`：弹出「现有方案 / DIY」二选一（`ui=dialog_options`）。
- `VIEW_PLAN` 与 `DIY_DESIGN`：设计阶段可在现有方案与 DIY 间自由往返，无强制顺序。
- `IMAGE_GEN`：DIY 方案可触发异步生图任务，客户端轮询 `/tasks/{task_id}`。
- `PLAN_CONFIRM`：用户确认方案。
- `SHOP_RECOMMEND`：按距离 / 价格 / 评价综合排序推荐店铺（`search_shops`）。
- `ORDER_CONFIRM`：由 `skill_order` 组装订单并返回 `pay_jump`，支付由小程序承接。
- `DONE`：已生成支付跳转参数。

---

## 四、结构化 UI 协议（前端渲染契约）

所有 `/chat` 响应统一格式：

```json
{
  "user_id": "u_1001",
  "reply": "自然语言回复",
  "ui": "text | dialog_options | plan_card | shop_card | order_card | pay_jump",
  "data": { "...": "按 ui 类型定义的字段" },
  "tool_calls": [{"name": "...", "arguments": {}, "result": "...", "status": "ok|error"}],
  "session_id": "..."
}
```

### 各 `ui` 类型的 `data` schema

| ui | data 字段 |
|----|-----------|
| `text` | 无额外字段 |
| `dialog_options` | `options: [{ "label": str, "value": str }]`（如 现有方案 / DIY 二选一） |
| `plan_card` | `plan_id, name, price, desc, effect_image_url, merchant_name` |
| `shop_card` | `shop_id, name, distance_km, price_range, rating` |
| `order_card` | `order_id, items, total_price, plan_type("existing"\|"diy")` |
| `pay_jump` | `order_id, page_path, params`（小程序下单页跳转参数） |

---

## 五、接口契约

### POST /chat
请求：
```json
{
  "user_id": "u_1001",
  "message": "想给母亲买一束花，预算 200 元左右",
  "session_id": "可选，不传则服务端生成",
  "user_role": "user",
  "location": { "lat": 22.55, "lng": 114.24 }
}
```
响应：见第四节 UI 协议（含 `reply / ui / data / tool_calls / session_id`）。

### GET /tasks/{task_id}
生图任务轮询，返回 `{ "task_id", "status": "pending|running|done|failed", "result_url": "..." }`。

### POST /chat/reset
```json
{ "user_id": "u_1001" }
```
清空该用户会话历史与短期记忆，便于测试。

### POST /auth/wx-login
小程序 `wx.login()` 拿到一次性 `code`，后端调微信 `code2session` 换 `openid` 并签发 JWT。
请求：`{ "code": "081abc..." }`
响应：`{ "token": "eyJ...", "openid": "oABC123", "unionid": null, "expires_in": 604800, "token_type": "Bearer" }`
- 微信未配置（`WECHAT_APPID`/`WECHAT_SECRET` 缺省）→ **503**，提示先填真实小程序数据。
- 微信返回 `errcode` → 透传 **400**。

### 健康检查
`GET /health` → `{ "status": "ok", "llm_mode": "live|mock", "image_mode": "live|mock", "auth": "dev|required", "data_source": "mock|remote" }`。

### 统一错误返回
```json
{ "code": 400, "message": "人类可读错误说明" }
```

---

## 六、工具与技能

### 内建工具（TOOL_REGISTRY）
| 工具 | 说明 |
|------|------|
| `search_plans(keyword, requirement?)` | 搜索商家预设方案（含效果图 URL）；结合会话结构化需求做软过滤；搜不到返回空而非兜底全量 |
| `get_plan_detail(plan_id)` | 获取方案详情 |
| `retrieve_knowledge(domain, query)` | 检索花卉知识库（花材/风格/搭配/预算/包装），设计前「查资料」避免凭空编造 |
| `generate_diy_plan(requirements)` | **基于知识库**设计结构化 DIY 方案：抽维度→查知识→组装主花/配材/配比/色彩/包装/寓意/预算，并产出生图 prompt |
| `generate_effect_image(plan)` | **异步**生图；传 `latest_diy` 时基于最近设计的方案生成精确 prompt（花材/色彩/包装一致），立即返回 `task_id` |
| `search_shops(plan)` | 按距离 / 价格 / 评价综合排序推荐店铺 |
| `save_memory(key, value)` | 写入用户长期偏好 |
| `revise_diy_plan(plan, feedback)` | 基于已有方案 + 用户反馈（如「便宜点」「不要玫瑰」）重新设计，返回新版本（version+1）|

### 知识库（DIY 设计能力的核心支撑）
`knowledge/` 目录是花卉 DIY 设计的领域知识库，当前用**通用花艺常识**搭好骨架，后续可替换为你的真实业务数据（替换方式见 `knowledge/TEMPLATE.md`）：
- `flowers.json`：花材库（花语 / 色系 / 季节 / 价格档 / 搭配性 / 角色）
- `styles.json`：风格体系（韩式 / 北欧 / 复古 / 自然风 / ins / 日式，**每个含 2 个细分 substyle**，如韩式甜美 / 韩式高级）
- `scenes.json`：场景 / 节日模板（情人节 / 母亲节 / 生日 / 纪念日 / 探病 / 圣诞 / 婚礼… → 推荐风格、色板、主花倾向、寓意基调、预算锚点）
- `pairings.json`：搭配规则（色彩 / 形态 / 场合 / 对象 → 推荐花材）
- `budget.json`：预算 → 配置档映射
- `packaging.json`：包装器型

`knowledge/store.py` 提供**向量混合检索（RAG）**：TF-IDF 向量空间 + 字符 n-gram 切词（纯 Python，零依赖、可离线），对外接口 `query_knowledge(domain, query)` 签名/返回结构不变。
- **混合策略**：关键词命中保底 ∪ 向量语义召回——短单 token（如「母亲节」「康乃馨」）走精确关键词（零退化）；多 token / 长自然语句（如 LLM 工具 `retrieve_knowledge` 传来的中文 NL）触发向量语义召回并按相关度排序。
- **可回滚**：`config.py` 的 `rag_enabled=False` 整体回退旧关键词行为；`rag_top_k` / `rag_keyword_boost` / `rag_min_score` 可调。
- **升级路径**：当前为轻量向量空间模型（VSM），花材量增大后可把 `store.py` 内的 `_VectorSpace` 替换为句向量模型（sentence-transformers / OpenAI embeddings），接口不变即可平滑升级到稠密向量 RAG。

`generate_diy_plan` 的设计链路：
`用户表达 → 抽维度(对象/场合/场景节日/预算/色系/风格/情感) → 查知识库(风格/场景/搭配/花材/包装) → 组装结构化方案(主花+配材+配比/色彩/包装/寓意/预算估算) → 生成生图 prompt`。
设计函数具备三项增强：**① 场景感知**（识别节日/场景关键词，注入整组偏好）；**② 风格细分**（先定大类再选子风格，如「高级」→ 韩式高级）；**③ 用户反馈迭代**（`revise_diy_plan` 接收已有方案 + 自然语言修改意见，重新设计生成 v2，原方案可追溯）。
**这是本智能体与「导购」的本质区别**：核心价值在「根据用户表达设计出专属方案」这一下，店铺/下单只是把设计落地的承接。

### 技能机制
`skills/` 下每个技能为独立自包含模块（含描述、schema、`run` 方法），启动时自动扫描注册。
**下单功能做成 skill 而非普通工具**：`skill_order` 仅负责组装订单数据、写入 `orders` 表、返回 `pay_jump` 参数——
**不直接调用微信支付**，支付由小程序承接。

---

## 七、记忆管理
- **短期**：`sessions` / `messages` 表持久化全部历史；每次请求载入最近 `N=20` 条作为上下文。
- **长期**：`memories(user_id, key, value)` KV 表。读：对话开始检索该用户记忆拼入 system prompt；
  写：识别到明确偏好（预算、送花对象、偏好色系等）时由模型调用 `save_memory` 落库。

---

## 八、数据层（可切换：Mock 数据源 ↔ 真实后端）

> 此处的 Mock 指**数据层**占位实现（`MockRepository`），与第九节「已移除的 LLM Mock 引擎」无关——LLM 必须配置真实密钥。

- `storage/repository.py` 定义抽象接口（`search_plans` / `get_plan` / `list_shops` / `get_shop` / 用户信息等）；`search_plans` / `list_shops` 额外接收 `FlowerRequirement` 结构化需求做过滤与排序，Mock 软过滤、Remote 透传真实后端。
- `build_repository()` 工厂按 `DATA_SOURCE` 选择实现：
  - `DATA_SOURCE=mock`（默认）：`MockRepository`，内置示例花店、产品、效果图占位 URL，零配置可跑。
  - `DATA_SOURCE=remote`：`RemoteRepository`，通过 `httpx` 调你的真实后端（`REMOTE_API_BASE` + 各端点路径可配）。
- **契约是「换配置即接入」的核心**：只要真实后端返回的 `Plan`/`Shop` JSON 形状与 `MockRepository` 一致（端点与字段见 `config.py` 的 `remote_*_path` 与 `storage/repository.py`），上层导购逻辑、UI 协议**零改动**即可工作。
- `DATA_SOURCE=remote` 但缺 `REMOTE_API_BASE` 时，启动告警并自动回退 `MockRepository`，服务照常起。
- 生图 API 同理：统一 `image_client`，可在 `config.py` 切换 `mock` / `dashscope` / `api2img` / `zhipu` 四种 `provider`。

---

## 九、LLM 封装
`call_llm(messages, tools=None, stream=False)`：基于 `openai>=1.x` 客户端，
`base_url / api_key / model` 全部可配置（示例提供 DashScope 兼容端点写法）；
支持流式 / 非流式、可配置超时与重试；`logging` 记录输入摘要、工具调用序列、错误栈，**不打印密钥**。
必须配置 `LLM_API_KEY`（系统已移除 Mock 引擎，未配置会启动报错），走真实模型。

---

## 十、配置规范
`config.py` 集中全部配置；密钥优先读 `.env`（`python-dotenv`），不硬编码字面值。
复制 `.env.example` 为 `.env` 后填入即可。

---

## 十一、部署与鉴权约束
- 必须 **HTTPS** 且域名已**备案**；域名需加入小程序 `request` 合法域名白名单。
- 鉴权开关：`AUTH_REQUIRED=false`（dev）时 `/chat` 可用 `user_id` 直连；`=true`（上线）时强制 `Authorization: Bearer <token>`。生产务必设 `JWT_SECRET`（自生成随机长串），缺失时仅进程内随机密钥（仅联调）。
- 推荐用 Docker 部署闭环：`docker compose up -d --build`，`.env` 经 `env_file` 注入，数据与生图落盘挂载 `./data` 卷，容器重建不丢。
- 部署与鉴权细节见第十节配置规范与 `.env.example`（微信 / JWT / 远程数据源字段已内置）。

---

## 十二、运行与验收

**本地开发（零配置）：**
```bash
pip install -r requirements.txt
cp .env.example .env          # 可选：填入真实 LLM / 生图 key
uvicorn api:app --host 0.0.0.0 --port 8000
```

**本地调试 CLI（无需起服务，typer 实现）：**
```bash
python cli.py design "母亲节给妈妈买束花，预算两三百"   # 设计结构化方案（含插花步骤/养护/贺卡/预算明细）
python cli.py knowledge -d pairing -q "看望生病住院的朋友"  # 向量语义检索
python cli.py revise -p plan.json -f "便宜点"             # 反馈迭代
python cli.py tools                                        # 列出已注册工具
```

**监控端点：** `GET /health`（含 `rag_enabled` 等状态）、`GET /metrics`（进程内请求计数 + 配置快照，接 Prometheus 前的看板）。

**生产 / 接真实小程序（Docker）：**
```bash
cp .env.example .env          # 填好微信 / JWT_SECRET / DATA_SOURCE=remote + REMOTE_API_BASE
docker compose up -d --build
curl http://localhost:8000/health
```

**验收标准：**
1. 一键启动，访问 `/health` 返回 `ok`，并暴露 `auth` / `data_source` 模式。
2. `POST /chat` 发送「想给母亲买一束花，预算 200 元左右」完整走通：
   现有/DIY 选择弹窗 → 方案卡片 → 确认 → 店铺推荐 → 下单 → `pay_jump`。
3. 确认前可在现有方案与 DIY 之间往返切换；中途闲聊不破坏流程；重置接口生效。
4. `pytest` 全绿（当前 **73 passed**：鉴权 + 远程仓库 + 知识库 + 向量检索 + 场景模板 + DIY 设计/迭代 + 维度抽取 + **结构化需求状态 FlowerRequirement** + **检索诚实化（搜不到不返全量 / location 透传真实排序）** + **会话级方案解析（杜绝并发串号）** + **历史回放 schema 归一化** + 生图 provider）。
5. 接真实小程序只需改 `.env`（微信 / JWT / 远程数据源字段见 `.env.example`），业务代码零改动。

---

## 十三、接入真实小程序（成品化）

本项目已做成「**仅替换配置即可接入真实小程序**」的成品，业务代码零改动。三步接入：
1. `.env` 填 `WECHAT_APPID` / `WECHAT_SECRET`（微信登录）。
2. 填 `JWT_SECRET` 并设 `AUTH_REQUIRED=true`（开启鉴权）。
3. 设 `DATA_SOURCE=remote` + `REMOTE_API_BASE`（真实后端按 `config.py` 中 `remote_*_path` 约定的端点返回 JSON）。

结构化 UI 响应协议见第四节；远程后端接口契约见 `config.py` 的 `remote_*_path` 与 `storage/repository.py`；部署速查见第十一 / 十二节。
