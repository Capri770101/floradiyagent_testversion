# 跳舞兰 · 花卉 DIY 设计智能体服务

基于 Python 的智能体后端服务，通过 FastAPI 提供 HTTP 接口，供 **H5 前端**与**微信小程序**调用。
核心能力为**花卉 DIY 设计**：理解用户表达 → 基于知识库设计结构化花艺方案（花材 / 配比 / 色彩 / 寓意 / 包装 / 预算）→ AI 生图看效果 → 推荐店铺 → 组装订单引导支付。
**DIY 方案资产库**会把用户确认过的方案持久化（个人复用 + 平台学习），让 AI 越用越懂你。

> 品牌：**跳舞兰**（Atelier de Fleurs）· 轻奢花艺 · 法式极简视觉（见 `maison-flora-design-prompt.md`）

---

## 一、项目定位

- **角色**：普通用户（user）/ 商家（merchant）/ 管理员（admin）。`users.role` 列管理角色。
- **登录**：手机号验证码（dev 固定码 `123456`）/ 微信小程序 `wx.login` / 账号密码（H5）。`AUTH_REQUIRED=true` 时所有业务接口强制鉴权。
- **模式**：ReAct（思考-行动-观察）主循环 + skill 编排（无状态机：流程由 ReAct 循环与工具产物依赖驱动）。
- **DIY 资产库**：确认入库（指纹去重）→ 成交升级（ordered + order_count）→ 个人检索复用 → 平台 `list_proven_plans` 学习。

---

## 二、目录结构

```
flora_diy_agent/
├─ api.py                # FastAPI 装配层（CORS/中间件/异常处理/lifespan + 挂载路由）
├─ routers/              # 按领域拆分（2026-08 重构，原 api.py 1300+ 行）
│  ├─ common.py          #   共享单例/限流器/身份解析/序列化辅助/请求模型
│  ├─ auth.py            #   认证（微信/手机号/账号）
│  ├─ chat.py            #   对话 / 生图任务 / 多会话
│  ├─ catalog.py         #   目录（方案/店铺）与运维端点
│  ├─ commerce.py        #   购物车/订单/支付/评价/券/积分/地址/收藏
│  ├─ merchant.py        #   商家工作台
│  └─ admin.py           #   管理后台
├─ agent.py              # 智能体主类：ReAct 主循环 + skill 编排 + DIY 入库钩子
├─ tools.py              # 工具注册表 + 内建工具
├─ skills/
│  ├─ __init__.py        # 自动扫描注册
│  └─ skill_order.py     # 下单技能（含 DIY 成交升级）
├─ engine/
│  ├─ llm.py             # call_llm：OpenAI 兼容封装（流式 / 非流式 / response_format）
│  ├─ state.py           # SessionStage（仅 UI 高亮）
│  └─ ui_protocol.py     # UI 消息协议 pydantic 模型
├─ storage/
│  ├─ db.py              # SQLite schema / 连接 / 事务
│  ├─ memory.py          # 短期（消息历史 + 多会话）+ 长期记忆
│  ├─ repository.py      # 数据仓库抽象（Mock / Remote）
│  ├─ catalog.py         # DB 商品目录 + 店铺智库档案
│  ├─ diy.py             # DIY 方案资产库（确认入库/去重/成交/复用）
│  ├─ commerce.py        # 电商事务（订单/购物车/券/积分/地址/评价）
│  ├─ payment.py         # 支付网关抽象（sandbox / wechat / alipay）
│  └─ tasks.py           # 生图任务管理（mock / dashscope / api2img / zhipu）
├─ knowledge/            # 领域知识库（RAG：TF-IDF + n-gram，零依赖）
├─ mcp_servers/          # 本地 MCP 服务器（vision：智谱 GLM-4V 读图）
├─ config.py             # 全部配置（含限流参数）
├─ security.py           # 微信 code2session / JWT / 手机号验证码 / 账号密码
├─ tests/                # 210 用例（鉴权/权限/订单/支付/限流/价格防篡改/DIY 资产库/RAG/管理后台…）
├─ H5/                   # React + Vite + Tailwind 移动端（跳舞兰视觉）
└─ README.md
```

