# 接入真实小程序 —— 集成指南

本智能体已做成「**仅替换配置即可接入真实小程序**」的成品。你不需要改任何业务代码，只要在本项目的 `.env` 里填好下面三类真实「小程序连接数据」，后端即从小程序接收流量、并返回结构化 UI 供前端渲染。

---

## 一、三步接入（核心）

| 步骤 | 配置项 | 含义 | 不填会怎样 |
|------|--------|------|------------|
| ① 微信登录 | `WECHAT_APPID` / `WECHAT_SECRET` | 小程序后台「开发管理 → 开发设置」获取 | `/auth/wx-login` 返回 503（dev 仍可纯 `user_id` 调） |
| ② 鉴权开关 | `JWT_SECRET` + `AUTH_REQUIRED=true` | 自己生成的随机长串；开启后 `/chat` 强制 Bearer 令牌 | 留空则进程内随机密钥（仅联调）；`false` 为 dev 模式 |
| ③ 真实数据 | `DATA_SOURCE=remote` + `REMOTE_API_BASE` | 指向你的小程序后端基址 | 缺 base 自动回退 Mock，服务照常启动 |

> 支付跳转页 `PAY_PAGE_PATH` 也在此处配置（默认 `/pages/order/confirm`），随真实小程序页面路径调整。

填好 ①②③ 后，`docker compose up -d` 即是一个**对接真实小程序的成品服务**。

---

## 二、小程序侧接入流程

```
小程序                                       后端 (flora-agent-service)
  │                                                │
  │ 1. wx.login() 拿到一次性 code                   │
  │ ───────── POST /auth/wx-login {code} ────────► │
  │ ◄──────── { token, openid, expires_in } ────── │  （内部调微信 code2session 换 openid，签发 JWT）
  │                                                │
  │ 2. 本地保存 token                               │
  │                                                │
  │ 3. 每次对话：                                   │
  │    Authorization: Bearer <token>                │
  │ ───────── POST /chat {message, user_role} ───► │
  │ ◄──────── 结构化 UI 响应（见下） ───────────── │
  │                                                │
```

**`/chat` 请求示例（开启鉴权后必须带头）：**

```bash
curl -X POST http://<your-host>:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"user_id":"oABC123","message":"想给妈妈买束花，预算200","user_role":"user"}'
```

> dev 模式（`AUTH_REQUIRED=false`）下可省略 `Authorization`，直接用 `user_id` 调，方便用 `/docs` 手测。

**`/auth/wx-login` 请求示例：**

```bash
curl -X POST http://<your-host>:8000/auth/wx-login \
  -H "Content-Type: application/json" \
  -d '{"code":"081abc..."}'
# → {"token":"eyJ...","openid":"oABC123","unionid":null,"expires_in":604800,"token_type":"Bearer"}
```

---

## 三、结构化 UI 响应（前端照此渲染）

`/chat` 始终返回统一结构：

```json
{
  "user_id": "oABC123",
  "reply": "已为你筛选到几款方案～",
  "ui": "plan_card",                 // text | dialog_options | plan_card | shop_card | pay_jump
  "data": { "plans": [ ... ] },      // 不同 ui 对应不同 data 结构
  "tool_calls": [ ... ],
  "session_id": "sess_xxx",
  "stage": "view_plan"
}
```

| `ui` 值 | 含义 | `data` 关键字段 |
|---------|------|----------------|
| `text` | 纯文本回复 | `{}` 或 `task_id`/`poll`（生图轮询） |
| `dialog_options` | 选项按钮 | `options:[{label,value}]` |
| `plan_card` | 方案卡片 | `plans:[{plan_id,name,price,desc,effect_image_url,tags}]` |
| `shop_card` | 店铺卡片 | `shops:[{shop_id,name,distance_km,price_range,rating,plan_ids}]` |
| `pay_jump` | 下单/支付跳转 | `order_id`, 跳转页 `page_path` 与 `params`（**不直接调微信支付**，支付由小程序承接） |

