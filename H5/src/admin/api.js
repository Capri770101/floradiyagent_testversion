// 管理后台 API 封装：独立 axios 风格的 fetch 实例，Bearer + 401/403 统一跳登录。
// 与 H5 共用同一后端 /api，但使用独立的 admin 令牌键（floradiy_admin_token）——
// 与 C 端 floradiy_token 隔离：后台登录不干扰前端登录态，反之亦然。
const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const TOKEN_KEY = 'floradiy_admin_token'

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
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 || res.status === 403) {
    // 会话失效/越权：清令牌，由页面层跳登录
    window.dispatchEvent(new window.CustomEvent('admin:auth-fail', { detail: res.status }))
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

export async function login(username, password) {
  const data = await request('/auth/admin-login', { method: 'POST', body: { username, password } })
  setToken(data.token)
  return data
}

export async function fetchProfile() {
  const data = await request('/auth/me')
  return data.user
}

export async function adminWithdrawals(status = '', limit = 50, offset = 0) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (limit) params.set('limit', limit)
  if (offset) params.set('offset', offset)
  const data = await request(`/admin/withdrawals?${params.toString()}`)
  return { withdrawals: data.withdrawals || [], total: data.total || 0 }
}

export async function adminWithdrawalAct(wdId, action, note = '') {
  const data = await request(`/admin/withdrawals/${encodeURIComponent(wdId)}/${action}`, {
    method: 'POST',
    body: { note },
  })
  return data.withdrawal
}
