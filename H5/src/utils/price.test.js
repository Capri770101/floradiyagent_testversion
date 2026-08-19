// utils/price.js 单元测试：金额计算单一数据源（运费由调用方传入，不写死）
import { describe, expect, it } from 'vitest'
import { calcPayable } from './price'

describe('calcPayable', () => {
  it('商品金额 + 配送费（运费由调用方传入）', () => {
    expect(calcPayable(199, 0, 5)).toBe(204)
  })

  it('扣除优惠券', () => {
    expect(calcPayable(199, 10, 5)).toBe(194)
  })

  it('未传运费时仅算商品-优惠', () => {
    expect(calcPayable(199, 0)).toBe(199)
  })

  it('抵扣超过总额时下限为 0', () => {
    expect(calcPayable(5, 100, 5)).toBe(0)
  })

  it('非法输入按 0 处理（运费正常计入）', () => {
    expect(calcPayable(NaN, undefined, 5)).toBe(5)
    expect(calcPayable('abc', 'x', 5)).toBe(5)
  })
})
