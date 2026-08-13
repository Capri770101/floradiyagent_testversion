# 版本对比：`111`（GitHub 主仓库） vs `flora_diy_agent`（工作副本）

> 生成时间：2026-08-13 | 背景：用户怀疑"开发错项目版本"，经核查属实。本文为收口决策用的完整对比。

## 1. 核心结论

- 两个版本是**从某个共同祖先各自演化的真分叉**，不是"同一份代码的不同快照"（两边几乎所有共享文件内容都不同）。
- `C:\Users\Capri\Desktop\111` = **真·git 仓库**，`origin = github.com/Capri770101/floradiyagent_testversion.git`，分支 `main`。**这正是 ChatGPT review 审的那一版**（review 提到的 `respond_to_user` / `session_flags` / `runtime.py` / `engine/` / `skills/` 全在此版）。
- `C:\Users\Capri\Desktop\flora_diy_agent` = **无 git 跟踪的工作副本**（WorkBuddy 项目目录），承载了我们前 4~5 轮全部升级（向量 RAG / typer CLI / `FlowerRequirement` / metrics / Makefile+CI / 96 测试）。
- **关键：两版互补而非包含**——各有对方缺失的核心能力，纯"二选一"都会丢东西。

---

## 2. 文件清单差异（`diff -rq`，已排除 git/缓存/数据/产物）

**仅 `111` 有（移植时若丢弃会丢失）：**
- `runtime.py` —— contextvars 依赖注入容器
- `storage/image_gen.py` —— 独立生图工厂 `build_image_gen`
- `scripts/` —— `demo_flow.py` 演示脚本
- `openapi.json` —— API 规范导出
- `LICENSE`
- tests：`test_agent_multitool` / `test_exceptions` / `test_flow` / `test_image_confirm` / `test_image_gen` / `test_protocol_contract`

**仅 `flora_diy_agent` 有（我们加的升级）：**
- `knowledge/` —— 向量 RAG 检索（store.py + 多个 json 知识域）
- `requirements.py` —— `FlowerRequirement` 结构化需求状态
- `cli.py` + `cli_repl.py` —— typer 本地 CLI
- `Makefile` + `.github/`（CI）+ `pyproject.toml`
- `Dockerfile` + `docker-compose.yml` + `.dockerignore`
- `security.py` —— 鉴权
- `INTEGRATION.md` —— 远端后端接入约定
- tests：`test_auth` / `test_chat_flow` / `test_diy_design` / `test_diy_iteration` / `test_extract_dims` / `test_image_provider` / `test_knowledge` / `test_knowledge_scenes` / `test_knowledge_vector` / `test_repository_remote` / `test_requirements` / `test_robustness` / `test_search_honesty`

**两边都存在但内容不同（已分叉）：**
`agent.py` `api.py` `config.py` `tools.py` `README.md` `.env` `.gitignore` `requirements.txt`
`engine/`（__init__/llm/state/ui_protocol）`skills/`（__init__/skill_order）`storage/`（__init__/db/memory/repository/tasks）

---

## 3. 架构接线对比（最关键，决定"能不能直接拷贝"）

| 维度 | `111`（GitHub 主仓库） | `flora_diy_agent`（工作副本） |
|------|------------------------|------------------------------|
| 主类 / 入口方法 | `Agent.chat()` | `ReActAgent.run()` |
| 依赖注入 | `runtime.py` contextvars：`rt.user_id` / `rt.location` / `rt.repository` / `rt.memory` / `rt.tasks` | `inject_context=True` 注入 `_context`（user_id/session_id/location/requirement） |
| 工具终结方式 | **`respond_to_user` 终结工具** + `_finalize()`（校验 stage 合法性、`ui ∉ ALL_UI` 钳制） | 自然语言回复即结束 + `_derive_ui()` / `_derive_next_stage()` 后端推导（等价兜底，但未用终结工具） |
| 工具注册 API | `register_tool(name, desc, params, func)` + `tool_descriptions()` / `tool_body_text()` | `@register_tool` 装饰器 + `to_openai_tools()` + `inject_context` |
| 结构化需求状态 | ❌ 无（仅 `session_flags`） | ✅ `FlowerRequirement`（sessions.requirement 列，每轮 extract→merge→持久化→注入） |
| 生图实现 | `storage/image_gen.py`（`build_image_gen`）+ `TaskManager(delay)` | `storage/tasks.py` 内聚，多 provider（zhipu/api2img/dashscope）+ base64 落盘 + 轮询（**能力更强**） |
| 远端后端切换 | ❌ **无 RemoteRepository** | ✅ `RemoteRepository` + `DATA_SOURCE=remote`（review 最看重的"解耦 SaaS 后端"恰好在此版） |
| 生图确认守卫 | ✅ `session_flags`（image_confirmed / image_submitted） | ❌（由阶段 + 工具内判断替代） |

