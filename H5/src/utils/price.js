// 金额计算：商品金额 + 配送费 - 优惠券抵扣（下限 0）。
// 配送费由后端运营配置下发（publicConfig().shipping_fee），前端不再写死常量，
// 避免「前端各算一遍 +20」与后端真实运费（如 5）发散（红线2：单一数据源）。
// Pay 页与 OrderConfirm 页统一引用本函数，并把后端下发的 shippingFee 传入，保证两处永远一致。
// 优惠券抵扣以后端落库的 order.discount 为准（下单时自动抵扣最优券），不再前端硬编码 -10。

/**
 * 计算应付总额。
 * @param {number} goodsTotal 商品金额
 * @param {number} discount 优惠券抵扣（后端 order.discount）
 * @param {number} shippingFee 配送费（后端 publicConfig().shipping_fee）
 * @returns {number}
 */
export function calcPayable(goodsTotal = 0, discount = 0, shippingFee = 0) {
  const base = Number(goodsTotal) || 0
  const off = Number(discount) || 0
  const ship = Number(shippingFee) || 0
  return Math.max(0, base + ship - off)
}

/**
 * 金额显示：统一保留两位小数（¥12.30）。
 * 全局唯一格式化入口，各页面不再各自定义 fmtMoney。
 */
export function fmtMoney(v) {
  return `¥${Number(v || 0).toFixed(2)}`
}

/**
 * 金额显示（千分位分组）：¥1,234.00，用于后台 GMV/流水等大额统计。
 */
export function fmtMoneyGrouped(v) {
  return `¥${Number(v || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}
