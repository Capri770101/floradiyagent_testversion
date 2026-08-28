// 电商接口客户端：经由 Vite 代理 /api → 后端（localhost:8080），无需改后端 CORS。
// 契约见 api.py 的 /plans /shops /cart /orders /pay 端点。
// 所有请求自动携带 Bearer 令牌（来自 auth.js），后端据此解析用户身份并隔离数据。

import { api } from './client'

// ---------------- 方案 / 店铺 ----------------

export async function listPlans(keyword = '') {
  const data = await api(`/plans?keyword=${encodeURIComponent(keyword)}`)
  return data.plans
}

export async function getPlan(id) {
  const data = await api(`/plans/${encodeURIComponent(id)}`)
  return data.plan
}

export async function listShops(location) {
  const params = new URLSearchParams()
  if (location?.lat != null && location?.lng != null) {
    params.set('lat', location.lat)
    params.set('lng', location.lng)
  }
  const q = params.toString()
  const data = await api(`/shops${q ? `?${q}` : ''}`)
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

// 轮询订单支付状态（扫码支付回调不可达场景的兜底）
export async function getPaymentStatus(orderId) {
  const data = await api(`/pay/${encodeURIComponent(orderId)}/status`)
  return data
}

// 更新订单收货信息（收货人 / 配送时间 / 备注）—— review 点名「收货人假交互」的后端真链路
export async function updateOrder(orderId, patch) {
  const data = await api(`/orders/${encodeURIComponent(orderId)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
  return data.order
}

export async function getShareCard(token) {
  const data = await api(`/share/card/${encodeURIComponent(token)}`)
  return data.card
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

export async function merchantOrders(shopId = '', status = '', keyword = '', dateFrom = '', dateTo = '') {
  const params = new URLSearchParams()
  if (shopId) params.set('shop_id', shopId)
  if (status) params.set('status', status)
  if (keyword) params.set('keyword', keyword)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
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

export async function merchantBatchToggle(shopId, planIds, on) {
  const data = await api('/merchant/plans/batch-toggle', {
    method: 'POST',
    body: JSON.stringify({ shop_id: shopId, plan_ids: planIds, on }),
  })
  return data
}

export async function merchantOrderDetail(orderId) {
  const data = await api(`/merchant/orders/${encodeURIComponent(orderId)}`)
  return data.order
}

export async function merchantAddLogistics(orderId, text) {
  const data = await api(`/merchant/orders/${encodeURIComponent(orderId)}/logistics`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
  return data.order
}

export async function merchantReviews(shopId = '') {
  const q = shopId ? `?shop_id=${encodeURIComponent(shopId)}` : ''
  const data = await api(`/merchant/reviews${q}`)
  return data.reviews
}

// 商家端：店铺商品管理（shop_id 归属店铺）
export async function merchantPlans(shopId) {
  const data = await api(`/merchant/plans?shop_id=${encodeURIComponent(shopId)}`)
  return data.plans
}

export async function merchantCreatePlan(shopId, payload) {
  const data = await api(`/merchant/plans?shop_id=${encodeURIComponent(shopId)}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return data.plan
}

export async function merchantUpdatePlan(shopId, planId, payload) {
  const data = await api(
    `/merchant/plans/${encodeURIComponent(planId)}?shop_id=${encodeURIComponent(shopId)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
  return data.plan
}

export async function merchantTogglePlan(shopId, planId) {
  const data = await api(
    `/merchant/plans/${encodeURIComponent(planId)}/toggle?shop_id=${encodeURIComponent(shopId)}`,
    { method: 'POST' },
  )
  return data.plan
}

export async function merchantDeletePlan(shopId, planId) {
  await api(
    `/merchant/plans/${encodeURIComponent(planId)}?shop_id=${encodeURIComponent(shopId)}`,
    { method: 'DELETE' },
  )
}

// 商家端：店铺资料编辑
export async function merchantUpdateShop(shopId, payload) {
  const data = await api(`/merchant/shop/${encodeURIComponent(shopId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return data.shop
}

// 商家上传图片（商品图/店铺图/封面/Logo），返回 { url: "/uploads/mxxx.jpg" }
export async function merchantUpload(file) {
  const fd = new FormData()
  fd.append('file', file)
  const data = await api('/merchant/upload', {
    method: 'POST',
    body: fd,
  })
  return data.url
}

// 商家端：商品分类管理（店铺装修·分类管理）
export async function merchantCategories() {
  const data = await api('/merchant/categories')
  return data.categories
}

export async function merchantCreateCategory(name) {
  const data = await api('/merchant/categories', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
  return data.category
}

export async function merchantRenameCategory(catId, name) {
  const data = await api(`/merchant/categories/${encodeURIComponent(catId)}`, {
    method: 'PUT',
    body: JSON.stringify({ name }),
  })
  return data.category
}

export async function merchantDeleteCategory(catId) {
  await api(`/merchant/categories/${encodeURIComponent(catId)}`, { method: 'DELETE' })
}

// ---------------- 商家-顾客会话（商家中心新增） ----------------

export async function merchantChats() {
  const data = await api('/merchant/chats')
  return data.chats
}

export async function merchantChatMessages(chatId) {
  const data = await api(`/merchant/chats/${encodeURIComponent(chatId)}/messages`)
  return data
}

export async function merchantSendChatMessage(chatId, content) {
  const data = await api(`/merchant/chats/${encodeURIComponent(chatId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
  return data.message
}

export async function merchantChatWithUser(userId, shopId) {
  const data = await api('/merchant/chats/with-user', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, shop_id: shopId }),
  })
  return data
}

export async function merchantReplyReview(reviewId, reply) {
  const data = await api(`/merchant/reviews/${encodeURIComponent(reviewId)}/reply`, {
    method: 'POST',
    body: JSON.stringify({ reply }),
  })
  return data.review
}

// 顾客侧：与店铺的会话（取或建）
export async function userChatWithShop(shopId) {
  const data = await api(`/chats/shop/${encodeURIComponent(shopId)}`)
  return data
}

// 顾客侧：与各商家的历史会话列表（消息中心展示用）
export async function listUserChats() {
  const data = await api('/chats')
  return data.chats
}

// ---------------- 售后（M4，用户侧） ----------------

export async function orderAftersale(orderId, payload) {
  const data = await api(`/orders/${encodeURIComponent(orderId)}/aftersale`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return data.aftersale
}

export async function myAftersales() {
  const data = await api('/me/aftersales')
  return data.aftersales
}

// ---------------- 运营配置（M7/M9：配送时段/FAQ/公告 后端下发） ----------------

export async function publicConfig() {
  return api('/config')
}

// ---------------- 商家入驻（M5，用户侧） ----------------

export async function merchantApply(payload) {
  const data = await api('/merchant/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return data.application
}

export async function myMerchantApplication() {
  const data = await api('/me/merchant-application')
  return data.applications
}

export async function userChatMessages(chatId) {
  const data = await api(`/chats/${encodeURIComponent(chatId)}/messages`)
  return data
}

export async function userSendChatMessage(chatId, content) {
  const data = await api(`/chats/${encodeURIComponent(chatId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
  return data.message
}


// 内容举报（阶段5）：商品/店铺/评价共用
export async function submitReport(payload) {
  return api('/reports', { method: 'POST', body: JSON.stringify(payload) })
}