---

## 三、会话焦点（Focus）

`SessionStage` 仅表示「用户当前在干嘛」的 UI 高亮，**不参与任何流程闸门**：
`ANALYZE / SELECT_MODE / VIEW_PLAN / DIY_DESIGN / IMAGE_GEN / PLAN_CONFIRM / SHOP_RECOMMEND / ORDER_CONFIRM / DONE`

---

## 四、结构化 UI 协议

所有 `/chat` 响应统一格式：

```json
{
  "user_id": "u_1001",
  "reply": "自然语言回复",
  "ui": "text | dialog_options | plan_card | shop_card | order_card | pay_jump | image_task",
  "data": { "...": "按 ui 类型定义的字段" },
  "tool_calls": [{"name": "...", "arguments": {}, "result": "...", "status": "ok|error"}],
  "session_id": "..."
}
```

| ui | data 字段 |
|----|-----------|
| `text` | 无额外字段（生图异步时可带 `task_id/poll`） |
| `dialog_options` | `options: [{label, value}]` |
| `plan_card` | `plans: [...]`（含 `label: Premium/Limited/New` 角标） |
| `shop_card` | `shops: [...]` |
| `order_card` | `order_id, items, total_price, plan_type` |
| `pay_jump` | `order_id, page_path, params` |
| `image_task` | `task_id, poll, result_url?` |

---

## 五、主要接口

| 接口 | 说明 |
|---|---|
| `POST /chat` | 对话主接口（ReAct + skill 编排；限流 30 次/min/IP） |
| `GET /tasks/{task_id}` | 生图任务轮询 |
| `POST /image/generate` | 直连生图入口 |
| `GET /conversations` 系列 | 多会话 CRUD + 历史回放 |
| `POST /auth/phone-code` | 手机验证码（限流 3 次/min/手机号） |
| `POST /auth/phone-login` | 手机号一键登录/注册（限流 10 次/min/手机号） |
| `POST /auth/wx-login` / `wx-bind` | 微信小程序登录 / 绑定 |
| `POST /auth/register` / `login` | 账号密码（限流 120 次/min/IP） |
| `/plans` `/shops` 系列 | 商品目录 / 店铺（支持 `lat/lng` 真实距离排序） |
| `/cart` `/orders` `/pay` 系列 | 电商闭环（**下单价格以目录为准，防篡改**） |
| `/coupons` `/coupon-offers` `/points` | 券 / 领券中心 / 积分 |
| `/merchant/*` `/admin/*` | 商家工作台 / 管理后台（角色鉴权） |
| `GET /health` `GET /metrics` | 健康检查 / 运行指标 |

统一错误返回：`{"code": 400, "message": "人类可读错误说明"}`。

---

## 六、工具与技能

| 工具 | 说明 |
|---|---|
| `search_plans(keyword, requirement?)` | 搜索预设方案（含需求软过滤；**个人已验证 DIY 方案优先**） |
| `get_plan_detail(plan_id)` | 方案详情 |
| `retrieve_knowledge(domain, query)` | 知识库 RAG（flower/style/scene/pairing/budget/packaging/proven） |
| `generate_diy_plan(requirements)` | 知识库驱动结构化 DIY 设计（含插花步骤/养护/贺卡/预算明细） |
| `generate_effect_image(plan)` | 异步生图（安全闸门：需用户确认） |
| `search_shops(plan)` | 按距离/价格/评价推荐店铺（结合定位） |
| `revise_diy_plan(plan, feedback)` | 反馈迭代（version+1） |
| `save_memory(key, value)` | 长期偏好 |
| `create_order(shop_id, plan_id, plan_type)` | 下单（DIY 成交自动升级资产库） |
| `respond_to_user(reply, ui, data, stage)` | 终结工具 |

