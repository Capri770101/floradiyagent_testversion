// 商家端 API 封装：独立 fetch 实例 + Bearer，401/403 统一跳登录。
// 与 C 端（floradiy_token）/ 管理后台（floradiy_admin_token）令牌隔离：
// 三端各自登录互不干扰（三端独立域名架构，JWT Bearer 按 origin 隔离）。
// 商家认证走 /auth/merchant-login / /auth/merchant-register（role=merchant 才可进入）。
const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const TOKEN_KEY = 'floradiy_merchant_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function request(path, { method = 'GET', body, params } = {}) {
  let url = `${API_BASE}${path}`
  if (params) {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== undefined && v !== null) qs.set(k, v)
    })
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  const headers = isForm ? {} : { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined && !isForm ? JSON.stringify(body) : body,
  })
  if (res.status === 401 || res.status === 403) {
    window.dispatchEvent(new window.CustomEvent('merchant:auth-fail', { detail: res.status }))
    throw new Error(res.status === 401 ? '登录已失效，请重新登录' : '无权访问该操作')
  }
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const data = await res.json()
      if (data.message || data.detail) msg = String(data.message || data.detail)
    } catch (e) {
      /* 非 JSON 响应 */
    }
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  get: (p, params) => request(p, { params }),
  post: (p, body) => request(p, { method: 'POST', body }),
  put: (p, body) => request(p, { method: 'PUT', body }),
  del: (p) => request(p, { method: 'DELETE' }),
}

// ---------------- 认证 ----------------

export async function merchantLogin(phone, password) {
  const data = await request('/auth/merchant-login', {
    method: 'POST',
    body: { username: phone, password },
  })
  setToken(data.token)
  return data
}

export async function merchantRegister(phone, password, shopName) {
  const data = await request('/auth/merchant-register', {
    method: 'POST',
    body: { phone, password, shop_name: shopName || undefined },
  })
  setToken(data.token)
  return data
}

export async function fetchProfile() {
  const data = await request('/auth/me')
  return data.user
}

// ---------------- 商家业务 ----------------

export async function merchantStats(shopId = '') {
  const data = await request(`/merchant/stats${shopId ? `?shop_id=${encodeURIComponent(shopId)}` : ''}`)
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
  const data = await request(`/merchant/orders${q ? `?${q}` : ''}`)
  return data.orders
}

export async function merchantShip(orderId) {
  const data = await request(`/merchant/orders/${encodeURIComponent(orderId)}/ship`, { method: 'POST' })
  return data.order
}

export async function merchantAcceptOrder(orderId) {
  const data = await request(`/merchant/orders/${encodeURIComponent(orderId)}/accept`, { method: 'POST' })
  return data.order
}

export async function merchantRejectOrder(orderId, reason = '') {
  const data = await request(`/merchant/orders/${encodeURIComponent(orderId)}/reject`, { method: 'POST', body: JSON.stringify({ reason }) })
  return data.order
}

export async function merchantOrderDetail(orderId) {
  const data = await request(`/merchant/orders/${encodeURIComponent(orderId)}`)
  return data.order
}

export async function merchantAddLogistics(orderId, text) {
  const data = await request(`/merchant/orders/${encodeURIComponent(orderId)}/logistics`, {
    method: 'POST',
    body: { text },
  })
  return data.order
}

export async function merchantReviews(shopId = '') {
  const data = await request(`/merchant/reviews${shopId ? `?shop_id=${encodeURIComponent(shopId)}` : ''}`)
  return data.reviews
}

export async function merchantReplyReview(reviewId, reply) {
  const data = await request(`/merchant/reviews/${encodeURIComponent(reviewId)}/reply`, {
    method: 'POST',
    body: { reply },
  })
  return data.review
}

export async function merchantPlans(shopId) {
  const data = await request(`/merchant/plans?shop_id=${encodeURIComponent(shopId)}`)
  return data.plans
}

export async function merchantCreatePlan(shopId, payload) {
  const data = await request(`/merchant/plans?shop_id=${encodeURIComponent(shopId)}`, {
    method: 'POST',
    body: payload,
  })
  return data.plan
}

export async function merchantUpdatePlan(shopId, planId, payload) {
  const data = await request(
    `/merchant/plans/${encodeURIComponent(planId)}?shop_id=${encodeURIComponent(shopId)}`,
    { method: 'PUT', body: payload },
  )
  return data.plan
}