---

## 四、真实后端接口契约（DATA_SOURCE=remote 时）

把 `REMOTE_API_BASE` 指向你的后端后，本服务会按以下约定调用（路径可用 `REMOTE_*_PATH` 覆盖）：

| 方法 & 路径 | 说明 | 期望返回（JSON） |
|-------------|------|------------------|
| `GET {base}/plans?keyword=` | 搜索方案 | `array<Plan>` |
| `GET {base}/plans/{id}` | 单方案详情 | `Plan \| {error:"not found"}` |
| `GET {base}/shops?plan_id=&lat=&lng=` | 推荐店铺 | `array<Shop>` |
| `GET {base}/shops/{id}` | 单店铺详情 | `Shop \| {error:"not found"}` |

**Plan 形状**（与 Mock 一致，前端可直接复用）：

```json
{
  "plan_id": "P001",
  "name": "康乃馨感恩花束",
  "price": 199.0,
  "desc": "11 支粉色康乃馨 + 满天星",
  "effect_image_url": "https://.../plan_P001.png",
  "merchant_name": "花漾工坊",
  "tags": ["母亲节", "康乃馨", "温馨"]
}
```

**Shop 形状：**

```json
{
  "shop_id": "S001",
  "name": "花漾工坊(盐田店)",
  "distance_km": 1.2,
  "price_range": "100-300",
  "rating": 4.8,
  "plan_ids": ["P001", "P002"]
}
```

> 只要你的后端返回上述 JSON，上层导购逻辑、状态机、UI 协议**零改动**即可工作。这也是「换配置即接入」的关键。

---

## 知识库：用真实业务数据替换通用骨架

DIY 设计能力由 `knowledge/` 下的 JSON 知识库驱动。当前是**通用花艺常识**骨架，接入真实业务时直接编辑这些 JSON 即可，无需改代码：

| 文件 | 替换为 | 关键字段 |
|------|--------|----------|
| `knowledge/flowers.json` | 你们实际可用/在售花材 | 花语、色系 `colors`、季节、价格档 `price_tier`、搭配性 `pairing_notes` |
| `knowledge/styles.json` | 你们定义的风格标准 | `typical_flowers`、`color_palette`、`packaging` |
| `knowledge/pairings.json` | 你们的设计经验规则 | `condition`（触发条件）、`recommendation`（推荐花材/搭配） |
| `knowledge/budget.json` | 你们各价位的实际配置 | `range`、`config`、`suggested_flowers` |
| `knowledge/packaging.json` | 你们提供的包装/器型 | `suitable_for`、`description` |

替换后 `design_diy_plan` 会自动用新数据生成方案；检索工具 `retrieve_knowledge` 也随之生效。若花材量很大，可后续将 `knowledge/store.py` 的轻量检索升级为向量检索（RAG），接口不变。

---

## 五、部署（Docker 一条龙）

```bash
# 1. 准备 .env（复制 .env.example 并填好①②③）
cp .env.example .env
# 2. 构建并后台启动
docker compose up -d --build
# 3. 健康检查
curl http://localhost:8000/health
# → {"status":"ok","llm_mode":"live","image_mode":"live","auth":"required","data_source":"remote","tools":7}
```

数据（SQLite + 生图落盘）持久化在挂载的 `./data` 卷，容器重建不丢。

---

## 六、开发期 vs 上线期速查

| 阶段 | LLM | 生图 | 数据源 | 鉴权 | 一句话 |
|------|-----|------|--------|------|--------|
| 本地开发 | `LLM_API_KEY=`(Mock) | `IMAGE_PROVIDER=zhipu`(免费) | `DATA_SOURCE=mock` | `AUTH_REQUIRED=false` | 零成本随便调 |
| 上线真实小程序 | 真实 key | 换付费档(如 dashscope) | `DATA_SOURCE=remote` + `REMOTE_API_BASE` | `AUTH_REQUIRED=true` + `JWT_SECRET` | 填好 ①②③ 即成品 |
