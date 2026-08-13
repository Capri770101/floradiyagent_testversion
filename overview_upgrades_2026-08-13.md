# 四方向优化升级（2026-08-13）

无真实业务数据前提下，木木勾选「方案可落地化 + 维度抽取增强 + 本地 CLI + 工程化收尾」四项全做。

## 1. 方案可落地化（`tools.py`）
`design_diy_plan` / `generate_diy_plan` 输出新增四块（纯模板，不依赖真实数据）：
- `diy_steps`：6 步插花指引（备材处理→定高构图→填充层次→配色比例→包装收尾→醒花养护），内容随本方案实际花材/包装动态生成。
- `care_tips`：通用养护 + 主花特例（百合去雄蕊防染色 / 绣球喜水急救 / 向日葵防垂头）。
- `card_message`：贺卡寄语，场景基调优先、避免长串花语堆砌。
- `budget_breakdown`：按花材档位单价估算主花/配材/叶材/包装分项，标注"估算，实际以门店为准"。

## 2. 维度抽取增强（`tools.py`）
- 扩表：对象别名、场合（婚礼/升职/入职）、风格别称（港风/中古/奶油风/法式）、色系别称（粉嫩/桃红/酒红/撞色）、氛围词（莫兰迪→素雅、马卡龙→清新、轻奢/治愈…）。
- 口语预算 `_BUDGET_ORAL`（两三百→250 等）+ 货币变体（块/块钱），正则放宽。
- **关键修复**：抽取改「最长命中」优先——原单字「红」会遮蔽「桃红」→粉，导致色系误判。
- 新增 `tests/test_extract_dims.py`（8 例）。

## 3. 本地 CLI（`cli.py`，typer）
子命令 `design / knowledge / revise / tools / chat`，无 API 也能试设计与跑回归。venv 已装 typer 0.27.1。

## 4. 工程化收尾
- `.env.example` 补 RAG 配置段。
- `api.py` 新增 `GET /metrics`（进程内请求计数 + 配置快照），`/health` 暴露 `rag_enabled`。
- `Makefile` + `.github/workflows/ci.yml`（ruff + pytest，Python 3.11/3.12）。
- `requirements.txt`（pip freeze，CI 可复现）。

## 验证
- `pytest`：**70 passed**（原 59 + 新增 11），ruff 全过。
- 冒烟：CLI `design` 输出含四块新字段；`/metrics` 计数正确；维度抽取单测全过。

## 文件清单
- 改：`tools.py`、`api.py`、`.env.example`、`README.md`、`pyproject.toml`（cli extra）
- 新增：`cli.py`、`tests/test_extract_dims.py`、`Makefile`、`.github/workflows/ci.yml`、`requirements.txt`

## 下一步可选
- 换真实业务数据（`knowledge/*.json`，按 `TEMPLATE.md`）。
- 花材量大时把 `_VectorSpace` 升稠密向量 RAG。
- 千问平台：仍「先观望」，待文档成熟再接。
