// 由字符串种子稳定派生一个占位色（用于无真实图片时的色块渲染）。
const PALETTE = [
  '#F2E2DB', '#E8D3DE', '#DCE7DC', '#F4E2C4',
  '#E2E0F0', '#D9EAF2', '#F6D9D2', '#E5ECD9',
]

export function imgColor(seed = '') {
  let h = 0
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0
  }
  return PALETTE[h % PALETTE.length]
}

// 稳定字符串哈希（用于占位图花卉变体选择等）
export function hashStr(str = '') {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (h * 31 + str.charCodeAt(i)) >>> 0
  }
  return h
}

// 把 hex 颜色按比例向白色提亮，返回 rgb()，用于占位图渐变（文艺风：柔和不刺眼）
export function lighten(hex, amt = 0.16) {
  const h = String(hex).replace('#', '')
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h
  const n = parseInt(full, 16)
  let r = (n >> 16) & 255
  let g = (n >> 8) & 255
  let b = n & 255
  r = Math.round(r + (255 - r) * amt)
  g = Math.round(g + (255 - g) * amt)
  b = Math.round(b + (255 - b) * amt)
  return `rgb(${r}, ${g}, ${b})`
}