**DIY 方案资产库**（`storage/diy.py`）：
- 用户确认方案 → `confirmed` 入库（`user_id + 内容指纹` 去重，不重复落库）
- 成交（create_order 以 diy 落单）→ `status=ordered` + `order_count+1`
- `search_diy_plans` 个人复用（按需求软过滤、按成交数优先）
- `list_proven_plans` 平台学习素材（供知识库 proven 域检索）

---

## 七、记忆管理

- **短期**：`sessions` / `messages` 表持久化全部历史（含 ui/data，前端可回放卡片）；每次请求载入最近 `N=20` 条。
- **长期**：`memories(user_id, key, value)` KV 表，模型调用 `save_memory` 落库。

---

## 八、安全设计

- **订单价格防篡改**：`POST /orders` 一律按目录 `repo.get_plan` 服务端取价，客户端传价无效；方案不存在 → 400。
- **接口限流**（内存滑动窗口，`config.rate_limit_*` 可调可关）：
  `/chat` 30/min/IP · `/auth/*` 120/min/IP · `/auth/phone-code` 3/min/手机号 · `/auth/phone-login` 10/min/手机号
- **鉴权**：JWT Bearer + 角色校验（admin/merchant 严格解析，不受 dev 开关影响）；`AUTH_REQUIRED=true` 时全站强制。
- **密码**：pbkdf2(SHA256) + 随机盐 + 恒定时间比较；明文永不落库。
- **验证码**：dev 固定码 `123456`；`sms_provider=real` 留接入通道。
- **生图 SSRF 防护**：host 白名单 + 私网 IP 校验；`/generated` 目录穿越防护。
- **日志**：不打印密钥。

---

## 九、配置

`config.py` 集中全部配置（pydantic-settings，读 `.env`）。关键项：
`LLM_API_KEY`（必填，live-only）、`IMAGE_PROVIDER`（mock/dashscope/api2img/zhipu）、
`WECHAT_APPID/SECRET`、`JWT_SECRET`、`AUTH_REQUIRED`、`DATA_SOURCE`（mock/remote）、
`PAYMENT_PROVIDER`（sandbox/wechat/alipay）、`RATE_LIMIT_*`。

---

## 十、部署

```bash
cp .env.example .env   # 填 LLM_API_KEY 等
uvicorn api:app --host 0.0.0.0 --port 8000
# 或 Docker
docker compose up -d --build
```

- 生产必须 HTTPS + 备案域名；`AUTH_REQUIRED=true` + 自设 `JWT_SECRET`。
- 限流/验证码为进程内存态：多 worker 部署需换 Redis（接口不变）。

---

## 十一、运行与验收

**本地调试 CLI**：
```bash
python cli.py design "母亲节给妈妈买束花，预算两三百"
python cli.py knowledge -d pairing -q "看望生病住院的朋友"
python cli.py revise -p plan.json -f "便宜点"
```

**验收标准**：
1. `pytest` 全绿（当前 **210 passed**，含限流/价格防篡改/DIY 资产库/鉴权/权限/订单/支付/RAG/管理后台）。
2. `POST /chat` 完整走通：设计 → 生图 → 店铺推荐 → 下单 → `pay_jump`。
3. 手机号登录（dev 验证码 `123456`）与微信登录可用。
4. `npm run build`（H5）通过。

---

## 十二、H5 前端

React + Vite + Tailwind 移动端（`H5/`），设计规范 `maison-flora-design-prompt.md`：
象牙白 + 香槟金 + 墨黑、Cormorant 衬线标题、2-4px 近直角、无投影、跳舞兰品牌。
页面：首页（定位/当季臻选/合作花店/吸底结算栏）、分类、店铺详情（美团式菜单）、
购物车、Agent 对话、我的（登录/订单/收藏/券/地址）、商家/管理后台。

---

*跳舞兰 · Atelier de Fleurs · 轻奢花艺 · 2026*