export async function merchantTogglePlan(shopId, planId) {
  const data = await request(
    `/merchant/plans/${encodeURIComponent(planId)}/toggle?shop_id=${encodeURIComponent(shopId)}`,
    { method: 'POST' },
  )
  return data.plan
}

export async function merchantDeletePlan(shopId, planId) {
  await request(
    `/merchant/plans/${encodeURIComponent(planId)}?shop_id=${encodeURIComponent(shopId)}`,
    { method: 'DELETE' },
  )
}

export async function merchantBatchToggle(shopId, planIds, on) {
  const data = await request('/merchant/plans/batch-toggle', {
    method: 'POST',
    body: { shop_id: shopId, plan_ids: planIds, on },
  })
  return data
}

export async function merchantUpdateShop(shopId, payload) {
  const data = await request(`/merchant/shop/${encodeURIComponent(shopId)}`, {
    method: 'PUT',
    body: payload,
  })
  return data.shop
}

export async function merchantUpload(file) {
  const fd = new FormData()
  fd.append('file', file)
  const data = await request('/merchant/upload', { method: 'POST', body: fd })
  return data.url
}

export async function merchantCategories() {
  const data = await request('/merchant/categories')
  return data.categories
}

export async function merchantCreateCategory(name) {
  const data = await request('/merchant/categories', { method: 'POST', body: { name } })
  return data.category
}

export async function merchantRenameCategory(catId, name) {
  const data = await request(`/merchant/categories/${encodeURIComponent(catId)}`, {
    method: 'PUT',
    body: { name },
  })
  return data.category
}

export async function merchantDeleteCategory(catId) {
  await request(`/merchant/categories/${encodeURIComponent(catId)}`, { method: 'DELETE' })
}

export async function merchantChats() {
  const data = await request('/merchant/chats')
  return data.chats
}

export async function merchantChatMessages(chatId) {
  const data = await request(`/merchant/chats/${encodeURIComponent(chatId)}/messages`)
  return data
}

export async function merchantSendChatMessage(chatId, content) {
  const data = await request(`/merchant/chats/${encodeURIComponent(chatId)}/messages`, {
    method: 'POST',
    body: { content },
  })
  return data.message
}

export async function merchantChatWithUser(userId, shopId) {
  const data = await request('/merchant/chats/with-user', {
    method: 'POST',
    body: { user_id: userId, shop_id: shopId },
  })
  return data
}

export async function merchantAftersales(status = '', limit = 50, offset = 0) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (limit) params.set('limit', limit)
  if (offset) params.set('offset', offset)
  const data = await request(`/merchant/aftersales?${params.toString()}`)
  return data
}

export async function merchantApproveAftersale(asId) {
  const data = await request(`/merchant/aftersales/${encodeURIComponent(asId)}/approve`, { method: 'POST' })
  return data.aftersale
}

export async function merchantRejectAftersale(asId, note = '') {
  const data = await request(`/merchant/aftersales/${encodeURIComponent(asId)}/reject`, {
    method: 'POST',
    body: { note },
  })
  return data.aftersale
}

export async function merchantRefundAftersale(asId) {
  const data = await request(`/merchant/aftersales/${encodeURIComponent(asId)}/refund`, { method: 'POST' })
  return data.aftersale
}

export async function merchantWithdrawals(limit = 50, offset = 0) {
  const params = new URLSearchParams()
  if (limit) params.set('limit', limit)
  if (offset) params.set('offset', offset)
  const data = await request(`/merchant/withdrawals?${params.toString()}`)
  return data.withdrawals || []
}

export async function merchantApplyWithdrawal(payload) {
  const data = await request('/merchant/withdrawals', { method: 'POST', body: payload })
  return data.withdrawal
}

// ---------------- 通知 ----------------

export async function merchantNotifications(ntype = '', limit = 50, offset = 0) {
  const params = new URLSearchParams()
  if (ntype) params.set('type', ntype)
  if (limit) params.set('limit', limit)
  if (offset) params.set('offset', offset)
  const data = await request(`/merchant/notifications?${params.toString()}`)
  return data.notifications || []
}

export async function merchantNotificationsUnreadCount() {
  const data = await request('/merchant/notifications/unread-count')
  return data.count || 0
}

export async function merchantMarkNotificationsRead(ids = null, all = false) {
  const body = all ? { all: true } : { ids }
  const data = await request('/merchant/notifications/read', { method: 'POST', body })
  return data.marked || 0
}