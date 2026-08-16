// utils/price.js 单元测试：金额计算单一数据源
import { describe, expect, it } from 'vitest'
import { calcPayable, SHIPPING_FEE } from './price'

describe('calcPayable', () => {
  it('商品金额 + 配送费', () => {
    expect(calcPayable(199, 0)).toBe(199 + SHIPPING_FEE)
  })

  it('扣除优惠券', () => {
    expect(calcPayable(199, 10)).toBe(199 + SHIPPING_FEE - 10)
  })

  it('抵扣超过总额时下限为 0', () => {
    expect(calcPayable(5, 100)).toBe(0)
  })

  it('非法输入按 0 处理', () => {
    expect(calcPayable(NaN, undefined)).toBe(SHIPPING_FEE)
    expect(calcPayable('abc', 'x')).toBe(SHIPPING_FEE)
  })
})
