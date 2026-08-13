# flora_diy_agent · 当前版本完整说明

> 本文档说明 **2026-08-13 推送到 GitHub 的当前版本**（`floradiyagent_testversion` / `main`，commit `212c814`）。
> 这是把两份 Python 分叉版（`111` 被 ChatGPT review 那版 + 本地 `flora_diy_agent` 升级工作副本）**取长补短融合**后的最终形态，也是唯一持续维护的活跃版本。

---

## 1. 项目定位

**花卉 DIY 设计智能体（Flower DIY Design Agent）**——不是「花卉购买导购」，而是根据用户表达**设计出一份花艺方案**（花材 / 配比 / 色彩 / 寓意 / 包装 / 预算），再按需把方案落到「店铺推荐 + 下单 + 支付跳转」等承接环节。

核心卖点是 **DIY 设计能力**，店铺 / 订单只是把设计落地的手段，不是核心。

---

## 2. 技术栈

| 层 | 选型 |
|----|------|
| Web 后端 | FastAPI + Pydantic v2 + pydantic-settings |
| Agent 编排 | 自研 ReAct 主循环（OpenAI function-calling 规范，DeepSeek/兼容模型） |
| 知识检索 | 纯 Python 向量 RAG（`knowledge/store.py`：TF-IDF + 字符 unigram/bigram，零重依赖） |
| 需求建模 | `FlowerRequirement` 一等公民结构化需求状态 |
| 数据访问 | Repository 抽象：`MockRepository`（开发） + `RemoteRepository`（接 SaaS 后端，`.env` 切换） |
| 生图 | 多 provider（智谱 zhipu / 万相 dashscope / api2img / mock），base64 落盘 + 异步轮询 |
| 存储 | SQLite（会话 / 消息 / 记忆 / 任务），分层 `storage/` |
| CLI | typer 本地命令行 |
| 工程化 | Makefile + GitHub Actions CI（py3.11/3.12）+ Docker + Ruff + pytest |

---

## 3. 目录结构

```
flora_diy_agent/
├── agent.py              # 智能体主类 ReActAgent：ReAct 主循环 + 状态机驱动
├── tools.py              # 工具注册表（@register_tool）+ 9 个工具实现 + 抽取器
├── requirements.py       # FlowerRequirement 结构化需求状态 + extract_requirement
├── api.py                # FastAPI 入口：/chat /tasks /chat/reset /health /metrics
├── config.py             # pydantic-settings 配置（含 RAG / 生图 / 鉴权 / 远程仓库）
├── security.py           # JWT 鉴权（AUTH_REQUIRED 开关）
├── cli.py / cli_repl.py  # typer CLI + REPL
├── engine/
│   ├── state.py          # SessionStage 状态枚举 + can_transition 校验
│   ├── ui_protocol.py    # UI 协议类型（text/dialog_options/plan_card/...）
│   └── llm.py            # call_llm 封装（兼容 OpenAI 协议）
├── knowledge/
│   ├── store.py          # 向量 RAG 检索（混合：关键词 ∪ 语义）
│   └── *.json            # 花材/风格/场景/预算/包装 知识库
├── storage/
│   ├── db.py             # SQLite 建表（含 session_flags 表）
│   ├── memory.py         # 会话/消息/长期记忆/session_flags 读写
│   ├── repository.py     # MockRepository + RemoteRepository + build_repository
│   └── tasks.py          # 异步生图任务管理
├── tests/                # 15 个测试文件，88 用例，全绿
├── INTEGRATION.md        # 远程后端接入契约
├── Makefile / .github/   # 工程化
└── VERSION_COMPARISON_111_vs_flora.md  # 两版差异对比（历史参考）
```

---

## 4. 核心架构

### 4.1 Agent 主循环（ReAct + Tool Calling）
```
用户输入 → System + History → LLM
  → LLM 决定调用哪些 tool（OpenAI function calling）
  → execute_tool 执行 → observation 以 role="tool" 回填
  → 带结果再让 LLM 思考 → 直到模型调 respond_to_user 终结本轮
```
- 处理了「同一轮多个 tool_calls 必须作为同一个 assistant message 回填」的协议坑（避免 DeepSeek 多轮 400）。
- **后端不盲信 LLM**：`can_transition()` 校验状态流转，`respond_to_user` 的 `ui`/`stage` 经状态机钳制。

### 4.2 状态机（业务约束）
```
ANALYZE → SELECT_MODE → VIEW_PLAN ⇄ DIY_DESIGN → IMAGE_GEN
        → PLAN_CONFIRM → SHOP_RECOMMEND → ORDER_CONFIRM → DONE
```
允许 `VIEW_PLAN ⇄ DIY_DESIGN` 回退；每次流转后端强制 `can_transition` 校验。

### 4.3 UI 协议（Agent → 前端契约）
`text / dialog_options / plan_card / shop_card / order_card / pay_jump`，每种含独立 data schema——前端按协议渲染，无需猜语义。

### 4.4 知识库向量 RAG（`knowledge/store.py`）
- 纯 Python TF-IDF + 字符 n-gram（中文友好），**零 numpy/sklearn 依赖**（dev 零成本）。
- 混合检索：关键词命中保底 ∪ 向量语义召回（仅多 token / 长自然语句触发；单 token 走精确关键词不退化）。
- 接口 `query_knowledge(domain, query)` 签名不变，上层零改动。

### 4.5 结构化需求状态（`requirements.py`）
`FlowerRequirement`（occasion / recipient / relationship / style / colors / mood / budget_min,max / location / raw）+ `extract_requirement(text)` + `merge`（多轮累加）。
**这是从「LLM context 里的自由文本」收敛成一等公民对象的关键一层**——DIY 设计、方案检索、店铺检索共用同一抽取器，可做真实过滤 / 排序。

