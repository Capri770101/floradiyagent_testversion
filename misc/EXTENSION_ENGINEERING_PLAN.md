# 跳舞兰 · 拓展工程计划书（生产化 · 第二 / 三 / 四部分）

> 范围：架构扩展性（二）、安全加固（三）、AI 智能体生产化（四）。
> 不覆盖（需外部资质/认证，本计划只留"可插拔骨架"）：真实支付渠道、真实短信通道、真实机审 API 接入。
> 目标：在不破坏现有 demo 行为的前提下，做**增量、可回滚、可测试**的生产化改造。

## 0. 总体原则
- **配置驱动**：所有新能力用 `settings`（pydantic-settings）开关控制，dev 默认保持现状，prod 开启。
- **接口不变**：对上游（前端 / agent / 路由）暴露的契约（`query_knowledge`、`ChatResponse`、UIType、存储返回 URL 等）签名保持稳定。
- **增量落地**：先搭抽象层（Phase 0），再逐能力切换，每 Phase 有独立验证，可随时回滚。
- **双后端共存**：SQLite（dev/test）与 PostgreSQL（prod）并存；Local 存储与 OSS/S3 并存，靠配置切换。

## 1. 阶段划分与交付物

| Phase | 内容 | 关键产出 | 是否阻断现有 demo |
|---|---|---|---|
| P0 | 基础设施抽象 | `redis.py` 连接池、`object_store.py` 抽象、配置项 | 否（默认走旧路径） |
| P1 | PostgreSQL 迁移 | 数据层抽象 + PG 实现 + 种子/迁移脚本 | 否（dev 仍 SQLite） |
| P2 | 对象存储 | `generated_dir`/`upload_dir` 走 OSS/S3 + CDN | 否（local 模式保留） |
| P3 | 异步任务队列 | 生图/通知/机审/索引入队，worker 进程 | 否（同步路径保留为 fallback） |
| P4 | 限流 Redis 化 | 滑动窗口改 Redis 后端 | 否（接口不变） |
| P5 | 安全加固 | 密钥/KMS 适配、SSRF egress、鉴权矩阵、依赖审计、Fail-Closed 机审 | 否 |
| P6 | AI 智能体生产化 | LLM 熔断/多 provider/成本预算、生图 fallback、RAG pgvector、质量护栏 | 否 |
| P7 | 可观测性（轻量） | 结构化日志、/metrics 指标、告警阈值 | 否 |

---

## 2. P0 — 基础设施抽象（所有后续能力的地基）

### 2.1 Redis 连接池
- 新增 `backend/storage/redis.py`：
  - `get_redis()` 返回连接池单例（基于 `redis.asyncio`）。
  - 配置：`REDIS_URL`（默认 `redis://127.0.0.1:6379/0`），`app_env=prod` 时缺失则 fail-fast。
- 仅在被显式使用时建立连接，dev/test 不依赖 Redis 也能跑。

### 2.2 对象存储抽象
- 新增 `backend/storage/object_store.py`：
  - 抽象基类 `ObjectStore`：`put(key, data) -> url`、`get(key) -> bytes`、`delete(key)`。
  - `LocalStore`：沿用当前 `data/generated`、`data/uploads` + `/uploads` 静态托管（dev 默认）。
  - `S3Store` / `OSSStore`：实现 `put` 直传对象存储，返回 `CDN_BASE + key`。
- 配置：`STORAGE_BACKEND`(local|s3|oss)、`STORAGE_BUCKET`、`STORAGE_ENDPOINT`、`STORAGE_CDN_BASE`、`STORAGE_PUBLIC_READ`。
- 现有 `config.generated_dir` / `upload_dir` 行为由 `LocalStore` 内部保留，调用方改为经 `ObjectStore` 接口。

---

## 3. P1 — PostgreSQL 迁移

> ⚠️ 修订说明：原方案对代码现状有两处关键误读（见 3.1 / 3.2），且漏掉了方言细节与 agent 记忆表，**真实工作量比原估至少高一个量级**，本版已纠正。

