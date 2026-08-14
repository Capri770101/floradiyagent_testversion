// 设计令牌 —— 严格对齐 DESIGN_SPEC_H5.md §1
// 颜色 / 圆角 / 字号 / 占位色 全部来自规范，避免散落硬编码。

export const COLORS = {
  bg: '#F8F6F2',
  white: '#FFFFFF',
  ink: '#333333',
  sub: '#999999',
  pink: '#E88AA1',
  pink2: '#F6DDE3',
  green: '#A7C5AE',
  cream: '#F7C99C',
  line: '#E8E2DC',
  dark: '#343434',
}

// §1.1 图片占位色：无真实素材时使用纯色块（非外部 URL，符合前端规范）
export const PLACEHOLDER = {
  homeBanner: '#F2E2DB',
  homeRec: ['#E9C3C9', '#E9B7C4', '#F0C58B'],
  agentPlan: '#E8BFC8',
  diyMain: '#E5C8C5',
  productBig: '#E4C3C6',
  shopCover: '#B9A18D',
  shopLogo: ['#A98B72', '#BBAA98'],
  avatar: '#E8C8CC',
  orderItem: ['#E7C0C7', '#E8C0C6'],
  cartItem: ['#E8C0C6', '#EFC78D'],
  guessLike: ['#F0C58B', '#E9C6CB'],
  catFeature: ['#E8BFC8', '#EFC78D'],
}

// 画布基准（移动端 375 × 812）
export const CANVAS = { w: 375, h: 812 }

// 价格统一强调色
export const PRICE_COLOR = COLORS.pink
