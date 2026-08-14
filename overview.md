# P0 收尾：状态机与生图收敛修复总览

## 本轮修复的三个 bug（承接第十六轮 P0 重构）

### 1. 全新会话首句即 DIY 进不去流程
- **现象**：用户第一句就说「自己 DIY 设计一束花」却停在 `analyze`。
- **根因（双层）**：
  - `agent._derive_next_stage` 的 `ANALYZE` 分支无条件 `return SELECT_MODE`，不尊重 diy 意图；
  - `engine.state._ALLOWED[ANALYZE]` 邻接表只列 `SELECT_MODE`，`can_transition` 把推导结果拦回 `ANALYZE`。
- **修复**：ANALYZE 分支改为 `if intent["diy"]: return DIY_DESIGN else SELECT_MODE`；邻接表放开 `ANALYZE → DIY_DESIGN`。

### 2. 生图始终生成不出来（live 抽测复现）
- **现象**：「帮我生成效果图看看」进 `image_gen`，但 LLM 只说"正在生成"不调工具；「好的生成吧」又被当确认推到 `shop_recommend`，图永不渲染。
- **根因（三层）**：
  - 原 `image_confirmed` 仅在进入 image_gen 当轮 `is_affirmative()` 才置位，「帮我生成」漏判；
  - 兜底补调闸门原限定 `new_stage == IMAGE_GEN`，用户说生成吧后已离开该阶段即不补调；
  - 兜底补调在 `update_stage` 之前执行，DB 阶段仍是旧值，触发 `generate_effect_image` 工具内置安全闸门「当前阶段不可生成」报错。
- **修复**：进入 IMAGE_GEN 即无条件置 `image_confirmed=1`；兜底闸门放宽到「已确认 + 未生成 + 未到终态」；补调前临时 `update_stage(IMAGE_GEN)` 让工具闸门通过，末端 `update_stage(new_stage)` 修正回真实阶段。

### 3. 测试回归
- `test_diy_flow_image_task_then_shops` 原断言 task_id 在「好的生成吧」轮；修正后生图在「生成效果图看看」轮即触发（更符合 UX），断言同步前移。
- 新增 `tests/test_state.py` 两个状态机回归（ANALYZE→DIY 合法 + `_derive_next_stage` 尊重 diy 意图）。

## 验证
- **Mock 模式**：`pytest 107 passed`、ruff 全过。
- **Live 真实 DeepSeek 抽测**（独立 UID 避开 SQLite 状态污染）：diy_design → image_gen → shop_recommend 全链路打通，task_id 最终下发（图可渲染）。
- **uvicorn**：已用最终代码重启（live 模式，PID 17968，`http://127.0.0.1:8000`）。
- **已知边界**：live 下若 LLM 未先调 `generate_diy_plan` 产出结构化方案，`generate_effect_image` 会报「请先设计方案」——属 LLM 方案可靠性问题（历史已知 `generate_diy_plan` 无真实设计能力），不在本次 machinery 范围。

## 提交（本地，未 push）
- `4f271df` refactor: 移除 H5 前端（api.py + h5/* 暂存删除）
- `ccde193` fix: 状态机与 stage 推进修复（agent.py / engine/state.py / engine/llm.py / storage/* / tests/*）
- 远端 `main` 仍停在 `4638f26`，**未 push**（沿用"视觉验收后一起 push"约定；H5 已删无前端可验收，待你确认是否推）。
- 未跟踪：`SYSTEM_CHECK_REPORT.md`（第十六轮系统检查报告）留作参考，未纳入提交。