### 3.1 现状（已核对代码）
- **唯一数据库入口是 `backend/storage/db.py:get_conn()`**，返回原始 `sqlite3.Connection`。订单 / 方案 / 店铺 / 购物车 / 支付 / 评价，以及 **agent 记忆**（`sessions` / `messages` / `session_flags` / `memories`）的真实读写，全部直接 `conn.execute("... ? ...")`，散落在 `commerce.py`、`diy.py`、`chat.py`、`merchant.py`、`admin.py`、`memory.py`、`catalog.py`、`notify.py`、`config.py`、`payment.py`、`recommend.py` 等 **十余个模块**。
- **`backend/storage/repository.py` 不是订单库抽象**，而是**商品目录数据源抽象**（`MockRepository` / `RemoteRepository`，仅服务花店目录检索），与订单 / 方案持久化无关——**不能**当作"PG 迁移的第二个实现"起点。
- **执行模型是同步 `sqlite3` + `asyncio.to_thread`**：router 层用 `await asyncio.to_thread(...)` 包裹同步存储函数（见 `api.py` 注释与 `merchant.py` / `chat.py` 等），所有 DB 调用都是 `conn.execute(...)`（同步、无 `await`）。
- 建表 SQL 集中在 `db.py:_SCHEMA`（`CREATE TABLE IF NOT EXISTS`），含电商表 + 智能体记忆表。agent 记忆是**落库持久化（重启不丢）**，不是纯内存。
- 方言耦合点（PG 下会直接报错，见 3.3 清单）：`?` 占位符（约 365 处）、`date('now')`、`INSERT OR IGNORE/REPLACE`、`JSON` 以 `TEXT` + Python 侧 `json.dumps/loads` 存储（约 40 处）。

### 3.2 方案（纠正后：先抽抽象，再写 PG 实现）
- **先抽数据访问抽象，再写 PG 实现**（绝非"实现第二个 backend"那么简单）：在 `db.py:get_conn()` 之上抽一层 DB 访问层（Repository / DAO），把散落十余模块的 `conn.execute("...?...")` 收口到该层；再为 PostgreSQL 提供第二个实现（asyncpg / SQLAlchemy async Core）。**这是真正的成本大头，原估工作量低估至少一个量级。**
- **同步 → 异步执行模型切换**：PG 用 asyncpg 后，所有 `conn.execute(...)` 要改成 `await conn.execute(...)`；调用链（`commerce` / `diy` / `chat` / `notify` / `merchant` / `admin` 及 router 的 `asyncio.to_thread` 包裹）要相应调整——要么保留 `to_thread` 包裹异步驱动，要么改成原生 async 存储层并去掉 `to_thread`。需全量回归。
- 引入 **SQLAlchemy 1.4+ async（Core）** 作方言无关层较稳妥（亦可复用现有建表 SQL 做 `MetaData.create_all`），避免手写两套方言 SQL。
- 由 `DATABASE_URL` 决定后端；未配置时回退 `db_path`（SQLite）。
- 种子脚本 `misc/seed_*.py` 同时支持两套后端；新增 `alembic`（或手写 `schema.sql`）做受控迁移，避免"首次启动自动建表"在生产失控。

### 3.3 方言迁移清单（必须逐项处理）
- **占位符**：`?` → `%s`（或命名 `:name`）。约 365 处 `conn.execute` 调用需替换。
- **日期函数**：`date('now')`（`admin.py:589`、`commerce.py:519` 的"今日统计"）→ PG 用 `CURRENT_DATE`。
- **UPSERT**：`INSERT OR IGNORE` / `INSERT OR REPLACE`（`admin.py` / `catalog.py` / `commerce.py` / `memory.py`）→ PG `INSERT ... ON CONFLICT (...) DO NOTHING / DO UPDATE`，需补唯一约束 / `ON CONFLICT` 目标列（如 `diy_plans(user_id, fingerprint)`、`session_flags(user_id, session_id, key)`）。
- **JSON 列**：当前 `TEXT` + Python 侧 `json.dumps/loads`（commerce / diy / memory / catalog / admin / config / payment / recommend 等约 40 处）→ PG 建议改 `JSONB` 并改用驱动原生 JSON 参数；最低限度保证 `TEXT` 兼容，但会丢失索引 / 查询能力。
- **类型与函数**：自增 / 主键、全文检索、`LIKE` / 排序、布尔等按 PG 调整。

### 3.4 迁移范围（含 agent 记忆，不可丢）
- 电商表：`users`、`addresses`、`categories`、`plans`、`shops`、`shop_plans`、`shop_profiles`、`shop_styles`、`shop_scenes`、`cart_items`、`orders`、`order_items`、`payments`、`reviews`、`image_tasks` 等。
- **智能体记忆表（必须覆盖，否则 agent 记忆全丢）**：`sessions`、`messages`、`session_flags`、`memories`（均在 `db.py:_SCHEMA`）。
- 幂等建表 / 旧库迁移脚本需同时覆盖以上全部表。

