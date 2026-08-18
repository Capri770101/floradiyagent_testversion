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