### 4.6 Repository 抽象（SaaS 解耦）
- `MockRepository`（开发测试）+ `RemoteRepository`（`.env` 设 `DATA_SOURCE=remote` 即接真实 SaaS 后端）。
- 远程只需实现 `INTEGRATION.md` 约定的端点（GET /plans、/shops…），上层业务 / 状态机 / UI **零改动**。
- **Agent 不持有业务数据库**，符合「Agent 只做智能层、业务数据在 SaaS 后端」原则。

### 4.7 生图安全闸门（`session_flags` + `is_affirmative`）
- 生图须用户明确同意（`image_confirmed=1`）→ 后端 `generate_effect_image` 三重校验：阶段 + image_confirmed + image_submitted（防同轮重复提交）。
- `is_affirmative` 关卡：进入 IMAGE_GEN 且用户明确肯定才写标记；进入生图阶段自动清历史 `image_*` 标记。

---

## 5. 融合来源说明（两版各贡献了什么）

**来自 `flora_diy_agent`（广度更全，作为基底）：**
- 向量 RAG 知识检索、FlowerRequirement 需求状态
- RemoteRepository + DATA_SOURCE 远端解耦
- typer CLI、Makefile/CI/Docker、auth 鉴权、GET /metrics
- 诚实化 Mock 检索（搜不到不返全量、location 透传使距离排序生效）
- 88 测试体系

**来自 `111`（深度 / 生产硬化）：**
- `session_flags` 生图安全闸门
- `respond_to_user` 终结工具（UI 协议输出更 deterministic）
- `is_affirmative` 生图确认关卡
- LICENSE / openapi.json

**刻意未融合：** `111` 的 `runtime.py`（contextvars DI）——当前 `inject_context` 已等价且更显式，强迁需重构所有工具签名，收益不大；`storage/image_gen.py` 旧生图管线已被更先进的 `storage/tasks.py` 替代。

---

## 6. 已注册工具（9 个）

| 工具 | 作用 |
|------|------|
| `search_plans` | 按关键词检索商家预设方案（搜不到**返回空**，不兜底全量） |
| `get_plan_detail` | 按 ID 取方案完整详情 |
| `retrieve_knowledge` | 向量 RAG 查知识库（花材/花语/搭配/风格/预算） |
| `generate_diy_plan` | 知识库驱动的结构化 DIY 设计（6 步插花 / 养护 / 贺卡 / 预算明细） |
| `revise_diy_plan` | 按反馈迭代方案 |
| `generate_effect_image` | 提交异步生图任务（受 session_flags 闸门约束） |
| `respond_to_user` | 终结工具：结构化输出 reply/ui/data/stage |
| `search_shops` | 按需求 + 距离/价格/评分综合排序推荐店铺 |
| `save_memory` | 写入长期用户偏好 |

---

## 7. 测试与质量门禁

- **pytest：88 用例全绿**（状态机流转 + /chat 冒烟 + 鉴权 + 远程仓库 + 知识库 RAG + 维度抽取 + FlowerRequirement + 检索诚实化 + 融合点回归）。
- **Ruff：全过**（lint + format，line-length 100）。
- CI：`.github/workflows/ci.yml` 在 Python 3.11 / 3.12 跑 ruff + pytest。

---

## 8. 本地运行

```bash
# 依赖（managed venv）
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 开发模式（mock，零成本）
cp .env.example .env          # DATA_SOURCE=mock，IMAGE_PROVIDER=zhipu（免费）
python -m uvicorn api:app --port 8000
# 打开 http://localhost:8000/docs 即可对话

# 本地 CLI（无需起服务）
python -m cli design "送给妈妈的粉色花束，预算200"
python -m cli knowledge --domain flowers --query "看望病人"
python -m cli chat --message "帮我设计一束"

# 测试 & lint
pytest
ruff check .

# 接真实 SaaS 后端（生产）
# .env: DATA_SOURCE=remote, REMOTE_API_BASE=https://your-backend, WECHAT_APPID/SECRET, AUTH_REQUIRED=true
```

---

## 9. 配置要点（`.env`）

| 项 | 含义 |
|----|------|
| `DATA_SOURCE` | `mock` / `remote`（切真实后端） |
| `LLM_*` | 模型 base_url / api_key / model（兼容 OpenAI 协议，默认 DeepSeek） |
| `IMAGE_PROVIDER` | `zhipu`(开发免费) / `dashscope` / `api2img` / `mock` |
| `RAG_*` | 向量检索开关 / top_k / 关键词加成 / 最小分 |
| `AUTH_REQUIRED` + `JWT_SECRET` | 开启 /chat 强制 Bearer |
| `WECHAT_*` / `PAY_PAGE_PATH` | 微信小程序接入与支付跳转 |

---

## 10. 已知边界 & 后续路线

- **知识库仍是示例数据**：`knowledge/*.json` 为占位花材/场景，真实业务数据待接入（花材量大时可把 `_VectorSpace` 升为句向量稠密 RAG，接口不变）。
- **Node 小程序版（`workbuddytest`）独立维护**：本 Python 版不覆盖它，两者是不同技术栈的并行产品线。
- **后续可选**：① 接真实业务数据；② 升稠密向量 RAG；③ 千问平台接入（待文档/账号就绪）；④ 把生产硬化（`session_flags`/`respond_to_user`）补端到端集成测试。

---

*生成于 2026-08-13，对应 GitHub commit `212c814`，已保留 `111` 全部历史。*
