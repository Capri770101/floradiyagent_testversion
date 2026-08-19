// utils/pinyin.js 单元测试：分类搜索拼音匹配
import { describe, expect, it } from 'vitest'
import { pinyinIncludes, matchPinyinFields } from './pinyin'

describe('pinyinIncludes', () => {
  it('中文原文命中', () => {
    expect(pinyinIncludes('洋桔梗花束', '桔梗')).toBe(true)
  })

  it('拼音全拼命中', () => {
    expect(pinyinIncludes('洋桔梗花束', 'yang')).toBe(true)
    expect(pinyinIncludes('洋桔梗花束', 'jiegeng')).toBe(true)
  })

  it('拼音首字母命中', () => {
    expect(pinyinIncludes('洋桔梗花束', 'yjg')).toBe(true)
  })

  it('英文/数字原样命中', () => {
    expect(pinyinIncludes('rose', 'rose')).toBe(true)
  })

  it('空查询恒真', () => {
    expect(pinyinIncludes('任意', '')).toBe(true)
  })

  it('无关词不命中', () => {
    expect(pinyinIncludes('洋桔梗', 'mo')).toBe(false)
  })
})

describe('matchPinyinFields', () => {
  it('多字段任中即中（名称拼音命中）', () => {
    expect(matchPinyinFields(['洋桔梗', '清新淡雅', '日常'], 'yjg')).toBe(true)
  })

  it('多字段都不中则否', () => {
    expect(matchPinyinFields(['洋桔梗', '清新淡雅', '日常'], 'mogu')).toBe(false)
  })
})
