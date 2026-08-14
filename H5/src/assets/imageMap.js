// 图片占位符 → 真实图片路径映射（单一信息源）。
//
// 约定：所有真实图片请放入 H5/public/images/...（Vite 会以 /images/... 对外提供，
// 无需改代码、无需配置）。文件不存在时 SmartImage 自动回退到色块，不影响线上运行。
// 替换图片 = 把图片按下方 path 放进对应目录即可，前端零改动。
//
// 推荐尺寸见 IMAGES.md（项目 H5 目录）。

export const IMAGE_BASE = '/images'

// 固定占位符（每个页面/卡片顶部的「大图」），与 tokens.PLACEHOLDER 的色值一一对应。
export const imageMap = {
  home_banner:       { path: '/images/home/banner.jpg',       color: '#F2E2DB', alt: '首页横幅',    size: '690×300' },
  home_rec_1:        { path: '/images/home/rec-1.jpg',        color: '#E9C3C9', alt: '推荐花束',    size: '200×200' },
  home_rec_2:        { path: '/images/home/rec-2.jpg',        color: '#E9B7C4', alt: '推荐花束',    size: '200×200' },
  home_rec_3:        { path: '/images/home/rec-3.jpg',        color: '#F0C58B', alt: '推荐花束',    size: '200×200' },
  agent_plan:        { path: '/images/plans/agent-plan.jpg',  color: '#E8BFC8', alt: '方案效果图',  size: '224×208' },
  diy_main:          { path: '/images/diy/main.jpg',          color: '#E5C8C5', alt: 'DIY 主图',    size: '360×280' },
  shop_cover:        { path: '/images/shops/cover.jpg',       color: '#B9A18D', alt: '店铺封面',    size: '750×340' },
  shop_logo:         { path: '/images/shops/logo.jpg',       color: '#A98B72', alt: '店铺 Logo',   size: '120×120' },
  avatar:            { path: '/images/user/avatar.jpg',       color: '#E8C8CC', alt: '用户头像',    size: '112×112' },
  category_feature_1:{ path: '/images/category/feature-1.jpg', color: '#E8BFC8', alt: '分类精选',   size: '200×200' },
  category_feature_2:{ path: '/images/category/feature-2.jpg', color: '#EFC78D', alt: '分类精选',   size: '200×200' },
}

// 动态按 id 拼路径（用于列表里的每件商品/店铺）——id 即后端 plan_id / shop_id。
export function itemImagePath(domain, id) {
  if (!id) return null
  return `${IMAGE_BASE}/${domain}/${encodeURIComponent(id)}.jpg`
}
