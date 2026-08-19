// 拼音搜索工具：为方案/店铺等中文文本提供拼音匹配。
// 使用 pinyin-pro 把中文转成拼音全拼 + 首字母，支持：
//   - 中文输入：命中原文
//   - 拼音全拼（如 "yang"）：命中 pinyin 全拼
//   - 拼音首字母（如 "ygj"）：命中 pinyinInitials 首字母
//   - 英文/数字：原样命中

import { pinyin } from 'pinyin-pro'

// 把一段文本转成可检索的拼音索引。
// 返回 { full: 全拼(小写,无空格), initials: 首字母(小写) }；无中文时返回空。
function buildPinyinIndex(text) {
  if (!text) return { full: '', initials: '' }
  const p = pinyin(text, { toneType: 'none', type: 'array' })
  const full = p.join('').toLowerCase()
  const initials = p
    .map((s) => (s ? s[0] : ''))
    .join('')
    .toLowerCase()
  return { full, initials }
}

// 判断 query 是否命中 target（含其拼音全拼/首字母）。
// q：用户输入，已 trim 并 toLowerCase。
export function pinyinIncludes(target, q) {
  if (!q) return true
  const raw = String(target || '').toLowerCase()
  if (raw.includes(q)) return true
  // 纯中文查询不需要拼音兜底（直接原文匹配即可）；但也可能命中拼音（如输入 "mo" 想搜 "茉莉"）
  const { full, initials } = buildPinyinIndex(raw)
  if (full && full.includes(q)) return true
  if (initials && initials.includes(q)) return true
  return false
}

// 组合多字段（name + desc + tags）的拼音匹配。
export function matchPinyinFields(fields, q) {
  if (!q) return true
  return fields.some((f) => pinyinIncludes(f, q))
}
