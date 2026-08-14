// 金额计算单一数据源：配送费 / 优惠券与后端（sandbox 演示）保持一致，
// 杜绝 review 点名的「前后端各算一遍 +20-10」发散问题。
// Pay 页与 OrderConfirm 页统一引用本文件，保证两处永远一致。

export const SHIPPING_FEE = 20
export const COUPON_DISCOUNT = 10

/** 计算应付总额 = 商品金额 + 配送费 - 优惠券（下限 0）。 */
export function calcPayable(goodsTotal = 0) {
  const base = Number(goodsTotal) || 0
  return Math.max(0, base + SHIPPING_FEE - COUPON_DISCOUNT)
}
