// 电商接口客户端：经由 Vite 代理 /api → 后端（localhost:8080），无需改后端 CORS。
// 契约见 api.py 的 /plans /shops /cart /orders /pay 端点。
// 所有请求自动携带 Bearer 令牌（来自 auth.js），后端据此解析用户身份并隔离数据。

import { authHeaders } from './auth'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function api(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...authHeaders(),
    ...(options.headers || {}),
  }
  // 统一超时（10s），避免弱网下请求挂死无反馈
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 10000)
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: ctrl.signal })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`后端 ${res.status}: ${text.slice(0, 200)}`)
    }
    return res.json()
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('请求超时，请稍后重试')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

// ---------------- 方案 / 店铺 ----------------

export async function listPlans(keyword = '') {
  const data = await api(`/plans?keyword=${encodeURIComponent(keyword)}`)
  return data.plans
}

export async function getPlan(id) {
  const data = await api(`/plans/${encodeURIComponent(id)}`)
  return data.plan
}

export async function listShops() {
  const data = await api('/shops')
  return data.shops
}

export async function getShop(id) {
  const data = await api(`/shops/${encodeURIComponent(id)}`)
  return data.shop
}

// ---------------- 购物车 ----------------

export async function getCart(userId) {
  const data = await api(`/cart?user_id=${encodeURIComponent(userId)}`)
  return data.items
}

export async function addCart(userId, item) {
  const data = await api('/cart', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, ...item }),
  })
  return data.item
}

export async function updateCart(itemId, patch) {
  const data = await api(`/cart/${encodeURIComponent(itemId)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  })
  return data.item
}

export async function removeCart(itemId) {
  await api(`/cart/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
}

// ---------------- 订单 / 支付 ----------------

export async function createOrder(userId, items, extra = {}) {
  const data = await api('/orders', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, items, ...extra }),
  })
  return data.order
}

export async function getOrder(orderId) {
  const data = await api(`/orders/${encodeURIComponent(orderId)}`)
  return data.order
}

export async function listOrders() {
  const data = await api('/orders')
  return data.orders
}

export async function orderAction(orderId, action) {
  const data = await api(`/orders/${encodeURIComponent(orderId)}/action`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return data.order
}

export async function listCoupons() {
  const data = await api('/coupons')
  return data.coupons
}

export async function getPoints() {
  return api('/points')
}

export async function payOrder(orderId, method = 'wechat') {
  const data = await api('/pay', {
    method: 'POST',
    body: JSON.stringify({ order_id: orderId, method }),
  })
  return data.pay
}

// 更新订单收货信息（收货人 / 配送时间 / 备注）—— review 点名「收货人假交互」的后端真链路
export async function updateOrder(orderId, patch) {
  const data = await api(`/orders/${encodeURIComponent(orderId)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
  return data.order
}

// ---------------- 收货地址 ----------------

export async function listAddresses() {
  const data = await api('/addresses')
  return data.addresses
}

export async function addAddress(payload) {
  const data = await api('/addresses', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return data.address
}

export async function updateAddress(addrId, patch) {
  const data = await api(`/addresses/${encodeURIComponent(addrId)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  })
  return data.address
}

export async function deleteAddress(addrId) {
  await api(`/addresses/${encodeURIComponent(addrId)}`, { method: 'DELETE' })
}

// ---------------- 收藏 ----------------

export async function listFavorites() {
  const data = await api('/favorites')
  return data
}

export async function addFavorite(planId) {
  await api('/favorites', {
    method: 'POST',
    body: JSON.stringify({ plan_id: planId }),
  })
}

export async function removeFavorite(planId) {
  await api(`/favorites/${encodeURIComponent(planId)}`, { method: 'DELETE' })
}

export async function favoriteStatus(planId) {
  const data = await api(`/favorites/${encodeURIComponent(planId)}/status`)
  return data.favorited
}

// ---------------- 评价 ----------------

export async function getReviews(planId) {
  const q = planId ? `?plan_id=${encodeURIComponent(planId)}` : ''
  const data = await api(`/reviews${q}`)
  return data.reviews
}

export async function postReview({ order_id, rating, content }) {
  const data = await api('/reviews', {
    method: 'POST',
    body: JSON.stringify({ order_id, rating, content }),
  })
  return data.review
}

// ---------------- 领券中心 / 积分商城 ----------------

export async function listCouponOffers() {
  const data = await api('/coupon-offers')
  return data
}

export async function claimCouponOffer(offerId) {
  const data = await api(`/coupon-offers/${encodeURIComponent(offerId)}/claim`, {
    method: 'POST',
  })
  return data.coupon
}

// ---------------- 商家端 ----------------

export async function merchantStats(shopId = '') {
  const q = shopId ? `?shop_id=${encodeURIComponent(shopId)}` : ''
  const data = await api(`/merchant/stats${q}`)
  return data
}

export async function merchantOrders(shopId = '', status = '') {
  const params = new URLSearchParams()
  if (shopId) params.set('shop_id', shopId)
  if (status) params.set('status', status)
  const q = params.toString()
  const data = await api(`/merchant/orders${q ? `?${q}` : ''}`)
  return data.orders
}

export async function merchantShip(orderId) {
  const data = await api(`/merchant/orders/${encodeURIComponent(orderId)}/ship`, {
    method: 'POST',
  })
  return data.order
}

export async function merchantReviews(shopId = '') {
  const q = shopId ? `?shop_id=${encodeURIComponent(shopId)}` : ''
  const data = await api(`/merchant/reviews${q}`)
  return data.reviews
}

// ---------------- 管理后台（方案 / 店铺 CRUD） ----------------

export async function adminListPlans() {
  const data = await api('/admin/plans')
  return data.plans
}

export async function adminListShops() {
  const data = await api('/admin/shops')
  return data.shops
}

export async function adminCreatePlan(payload) {
  const data = await api('/admin/plans', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return data.plan
}

export async function adminUpdatePlan(planId, payload) {
  const data = await api(`/admin/plans/${encodeURIComponent(planId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return data.plan
}

export async function adminDeletePlan(planId) {
  await api(`/admin/plans/${encodeURIComponent(planId)}`, { method: 'DELETE' })
}

export async function adminCreateShop(payload) {
  const data = await api('/admin/shops', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return data.shop
}

export async function adminUpdateShop(shopId, payload) {
  const data = await api(`/admin/shops/${encodeURIComponent(shopId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return data.shop
}

export async function adminDeleteShop(shopId) {
  await api(`/admin/shops/${encodeURIComponent(shopId)}`, { method: 'DELETE' })
}
