# 花卉选购引导智能体（微信小程序后端）

基于 Python + FastAPI 的智能体（Agent）服务：通过 ReAct 模式驱动的花卉导购业务流程，
为微信小程序提供结构化 UI 协议的后端接口。

## 快速开始

```bash
pip install -r requirements.txt
# 复制 .env.example 为 .env，填入密钥（不填也可用 mock 大模型全链路运行）
uvicorn api:app --host 0.0.0.0 --port 8000
```

测试：

```bash
pytest -v
```

> 无 OpenAI/通义密钥时，`LLM_BACKEND=auto` 会自动回退到内置 mock 大模型，
> 脚本化走通完整业务流，便于本地开发与自动化测试。

## 项目结构

```
├─ agent.py              # 智能体主类：ReAct 主循环 + 状态机驱动
├─ tools.py              # 工具注册表 TOOL_REGISTRY + 内建工具
├─ skills/
│  ├─ __init__.py        # 技能自动发现（新增技能放此目录即自动注册）
│  └─ skill_order.py     # 下单技能：组装订单 + 支付页跳转参数
├─ engine/
│  ├─ llm.py             # 大模型封装（OpenAI 兼容 + mock 后端 + 流式预留）
│  ├─ state.py           # SessionStage 状态机与流转校验
│  └─ ui_protocol.py     # 结构化 UI 协议模型
├─ storage/
│  ├─ db.py              # SQLite 封装（每操作独立连接，线程安全）
│  ├─ memory.py          # 短期（消息历史）/ 长期（偏好 KV）记忆、订单
│  ├─ repository.py      # 数据仓库抽象 + Mock 实现（真实数据库接入预留）
│  ├─ tasks.py           # 异步任务（AI 生图）管理与轮询
│  └─ image_gen.py       # 生图供应商适配（mock / 通义万相预留）
├─ api.py                # FastAPI：/chat、/tasks、/chat/reset、/health
├─ config.py             # 配置集中管理（密钥读环境变量）
└─ tests/                # 状态机 + 端到端冒烟测试
```

## 接口契约

### POST /chat

请求：

```json
{ "user_id": "wx_openid", "message": "想给母亲买一束花，预算200元",
  "session_id": null, "user_role": "user", "location": "人民广场" }
```

响应（统一 `ChatResponse`，`ui` 为小程序渲染依据）：

```json
{
  "user_id": "wx_openid",
  "reply": "…自然语言回复…",
  "ui": "dialog_options | text | plan_card | shop_card | order_card | pay_jump",
  "data": { "…": "按 ui 类型约定的字段" },
  "tool_calls": [ { "name": "search_plans", "arguments": {…}, "result": "…", "status": "ok" } ],
  "session_id": "…"
}
```

| ui | data 结构 |
| --- | --- |
| `text` | `{}` |
| `dialog_options` | `{"question", "options": [{"label","value"}]}` |
| `plan_card` | `{"plan_id","name","price","desc","effect_image_url","merchant_name","plan_type"}` |
| `shop_card` | `{"shops":[{"shop_id","name","address","distance_km","price_range","rating"}], "question"}` |
| `order_card` | `{"order_id","plan_type","plan_name","quantity","total_price","shop_id"}` |
| `pay_jump` | `{"order_id","page_path","params":{"order_id"}}`（小程序下单页跳转） |

### 其他

- `GET /tasks/{task_id}`：AI 生图异步任务轮询（`status`: pending/done/error，`result_url` 为效果图）
- `POST /chat/reset`：`{"user_id": "…"}` 清空该用户会话与历史
- `GET /health`：健康检查（含当前 LLM/生图后端与已注册工具）

## 业务流（状态机）

```
需求分析 ANALYZE → 弹窗询问 SELECT_MODE → [现有方案 VIEW_PLAN ⇄ DIY DIY_DESIGN]
→ 效果图 IMAGE_GEN（异步，可选）→ 方案确认 PLAN_CONFIRM → 店铺推荐 SHOP_RECOMMEND
→ 下单确认 ORDER_CONFIRM → DONE（引导支付页）
```

