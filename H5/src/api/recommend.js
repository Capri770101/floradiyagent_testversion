// 个性化推荐客户端（模块三）：全部来自后端 /recommend/*，前端不写死推荐列表。
// 定位可选（getLocation() 传 lat/lng），后端无定位时自动降级热度推荐。

import { api } from './client'

function qs(params) {
  const parts = []
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') parts.push(`${k}=${encodeURIComponent(v)}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

// 猜你喜欢 / 同风格方案：GET /recommend/plans?lat=&lng=&limit=&style=
export async function recommendPlans({ lat, lng, limit = 6, style } = {}) {
  const data = await api(
    `/recommend/plans${qs({ lat, lng, limit, style })}`,
  )
  return data.items || []
}

// 附近同类店铺：GET /recommend/shops?lat=&lng=&limit=&shop_id=（排除自身）
export async function recommendShops({ lat, lng, limit = 6, shopId } = {}) {
  const data = await api(
    `/recommend/shops${qs({ lat, lng, limit, shop_id: shopId })}`,
  )
  return data.items || []
}

// 当季臻选：GET /recommend/signature?lat=&lng=&limit=（角标气质 + 热度 + 距离策展，返回含 dist_km）
export async function recommendSignature({ lat, lng, limit = 3 } = {}) {
  const data = await api(
    `/recommend/signature${qs({ lat, lng, limit })}`,
  )
  return data.items || []
}
