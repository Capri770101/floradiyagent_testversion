// 订单状态徽章共享元数据（Orders / Profile / Merchant / Logistics 同源，避免各页写死配色）。
export const STATUS_META = {
  created: { label: '待付款', cls: 'bg-orange-50 text-orange-600' },
  pending_payment: { label: '待付款', cls: 'bg-orange-50 text-orange-600' },
  paid: { label: '待发货', cls: 'bg-amber-50 text-amber-600' },
  shipped: { label: '配送中', cls: 'bg-blue-50 text-blue-600' },
  done: { label: '已完成', cls: 'bg-green-50 text-green-600' },
  canceled: { label: '已取消', cls: 'bg-line/40 text-sub' },
}

export function statusMeta(status) {
  return STATUS_META[status] || { label: status, cls: 'bg-line/40 text-sub' }
}

// 商家接单/拒单状态：综合 status + merchant_status 给出 C 端用户可感知的标签。
// 返回 { label, cls } 或 null（无商家确认语义时用 statusMeta 兜底）。
export function merchantConfirmMeta(order) {
  if (!order) return null
  const s = order.status
  const ms = order.merchant_status || ''
  if (s === 'paid' && ms === '') {
    return { label: '待商家确认', cls: 'bg-amber-50 text-amber-600' }
  }
  if (s === 'paid' && ms === 'accepted') {
    return { label: '商家已接单', cls: 'bg-blue-50 text-blue-600' }
  }
  if (s === 'canceled' && ms === 'rejected') {
    return { label: '商家拒单·已退款', cls: 'bg-red-50 text-red-600' }
  }
  return null
}