规则：`PLAN_CONFIRM` 确认前，用户可随时在现有方案与 DIY 之间**来回切换**；
确认后进入店铺推荐，不再回退方案选择（放弃订单除外）。状态与历史持久化于 SQLite，重启不丢。

## 记忆

- 短期：`messages` 表按 user 持久化对话历史，每轮载入最近 20 条；
- 长期：`memories` 表存偏好 KV（预算/送花对象/色系…），对话开始注入系统提示词，
  模型识别到明确偏好时调用 `save_memory` 工具写入。

## 微信小程序对接说明

- 生产要求 **HTTPS + 已备案域名**，域名须加入小程序 request 合法域名白名单（联调用 IP 需在开发者工具关闭域名校验）；
- 用户身份：`wx.login` → `code2session` 获取 `openid`，作为 `user_id` 传入 `/chat`，长期记忆按 openid 隔离；
- `wx.request` 默认 60s 超时：本服务单请求完成全流程（含工具调用），生图等慢操作走 `task_id` 轮询，避免长连接；
- 用户角色 `user_role` 已预留（user/merchant/admin），本期仅实现普通用户，权限钩子在 `skills/skill_order.py` 中演示；
- 上线（中国大陆）可接入微信 `msgSecCheck` 对用户消息做内容安全检测（建议在网关层统一处理）。

## 大模型配置（OpenAI 兼容）

支持 DeepSeek、通义千问等 OpenAI 兼容供应商，`config.py` / `.env` 中 `base_url`、`api_key`、`model` 均可配置（`LLM_*` 优先，兼容旧 `OPENAI_*` 变量名）。DeepSeek 示例：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-…
```

通义千问兼容端点示例：

```env
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

## AI 生图（供应商可切换）

```env
# 方式一（推荐，免费）：智谱 CogView-3-Flash（开放平台 https://open.bigmodel.cn）
# 共享免费额度易 429，已内置 15s*次数退避重试；出图带智谱角标水印
IMAGE_PROVIDER=zhipu
IMAGE_ZHIPU_API_KEY=xxxx.xxxx                 # 智谱开放平台 API key
IMAGE_ZHIPU_MODEL=cogview-3-flash

# 方式二：api2img（OpenAI 兼容中转商，约 0.01 元/张，测试阶段省钱）
# 参考 https://github.com/MrVoler/api2img-skill 推荐的中转商（如 cc-vibe.com）
IMAGE_PROVIDER=api2img
IMAGE_OPENAI_BASE_URL=https://api.xxx.com/v1   # 中转商地址，v1 结尾
IMAGE_OPENAI_API_KEY=sk-…
IMAGE_OPENAI_MODEL=flux-1.1-pro                # 视中转商支持的模型
IMAGE_SIZE=1024x1024
IMAGE_RESULT_BASE=http://127.0.0.1:8000        # b64 结果落盘后的对外访问地址

# 方式三：DashScope（通义万相）
IMAGE_PROVIDER=dashscope
IMAGE_API_KEY=sk-…
IMAGE_MODEL=wanx-v1
```

| 供应商 | 成本量级 | 返回方式 |
| --- | --- | --- |
| zhipu（智谱 CogView-3-Flash） | 免费（带角标水印） | 直链透传；429 自动退避重试 |
| api2img（中转） | ~0.01 元/张 | 直链 url 透传；b64_json 落盘 `data/images/`，经 `/images/*` 静态提供 |
| dashscope（通义万相） | 按官方计费 | 异步任务轮询，返回 OSS 直链 |
| mock | 免费 | 占位 URL |

接口上各供应商统一：`generate_effect_image` 返回 `task_id`，客户端经 `/tasks/{id}` 轮询取 `result_url`，切换供应商不影响上层与前端。

## 真实数据库接入

`storage/repository.py::BaseRepository` 为统一契约，当前 `MockRepository` 内置示例数据。
接入真实库时实现该接口并在 `api.py` 装配处替换注册，上层零改动。