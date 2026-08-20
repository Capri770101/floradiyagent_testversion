# 数据库分域架构基线（Database Domain Architecture）

> 状态：✅ 已拍板（2026-08-20）。本文档是 `MULTI_DOMAIN_TASK_SPEC.md` 的数据库专项基线，**执行任何数据库相关改造前必须先 Read 本文 + Grep 确认目标表/字段/函数是否已存在**（任务书纪律）。
>
> 核心结论：**单库（agent_service.db）+ 逻辑分域 + RBAC 隔离，物理不分库**。前端三独立域名共享同一后端、同一业务库；隔离靠鉴权层，不靠物理分库。

---

## 0. 总原则

1. **单库是共享真相源**：业务数据全在 `data/agent_service.db`（`config.py` → `settings.db_path`），全项目唯一连接入口 `storage/db.py:get_conn()`。三前端域名（C端/商家/管理）通过 CORS 调同一后端、读同一库。
2. **物理不分库**：不按"角色"拆成三库（否则订单链路 `customer↔merchant↔admin` 同一笔数据要在三库间同步，陷入分布式一致性地狱）。淘宝/美团/抖音小店同理——多端分域名、核心单库（或按业务域强一致分库，绝非按角色）。
3. **隔离靠 RBAC（应用层）**：
   - C 端用户：只能操作 `user_id = 自己` 的数据（`resolve_uid` + 归属校验）。
   - 商家端：只能操作 `shop_id = 自己店铺` 的数据（`_require_merchant` + shop 归属）。
   - 管理端：可调取全部 + 编辑权（`_require_admin`）。
4. **智能体私有域独立**：Agent 原生训练/知识库/记忆不进业务库，业务库访问须授权调用（见 §4）。

---

## 1. 四域划分（逻辑归属，非物理分库）

### 域 A：用户域（C 端，相对独立）
| 表 | 角色归属 | 隔离方式 |
|----|---------|---------|
| `users`(`role='user'`) | 顾客账号 | `WHERE role='user'` |
| `addresses` / `favorites` | 个人资料 | `user_id = 自己` |
| `cart_items` | 购物车 | `user_id = 自己`（已补 P0 归属校验） |
| `orders` / `order_items` / `payments` / `order_logistics` | 订单与购买记录 | `user_id = 自己` |
| `aftersales` / `reviews` | 售后/评价 | `user_id = 自己` |
| `sessions`（Agent 对话记录） | 个人会话 | `user_id = 自己` |
| `user_points` / `point_records` / `coupons` / `coupon_offers` | 积分/优惠券 | `user_id = 自己` |

> 木木定义："普通用户相对独立，仅含基础信息、购物车、订单、Agent 对话、购买记录、地址等个人数据。" ✅ 现状齐备，逻辑上即 `WHERE role='user'`。

### 域 B：商家域（店铺作单位存储）
| 表 | 角色归属 | 隔离方式 |
|----|---------|---------|
| `users`(`role='merchant'`) | 商家账号 | `WHERE role='merchant'` |
| `merchant_shops`（桥接） | 商家↔店铺（支持一商家多店） | `user_id = 自己` |
| `shops`（含 `sales` 月售） | 店铺单位存储 | `shop_id = 自己店铺` |
| `shop_*` / `shop_plans` / `shop_profiles` / `shop_styles` / `shop_scenes` | 店铺装修/商品 | `shop_id = 自己店铺` |
| `plans`（含 `sold` 已售） | 店内商品 | 经 `shop_plans` 归属店铺 |
| `shop_chats` / `chat_messages` | 客户 IM 沟通 | `shop_id = 自己店铺` |
| `merchant_applications` | 入驻申请 | `user_id = 自己` |

> 木木定义："商家个人信息 + 该账号对应各店铺信息（含商品销量等），店铺作单位存储。" ✅ `merchant_shops` 桥接表已支持"一商家多店"；若将来简化为"一商家一店"，仅前端/逻辑约束，物理结构不变。

### 域 C：管理域（全量 + 编辑权）
- 调取域 A + 域 B **全部数据** + 编辑权。
- 独有：`operations_config`（运营配置下发，见 §5 轻档排版）。
- 治理能力（现成）：`reviews.status='hidden'`（下架评价）、`shop_plans.status='on/off'`（开关商品）、`users.status='banned'`（封禁账号）、`operations_config` 下发全局配置。
- 举报治理（阶段5）：`reports`（`target_type ∈ {plan,shop,review}`，`status ∈ {pending,passed,rejected,banned}`）——C 端举报 → admin 处理；`banned/passed` 联动下架目标（商品/店铺置 off、评价置 hidden）。
> 木木定义："管理员调取所有信息并有编辑权，同时应有对 C 端的一些排版编辑能力。" 排版能力按**轻档**实现（§5）。

### 域 D：智能体私有域（独立，不共享业务库）
- 原生训练参数（代码/配置）
- 知识库 `knowledge/`（文件，TF-IDF 检索 `store.py`）
- 长期记忆 `agent/data/agent_memory.db`（独立库文件，与 `agent_service.db` 物理分离；随智能体收拢进 `agent/`）
- 业务库访问 = **授权调用**（见 §4），默认无权直连。

---

## 2. `users` 表：三角色同表（关键决策）

- **同表不分表**：`users.role ∈ {user, merchant, admin}`，外加 `status ∈ {active, banned}`（`storage/db.py`）。
- **手机号全局唯一（木木点1 硬约束）**：
  - 商家独立注册后，该手机号**不能再注册/登录用户端**，反之亦然。
  - 实现：`users.phone` 加唯一索引兜底 + `security.register_user` / `phone_login_user` 跨角色校验（注册商家时查该手机号是否已被任意 `users` 行占用）。
  - **必须同表**：物理分表会破坏"跨角色查同一手机号"的全局唯一校验。