---

## 4. 能力矩阵

| 能力 | `111` | `flora_diy_agent` | 说明 |
|------|:----:|:----------------:|------|
| ReAct + function calling 主循环 | ✅ | ✅ | 两边都有，正确架构 |
| `respond_to_user` 结构化终结 | ✅ | ❌ | 111 强制模型以工具收尾，输出更 deterministic |
| `session_flags` 生图守卫 | ✅ | ❌ | 111 后端强约束生图确认 |
| `runtime.py` contextvars DI | ✅ | ❌ | 111 的注入更"全局"，flora 用参数注入 |
| `storage/image_gen.py` 独立模块 | ✅ | ❌(合并进 tasks) | flora 的 tasks.py 多 provider，能力更全 |
| `RemoteRepository` + `DATA_SOURCE` 远端切换 | ❌ | ✅ | **review 1 号建议，仅 flora 实现** |
| 向量 RAG `knowledge/` | ❌ | ✅ | 我们这轮加的 |
| `FlowerRequirement` 结构化需求 | ❌ | ✅ | review 点名的最关键缺口，已补 |
| typer CLI | ❌ | ✅ | 本地零 API 试设计 |
| Makefile + CI + Docker | ❌ | ✅ | 工程化收尾 |
| 鉴权 `security.py` | ❌ | ✅ | |
| 测试规模 | ~8 文件（含 protocol/image 专项） | **96 passed / 15 文件** | flora 覆盖更广 |

---

## 5. 移植性评估（无论选哪版为准，另一版的独特价值都要搬过来）

**若以 `111` 为准，把 flora 升级搬过去：**
- 可直接拷（自包含、改动小）：`knowledge/`、`requirements.py`、`cli.py`、`Makefile`、`.github/`、`Dockerfile`、`security.py`、`INTEGRATION.md`、对应 tests。
- 需改造：`RemoteRepository` 要并入 111 的 `BaseRepository` 体系；agent 编排要把 flora 的 `FlowerRequirement` 接入（111 当前无此概念）。
- 风险：会丢掉 111 的 `respond_to_user` / `session_flags`（除非同时保留）。

**若以 `flora_diy_agent` 为准，把 111 hardening 补进来：**
- 可直接加：`openapi.json`、`LICENSE`、`scripts/`、111 的 `test_protocol_contract` / `test_image_confirm` / `test_image_gen` 等专项测试。
- 建议补的 hardening：`session_flags` 生图守卫（flora 当前靠阶段+工具内判断，不如 flags 显式）、`respond_to_user` 终结工具（可选，让 UI 输出更 deterministic）、`runtime.py` 思路参考。
- `image_gen.py` 不必搬（flora 的 `tasks.py` 已更强）。

---

## 6. 我的判断与建议

- 两版**互补**，纯二选一会丢能力，应做**合并**而非覆盖。
- 推荐 **以 `flora_diy_agent` 为合并基底**：它已具备 review 最看重的 `RemoteRepository` 解耦 + 全部功能升级 + 96 测试 + CI；再把 `111` 的 production hardening（`session_flags`、`respond_to_user` 可选、`openapi.json`、`LICENSE`）补进来。
- 合并完成后，让结果 `git init` 并接上现有 `floradiyagent_testversion` 远端（保留 `111` 的 GitHub 历史可通过添加 remote 后 merge/cherry-pick，避免覆盖）。
- 这套路径比"以 111 为准"工作量更小，且保住 review 最在意的解耦能力。

---

## 7. 待你决策

1. **以 `flora_diy_agent` 为准 + 补 111 hardening（推荐）** —— 合并后接 GitHub。
2. **以 `111` 为准 + 移植 flora 升级** —— 保留 111 的 `respond_to_user`/`session_flags` 体系。
3. **先小范围试合并一两个模块**（如只把 `session_flags` 生图守卫搬进 flora），看手感再决定全量。
4. **暂不合并** —— 维持现状，你先核对两边代码。

> 注：截至本文，未对任何文件做移动/合并/删除；`flora_diy_agent` 含 `_legacy/` 备份，无数据丢失风险。