### 3.5 验证
- CI 矩阵：pytest 同时跑 SQLite 与 PG（PG 用 testcontainers / CI 服务）。
- 现有 263 用例不应因切换后端而失败（**含 agent 记忆读写用例**）。
- 灰度 & 回滚：SQLite 保留为降级实现；PG 为主库，回滚以 PG 为准，确保已落库的订单与 agent 记忆不丢。

---

## 4. P2 — 对象存储落地

- 生图产物（`agent` 生图落盘、`backend` 上传图片）统一经 `ObjectStore.put`。
- 返回给前端的 URL 改为 `STORAGE_CDN_BASE + key`（local 模式仍是 `/uploads/...` 静态路径，契约不变）。
- 保留 `image_download_allowed_hosts` SSRF 白名单 + 私网 IP 校验（`_is_safe_image_url`），并在 P5 收敛到统一 egress 客户端。

---

## 5. P3 — 异步任务队列（Redis + RQ）

- 引入 **RQ**（比 Celery 轻，契合现有栈）或 Celery；worker 进程独立。
- 任务定义（`backend/tasks/queue.py` + `misc/worker` 启动命令）：
  - `generate_effect_image`：生图（耗时长，移出请求路径）。
  - `send_notifications`：站内信/通知。
  - `run_moderation`：调用 `review.review_image`（占位，真实 API 接好后自动生效）。
  - `reindex_knowledge`：RAG 索引构建（配合 P6 pgvector）。
- `/chat` 的 `image_task` 改为：入队 → 返回 `task_id` → 前端轮询 `/tasks/{id}`（或 webhook 推）。同步路径保留为 fallback（`image_provider=mock` 或 worker 不可用时）。
- 配置：`TASK_QUEUE_ENABLED`、`TASK_QUEUE_SYNC_FALLBACK`。

---

## 6. P4 — 限流 Redis 化

- 现有内存滑动窗口（`rate_limit_*`）抽象为 `RateLimiter` 接口：
  - `MemoryRateLimiter`（现状，dev 默认）
  - `RedisRateLimiter`（prod，多 worker 一致）
- 接口与调用点不变；`app_env=prod` 默认切 Redis。验证：起 2+ worker 压测，确认限流跨进程生效。

---

## 7. P5 — 安全加固

### 7.1 密钥管理
- `config.py` 已"代码不出现密钥字面值"，保持并补强：
  - 支持从密钥服务（KMS / Vault / 云 secret manager）按 `SECRET_PROVIDER` 读取，`{secret:name}` 占位解析（复用 MCP 的 `{env:}` 思路）。
  - `app_env=prod` 启动断言：强制 `JWT_SECRET`、`LLM_API_KEY`、`STORAGE_*`、`REDIS_URL` 等齐备，否则 fail-fast（已在 `api.py` lifespan 有 prod 断言，补清单）。

### 7.2 SSRF 收敛（egress allowlist）
- 新增统一出站 HTTP 客户端 `backend/net/egress.py`：
  - 所有外网请求（生图下载、`remote` 数据源、`tencent_geocode_url`、机审回调）必须经它。
  - 校验：host 在白名单 + 解析 IP 非私网/环回/链路本地（复用 `_is_safe_image_url` 逻辑，泛化）。
- 加单测覆盖私网 IP、非常规端口、DNS rebinding 场景。

### 7.3 鉴权矩阵与越权测试
- 产出 `misc/AUTHZ_MATRIX.md`：端点 × 角色（C / merchant / admin）允许表。
- 自动化测试：merchant 访问他人店铺订单、admin 越权改用户、C 端越权读他人地址等，全部应 403/404。

### 7.4 依赖与审计
- 接入 `pip-audit`（后端）、`npm audit`（前端）到 CI；版本 pin（`misc/requirements.txt` 已存在，补 hash/pin）。
- 静态扫描：ruff 现有规则 + 新增 secrets 扫描（如 gitleaks）防止密钥误提交（`.gitignore` 已忽略 `.env`，再加扫描兜底）。

### 7.5 机审 Fail-Closed
- `review.py` 改造：新增 `CONTENT_REVIEW_FAIL_CLOSED`（prod 默认 `true`）。
  - `true`：未接入真实 API（`content_review_url` 空）时**拒绝上传**并告警，而非静默放行。
  - 真实 API 仅替换 `_review_remote` 实现，上传端点零改动（README 已承诺的契约）。

