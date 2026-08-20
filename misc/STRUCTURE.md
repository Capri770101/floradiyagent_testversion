# 项目结构说明（flora_diy_agent）

> 更新于 2026-08-20。重构目标：智能体相关文件（代码 / 知识库 / 测试 / 专属数据库）全部收拢进 `agent/`，后端进 `backend/`，工程与杂项进 `misc/`，根目录仅保留文件夹 + 两个必需文件。

## 一、总览

```
flora_diy_agent/
├─ agent/                  # 智能体（独立文件夹，含专属数据库与测试）
│  ├─ agent.py             #   智能体主类：ReAct 主循环 + skill 编排 + DIY 入库钩子
│  ├─ tools.py             #   工具注册表 + 内建工具（设计/生图/检索/下单等）
│  ├─ cli.py               #   本地调试 CLI（python agent/cli.py ...）
│  ├─ requirements.py      #   意图解析 / 维度抽取 / 搜索诚实化等辅助逻辑
│  ├─ data/                #   智能体专属数据
│  │  └─ agent_memory.db   #     长期记忆库（历史遗留独立文件，代码零引用，归档保留）
│  ├─ tests/               #   智能体测试（13 文件 + conftest.py）
│  │  ├─ conftest.py       #     测试环境（临时 DB / 离线 LLM / mock 生图 / 限流重置）
│  │  ├─ test_diy_design.py / test_diy_iteration.py / test_diy_storage.py
│  │  ├─ test_extract_dims.py / test_history_sanitize.py / test_image_provider.py
│  │  ├─ test_knowledge.py / test_knowledge_scenes.py / test_knowledge_shops.py / test_knowledge_vector.py
│  │  ├─ test_plan_resolution.py / test_respond_validation.py / test_search_honesty.py
│  ├─ engine/              #   LLM 封装 / 会话状态机 / UI 协议
│  ├─ skills/              #   技能自动扫描注册（skill_order.py 下单技能）
│  ├─ knowledge/           #   领域知识库 JSON + RAG 检索（TF-IDF + n-gram，零依赖）
│  ├─ mcp_servers/         #   本地 MCP 服务器（vision：智谱 GLM-4V 读图）
│  └─ examples/            #   实跑质量检查脚本（live_check.py）
├─ backend/                # 后端服务（FastAPI，uvicorn backend.api:app）
│  ├─ api.py               #   FastAPI 装配层（CORS/中间件/异常/lifespan + 路由挂载）
│  ├─ config.py            #   全部配置（读 misc/.env；db_path 指向 data/agent_service.db）
│  ├─ security.py          #   微信 code2session / JWT / 手机号验证码 / 账号密码 / 商家注册
│  ├─ review.py            #   内容机审（阶段5：开关预留 + 真实 API 挂载点，dev 放行）
│  ├─ routers/             #   auth/chat/catalog/commerce/merchant/admin/notify/recommend/report
│  ├─ storage/             #   db/memory/repository/catalog/diy/commerce/payment/tasks/notify/report/recommend
│  │                       #   ↑ memory/diy/tasks 为「智能体 + 后端 API」共享存储层
│  └─ scripts/             #   种子/清理脚本（seed_demo / seed_admin / clear_seed）
├─ H5/                     # React + Vite + Tailwind 移动端小程序（跳舞兰视觉）
│  ├─ src/                 #   C 端（index.html 入口；已剥离商家代码，bundle 不再含商家工作台）
│  ├─ src/merchant/        #   商家端独立应用（merchant.html 入口，独立令牌 floradiy_merchant_token）
│  ├─ src/admin/           #   管理后台独立应用（admin.html 入口，独立令牌 floradiy_admin_token）
│  └─ merchant.html / admin.html / index.html   # 三端三个构建入口
├─ tests/                  # 后端 API / 业务测试（25 文件 + conftest.py，263 用例）
│  ├─ conftest.py          #   测试环境（与 agent/tests/conftest.py 同构）
│  └─ test_auth*.py test_order_*.py test_merchant*.py test_admin*.py
│     test_payment.py test_rate_limit.py test_permissions.py ...（鉴权/权限/订单/支付/限流/价格防篡改/管理后台）
├─ data/                   # 运行时落盘（gitignore）
│  ├─ agent_service.db     #   共享主库：会话/消息/记忆/DIY 方案/商品/订单/用户（后端 + 智能体共用）
│  ├─ generated/           #   AI 生图产物
│  └─ uploads/             #   商家上传素材
├─ misc/                   # 工程与杂项（全部工程文件在此）
│  ├─ pyproject.toml       #   pytest / ruff 配置（testpaths 指向 ../tests 与 ../agent/tests）
│  ├─ .env / .env.example  #   密钥与配置（gitignore）
│  ├─ Dockerfile / Dockerfile.frontend / docker-compose.yml / Makefile / requirements*.txt
│  ├─ nginx/frontends.conf #   三端独立域名 nginx 模板（三端口=三入口 + /api /uploads 反代）
│  ├─ README.md            #   项目说明（含目录结构）
│  ├─ .workbuddy/ .github/ #   Agent 配置与 CI（.github 已移入，CI 停用）
│  ├─ docs/                #   架构文档（DATABASE_ARCHITECTURE.md 等）
│  └─ *.md                 #   任务书 / 设计文档 / 复盘
├─ .gitignore              # 仓库忽略规则（保留在根目录，功能必需）
├─ AGENTS.md               # opencode 工作约定（保留在根目录，功能必需）
└─ (隐藏工具目录) .idea/ .playwright-mcp/ .pytest_cache/ .ruff_cache/ __pycache__/
```

