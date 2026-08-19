# 开发计划与进度

> 与 `NEW_FEATURES_TASK_SPEC.md` 对齐。已完成项标记 ✅ 并保留交接要点；未开始/进行中标记 ⬜/🔄。

## 模块一：消息通知中心（✅ 已完成）

- `storage/db.py`：`notifications` 表 + `_ALTERS` 幂等迁移。
- `storage/notify.py`：`create_notification` / `try_create`（旁路容错）/ 列表 / 未读计数 / 标记已读。
- `routers/notify.py`：列表、未读、已读（单条/批量/全部）、详情；`routers/commerce.py`（下单/支付/发货）、`routers/merchant.py`（物流）、`storage/chats.py::reply_review`（评价回复）、`routers/admin.py`（售后审核/公告）埋点。
- 前端：`H5/src/api/notify.js`、`H5/src/pages/Notifications.jsx`、`NotificationDetail.jsx`、`TabBar` 红点、`Settings.jsx` 开关占位。
- 测试：`tests/test_notifications.py`（9 用例，含越权与 try_create 容错）。
- 验收要点：业务埋点不依赖微信推送；`push_channel` 仅占位恒 inbox。

## 模块二：DIY 卡片内容扩充（✅ 已完成）

- `storage/db.py`：`diy_plans` 新增 6 列：`difficulty / est_time / shelf_life / suitable_for / caution / mood_tags`（建表 + `_ALTERS`）。
- `tools.py`：`_build_plan` 规则兜底（`_suitable_for` / `_build_caution` / `_mood_tags` 辅助函数）+ `_merge_plan` merge keys 扩展 + design_with_llm / revise_with_llm prompt 新字段 schema。
- `storage/diy.py`：`save_diy_plan` INSERT 28 列；`_row_to_plan` 还原（旧方案缺失字段不崩）。
- `scripts/seed_demo.py`：演示 DIY 方案「北欧 · 生日花束」6 新字段有值。
- 前端：`DiyPlanCard.jsx` `normalizePlan` 扩展 + 头部 occasion chip + 制作难度/预计耗时/保鲜期 + 适宜人群 + 情绪标签 + 禁忌提醒警示卡；`Notifications.jsx` 品牌色统一。
- 测试：`tests/test_diy_storage.py` / `test_diy_design.py` 各 +2；`H5/src/components/DiyPlanCard.test.jsx`（3 用例）。
- 验收要点：卡片新区块全部有真实 DB 来源；编辑面板不暴露新字段（展现增强）。

## 模块三：个性化推荐打磨（✅ 已完成，含业务闭环/体验优化轮）

- `storage/config.py`：`K_REC_WEIGHTS` + 默认权重（0.4/0.4/0.2）。
- `storage/recommend.py`：`extract_preferences`（favorites + orders.items JSON + orders.shop_id；注意 `order_items` 为遗留空表勿用）、`recommend_plans`、`recommend_shops`；`STYLE_GROUPS` 风格词表分组（北欧→简约/ins 等，style 参数/偏好画像/店铺风格命中三路归一化）。
- `routers/recommend.py`：`GET /recommend/plans`、`GET /recommend/shops`（复用 `_plan_card` / `_shop_card` 序列化）。
- 前端：`H5/src/api/recommend.js`；`Home.jsx` 猜你喜欢（横滑，带定位，卡片收藏心形动线：匿名引导登录、乐观切换、收藏后即时刷新推荐）；`Home.jsx` 当季臻选（`/recommend/signature` 策展推荐：角标气质+热度+距离，卡片带「距你 x.xkm」）；`ShopDetail.jsx` 附近同类店铺（排除自身）；`DiyDetail.jsx` 同风格方案（style 软加权）；三处推荐位共用 `H5/src/hooks/useRecommend.js`（四态 + 防竞态）。
- 首页店铺位置优先：`/shops?lat=&lng=` 按定位距离升序（无定位回退静态 distance_km），首店打「距你最近」标，实测切换定位（龙岗→绿野花艺 16.7km 居首）即时重排。
- 运营配置：`GET/PUT /admin/config` 支持 `recommend_weights`（0~1 校验、部分更新），并入公开 `GET /config`；`H5/src/admin/pages/Config.jsx` 增加距离/偏好/热度三个权重输入（保存后 C 端即时生效）。
- `Home.jsx` 数据加载拆分：购物车与定位无关 → 挂载时加载一次；定位变更只重拉店铺/精选。
- 测试：`tests/test_recommend.py`（12 用例，含风格词表分组、运营权重配置、当季臻选策展与距离决胜）。
- 验收：浏览器实测收藏动线（匿名→登录引导 / 登录→乐观切换）、admin 权重保存回显、同风格方案别名命中（北欧→P010/P007 居首）、当季臻选三卡带距离、合作花店按定位重排；`docs/FIELD_CONTRACT.md` §1.7 已同步。
- 已知坑：`seed_catalog` 热度演示值由进程级随机 `hash()` 生成 → 依赖排序断言的测试须先归一化热度数据（`_neutralize_heat`）。

## 回归基线

- 后端：`python -m pytest -q`（246 用例，连续多轮全绿；含通知/推荐 flaky 修复）。
- 前端：`npx vitest run`（13 用例）、`npx eslint src`（0 errors）、`npm run build`。
- 演示数据：`python scripts/seed_demo.py`（capri_demo 收藏 P001 作为偏好信号）。