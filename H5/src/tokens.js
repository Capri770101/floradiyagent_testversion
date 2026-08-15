// 设计令牌 —— Maison Flora 轻奢规范（maison-flora-design-prompt.md §2/§4）
// 颜色 / 圆角 / 字号 / 占位色 全部来自规范，避免散落硬编码。

export const COLORS = {
  bg: '#FAF8F5',       // 象牙白
  white: '#FFFFFF',
  ink: '#1A1A1A',      // 墨黑
  sub: '#6B6B6B',      // 石板灰
  pink: '#B5985A',     // 香槟金（主色）
  pink2: '#F0EBE3',    // 砂色
  green: '#A0947C',    // 暖灰褐（状态）
  cream: '#C9A96A',    // 浅金
  line: '#D4CFC6',     // 石色细描边
  dark: '#1A1A1A',     // 墨黑
  gold: '#B5985A',
  goldDark: '#6B5630',
  burgundy: '#722F37',
  sand: '#F0EBE3',
  stone: '#8B8680',
}

// 图片占位色：无真实素材时使用低饱和暖调色块（Maison 风格）
export const PLACEHOLDER = {
  homeBanner: '#EFE9DE',
  homeRec: ['#E8E0D2', '#E5DCCB', '#EDE2CE'],
  agentPlan: '#E9E1D3',
  diyMain: '#EBE3D6',
  productBig: '#EAE2D4',
  shopCover: '#DED4C2',
  shopLogo: ['#CFC2A9', '#D8CCB6'],
  avatar: '#E9E1D3',
  orderItem: ['#E8E0D2', '#E9E1D3'],
  cartItem: ['#E8E0D2', '#EFE6D2'],
  guessLike: ['#EDE2CE', '#E8E0D2'],
  catFeature: ['#E9E1D3', '#EDE2CE'],
}

// 画布基准（移动端 390 × 844）
export const CANVAS = { w: 390, h: 844 }

// 价格统一强调色（香槟金）
export const PRICE_COLOR = COLORS.pink