## 二、数据库分布（三层）

| 数据库 | 位置 | 归属 | 说明 |
|---|---|---|---|
| `agent_service.db` | `data/` | 共享主库 | 会话/消息/记忆 + 业务（商品/订单/用户）。后端 API 与智能体共用单库，`config.py` 的 `db_path` 指向它 |
| `agent_memory.db` | `agent/data/` | 智能体专属 | 历史遗留的独立记忆库（24KB，代码零引用），归档保留 |
| `flora_test_agent.db` | 系统临时目录 | 测试 | pytest conftest 每次运行前重建的隔离测试库 |

历史 0 字节空库（`flora.db` / `app.db` / `backend/storage/floradiy.db`）已清理。
`agent_service.db-wal/-shm` 为运行中进程的 WAL 残留，属正常现象。

## 三、测试布局

- **`tests/`**（25 文件）：后端 API / 业务（鉴权、权限、订单、支付、限流、价格防篡改、管理后台、会话、推荐、商家认证、内容举报）。
- **`agent/tests/`**（13 文件）：智能体（DIY 设计引擎、迭代、资产库、知识库 RAG、生图 provider、记忆净化、意图解析、ReAct 契约）。
- **conftest 双份**：`tests/conftest.py` 与 `agent/tests/conftest.py` 内容一致（临时 DB + 离线 LLM + mock 生图 + 限流重置）。
  必须分别放置：pytest 的 `confcutdir` 默认取配置文件目录（`misc/`），根目录与 misc/ 的 conftest 都会被排除或仅在特定模式下加载；conftest 必须位于收集路径链上。

## 四、常用命令（工作目录 = 项目根）

| 命令 | 用途 |
|---|---|
| `python -m pytest -q -c misc/pyproject.toml` | 全量测试（263 用例，tests/ + agent/tests/） |
| `python -m pytest "tests/xxx.py" -c misc/pyproject.toml` | 指定文件（后端） |
| `python -m pytest "agent/tests/xxx.py" -c misc/pyproject.toml` | 指定文件（智能体） |
| `python -m ruff check --config misc/pyproject.toml .` | lint |
| `python -m uvicorn backend.api:app --host 127.0.0.1 --port 8080` | 后端启动（根目录） |
| `docker build -f misc/Dockerfile .` / `docker compose -f misc/docker-compose.yml up` | 容器 |