- **商家独立注册 ≠ 物理分表**：只是 `role` 从 `user` 升 `merchant`（入驻审核通过 `set_user_role`），账号体系共享。

---

## 3. 销量统计（正式上线版，木木拍板②）

**现状（待改）**：`plans.sold`（`storage/db.py:72`）、`shops.sales`（`storage/db.py:126`）字段已存在，注释明写"种子演示值，正式上线由订单统计"。

**方案：实时 + 幂等 + 定时兜底**

1. **主 · 实时更新**：在 `storage/commerce.mark_order_paid`（`storage/commerce.py:1315`，支付成功唯一可信钩子）内，订单 `pending→paid` 时遍历 `order_items`，对每个 `plan_id` / 对应 `shop_id` 执行：
   ```sql
   UPDATE plans SET sold = sold + ? WHERE id = ?;
   UPDATE shops SET sales = sales + ? WHERE id = ?;
   ```
   - **幂等天然保证**：`mark_order_paid` 已 `if row["paid"]: return True`，重复回调不会重复计数。
   - 落点正确：该函数由 `api.pay_notify` 验签后调用，**绝不被前端直接触发**，避免伪造计数。
2. **备 · 定时兜底**：新增定时任务（建议每日凌晨），全量重算 `plans.sold = (SELECT SUM(qty) FROM order_items oi JOIN orders o ON oi.order_id=o.order_id WHERE oi.plan_id=plans.id AND o.paid=1)`、`shops.sales` 同理。用于修复异常漏算、可随时重算。
3. **上线动作**：清空 `plans.sold` / `shops.sales` 种子演示值，由统计逻辑填充（符合红线①"上线可清空重灌"）。

> 冗余字段保留（不每次查询 JOIN 算），换取列表页高性能；靠上面的实时+定时双写保持准确。

---

## 4. 智能体授权调用约束（木木拍板③，重要）

**原则**：LLM/tool **禁止**直接 `get_conn().execute("INSERT/UPDATE/DELETE ...")` 裸写业务库。所有 Agent 触达业务库的 action 必须映射到 `storage.*` 受控 service 函数（受控 tool → service → DB），防止 LLM 越权/注入、统一价格与权限安全。

**现状违规**：`skills/skill_order.py:79-93` 直接：
```python
with transaction() as c:
    c.execute("INSERT INTO orders(order_id, user_id, ...) VALUES (...)", (...))
```
违反授权调用原则，且未复用现有价格安全逻辑。

**改造指引**（agent 执行）：
1. `skill_order.create_order` 改为调用 **`storage.commerce.create_order`**（`storage/commerce.py:896`）——该 service 已做：服务端按目录取价（覆盖客户端价，防篡改）、自动抵扣最优券、落库、移除购物车。
2. tool 层只负责：解析 `shop_id` / `plan_id` / `plan_type` 占位符、组装 `items`、调用 service、处理 DIY 升级（`mark_diy_plan_ordered`）、返回 `pay_jump`。
3. 若 `create_order` service 暂不支持 `plan_type='diy'` 或 `shop_id` 透传，优先**扩展 service**（而非 tool 自己写 SQL）。
4. **通用纪律**：新增任何触达业务库的 tool，不得出现 `get_conn().execute("INSERT/UPDATE/DELETE")`；统一经 `storage.*`。

> 收益：① 灭 LLM 直写 SQL 的越权/注入面；② 复用 `create_order` 已落地的价格安全（review P0）；③ 审计与权限集中。

---

## 5. 管理端排版编辑能力（轻档，木木拍板①）

- **决策**：轻档 = 复用现有 `operations_config`（`storage/db.py:336`），**不加页面级排版表**。
- 现有 key 集（JSON 值）：`delivery_options` | `shipping_fee` | `coupon_rules` | `faqs` | `announcements`。前端经 `publicConfig()` 拉取，灭写死（呼应红线②）。
- **未来若需首页模块编排/显隐/banner 拖拽**，再扩 `page_layouts` 表（当前**不需要**，避免过度设计）。

---

## 6. 空残留清理（已完成，2026-08-20）

- ~~`floradiy.db` / `flora.db` / `app.db`~~：0 字节空文件，代码零引用，**已删除**。
- `agent_memory.db`：智能体记忆，独立保留，**已随智能体收拢移至 `agent/data/agent_memory.db`**（代码零引用，归档留存）。

---

## 7. 决策记录

| 日期 | 决策 | 说明 |
|------|------|------|
| 2026-08-19 | 三端独立域名 | C端/商家/管理 三个独立域名，同仓多 entry，后端共享 FastAPI，Bearer Token 认证 |
| 2026-08-20 ① | 管理端排版 = 轻档 | 复用 `operations_config`，不加页面级排版表 |
| 2026-08-20 ② | 销量字段 = 正式上线版 | `plans.sold`/`shops.sales` 改由订单统计（mark_order_paid 实时 + 定时兜底），废种子演示值 |
| 2026-08-20 ③ | 智能体授权调用 | 业务库禁止 LLM 裸写 SQL，`skill_order.py` 改走 `storage.commerce.create_order` |
| 2026-08-20 ④ | 智能体文件收拢 | 智能体代码/知识库/测试/专属库全部归入 `agent/`（含 `agent/data/agent_memory.db`、`agent/tests/`）；0 字节空库已删；共享主库 `agent_service.db` 留 `data/` |

---

## 8. 相关文档
- 三端域名/前端/认证/部署任务：`MULTI_DOMAIN_TASK_SPEC.md`
- 改进建议（含生产鉴权 fail-fast）：`IMPROVEMENT_PROPOSAL.md`
- 数据字段来源审计：`DATA_SOURCE_AUDIT.md`
