# 图片占位符存储位置说明（H5）

本文件说明各页面「图片占位符」现在用的色块，以及**将来替换为真实图片时应当放在哪里**。

## 约定（重要）

- 所有真实图片统一放入 `H5/public/images/...` 目录（Vite 会以 `/images/...` 对外提供，**无需改代码、无需任何配置**）。
- 前端已接入 `SmartImage` 组件：文件不存在时自动回退到色块；**把图片按下方路径放进去，刷新即生效，前端零改动**。
- 路径单一信息源见 `H5/src/assets/imageMap.js`（固定大图）与 `itemImagePath(domain, id)`（按商品/店铺 id 动态拼路径）。

## 目录结构（已建好，先把图丢进来即可）

```
H5/public/images/
├── home/        # 首页横幅、推荐位   → banner.jpg, rec-1.jpg, rec-2.jpg, rec-3.jpg
├── plans/       # 方案/商品图（按 plan_id） → P001.jpg, DIY_xxxx.jpg ...
├── shops/       # 店铺封面/Logo     → cover.jpg, logo.jpg, S001.jpg ...
├── diy/         # DIY 方案主图      → main.jpg
├── user/        # 用户头像          → avatar.jpg
├── category/    # 分类精选          → feature-1.jpg, feature-2.jpg, <category_id>.jpg
├── cart/        # 购物车商品（同 plans/<id>.jpg）
└── orders/      # 订单商品（同 plans/<id>.jpg）
```

## 占位符清单（当前色块 → 应放图片路径）

| 页面 / 组件 | 元素 | 当前色块 | 真实图片路径 | 推荐尺寸 |
|---|---|---|---|---|
| Home 首页 | 顶部横幅 | `#F2E2DB` | `/images/home/banner.jpg` | 690×300 |
| Home 首页 | 推荐花束 ×3 | `#E9C3C9/#E9B7C4/#F0C58B` | `/images/home/rec-1.jpg` ~ `rec-3.jpg` | 200×200 |
| Home 首页 | 推荐方案卡 | 按 id 派生 | `/images/plans/<plan_id>.jpg` | 200×200 |
| Home 首页 | 热门商家 | 按 id 派生 | `/images/shops/<shop_id>.jpg` | 108×132 |
| Agent 对话 | 方案缩略图 | `#E8BFC8` | `/images/plans/<plan_id>.jpg`（DIY 用 `/images/plans/agent-plan.jpg` 兜底） | 224×208 |
| DiyPlanCard（对话内方案卡） | 方案主图 | `#E5C8C5` | `/images/diy/main.jpg` | 208×208 |
| DiyDetail DIY 详情 | 主图 | `#E5C8C5` | `/images/diy/main.jpg` | 360×280 |
| ProductDetail 商品详情 | 商品大图 | 按 id 派生 | `/images/plans/<plan_id>.jpg` | 750×750 |
| ShopDetail 店铺详情 | 店铺封面 | `#B9A18D` | `/images/shops/cover.jpg` | 750×340 |
| ShopDetail 店铺详情 | 店铺 Logo | `#A98B72` | `/images/shops/logo.jpg` | 120×120 |
| ShopDetail 店铺详情 | 店铺推荐方案 | 按 id 派生 | `/images/plans/<plan_id>.jpg` | 144×144 |
| Cart 购物车 | 商品图 | 按 id 派生 | `/images/plans/<plan_id>.jpg` | 124×124 |
| Category 分类 | 精选方案 | 按 id 派生 | `/images/category/<id>.jpg` | 120×156 |
| OrderConfirm 订单确认 | 商品图 | 按 id 派生 | `/images/plans/<plan_id>.jpg` | 124×124 |
| Profile 我的 | 头像 | `#E8C8CC` | `/images/user/avatar.jpg` | 112×112 |
| PlanCard 通用方案卡 | 缩略图 | `#E8BFC8` | `/images/plans/agent-plan.jpg` | 224×208 |

> 说明：`mock.js` 里的 `color` 字段是**数据层**占位，最终都会映射到 `/images/plans/<id>.jpg` 这一约定，运行时由后端 `plan_id` 决定具体路径；替换真实图片只需按 `plan_id` 命名放入 `plans/` 目录。

## 替换步骤

1. 把图片按上表「真实图片路径」放进 `H5/public/images/...`（建议用 `plan_id`/`shop_id` 命名，如 `plans/P001.jpg`）。
2. 重启 `npm run dev`（或重新构建）。无需改任何前端代码。
3. 若某图不想放，删除该文件即可自动回退到色块占位。

## 接入真实图源（进阶）

正式上线时，更稳妥的做法是让后端在 `repo.get_plan` 返回 `image` 字段（绝对/相对 URL），前端 `SmartImage` 直接吃 `src`。当前后端 `_plan_card` 固定返回 `image: None`，目录图片为本地托管的过渡方案。