### 7.6 日志脱敏
- `setup_logging` 已声明不打印敏感字段；新增断言测试：扫描 logger 调用确保 `api_key`/`phone`/`token` 不进日志。

---

## 8. P6 — AI 智能体生产化

### 8.1 LLM 可靠性（`agent/engine/llm.py`）
- 重试：指数退避 + 抖动，区分可重试（超时/5xx/限流）与不可重试（4xx 鉴权）。
- 超时分级：`llm_timeout`（单次）与 `request_timeout`（整轮）已存在，新增按工具类型细分。
- **熔断**：连续失败达阈值（如 5 次）进入 OPEN 状态，快速失败并降级规则引擎，半开探测恢复。
- **多 provider 兜底**：`LLM_PROVIDERS` 列表（primary/secondary，可不同 base_url/model），primary 失败自动切 secondary；配置驱动。
- **优雅降级**：LLM 不可用时回到"规则引擎 + 知识库检索"兜底（README 已有降级路径，确保产物结构完整、不抛裸异常）。

### 8.2 成本控制
- Redis 计数器：per-user 日/月 token 预算 + 全局预算；超限返回友好提示并限流。
- 记录 `prompt_tokens`/`completion_tokens` 到指标（P7）。
- 复用 `rate_limit_chat_per_minute` 已有 IP 级限流，叠加用户级预算。

### 8.3 生图稳定性（`image provider`）
- provider 健康探测；`api2img/dashscope/zhipu` 链路 fallback（一个失败切下一个）。
- 相同 prompt（+参数）结果缓存（Redis + 对象存储 key），降本提速。
- 成本追踪随生图任务上报指标。

### 8.4 RAG 扩展（`agent/knowledge/store.py`）
- 新增可选 `PgVectorBackend`：知识条目入库 pgvector，`query_knowledge(domain, query)` 接口不变（现状 TF-IDF 作为小数据默认 + 保底）。
- 配置 `RAG_BACKEND`(tfidf|pgvector)；`reindex_knowledge` 任务（P3）负责建索引。
- 混合检索策略（关键词保底 ∪ 向量召回）保留。

### 8.5 质量护栏
- 方案产物 schema 校验（花材/配比/价格/库存），价格与库存强制取自 DB（README 已承诺服务端权威），不一致标记人工复核。
- 建立 **eval 集 + 回归测试**：固定需求 → 期望方案维度/价格区间，CI 跑回归，防 LLM 升级/换模型导致质量漂移。
- 不确定项（低置信度检索/超预算）在 `plan_card` 标注提示，而非静默猜测。

---

## 9. P7 — 可观测性（轻量，支撑上面验证）
- 结构化日志（JSON 格式可选），关键字段：trace_id、user_id、tool 序列、耗时、token 数。
- 暴露 `/metrics`（Prometheus 格式）：QPS、P95 耗时、错误率、LLM 成本、生图成功率、限流命中。
- 告警阈值（文档化）：LLM 错误率、熔断状态、worker 存活、Redis 连通。

---

## 10. 验证总表（每个 Phase 收尾必跑）
- 后端：`python -m pytest -q -c misc/pyproject.toml`（含 PG 矩阵）、`python -m ruff check --config misc/pyproject.toml .`
- 前端：`npx eslint src`、`npx vitest run`、`npm run build`（H5/）
- 专项：SSRF 单测、鉴权越权单测、LLM 熔断单测、Fail-Closed 单测、PG 迁移用例。
- 冒烟：启动后端 `/health`、跑一次 `/chat` design 链路、生图走异步队列、对象存储读写。

## 11. 回滚策略
- 每个 Phase 通过配置开关独立可关：`STORAGE_BACKEND=local`、`TASK_QUEUE_ENABLED=false`、`RAG_BACKEND=tfidf`、`CONTENT_REVIEW_FAIL_CLOSED=false`、`RedisRateLimiter` 回退 `MemoryRateLimiter`。
- 数据库：PG 与 SQLite 双实现并存，切回不丢数据（SQLite 为子集，迁移单向需注意；生产以 PG 为准，回滚仅限紧急，需备份）。
- 全部改动走 PR + CI，禁止直接改 main。

## 12. 建议实施顺序
P0 → P4（限流 Redis，低成本高收益）→ P5（安全，含 Fail-Closed）→ P1（PG，核心但工作量大，可并行小步）→ P2（对象存储）→ P3（异步队列）→ P6（AI 生产化）→ P7（可观测）。

---
*本文档为实施蓝图，具体代码改动在对应 Phase 启动时再逐文件落地。*
