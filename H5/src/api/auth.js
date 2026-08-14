// 账号体系：注册 / 登录 / 资料，以及统一身份解析。
// 设计：登录后把 token + user_id 存入 localStorage；getUserId 优先返回登录身份，
// 未登录时回退到匿名 uid（首次自动生成），保证现有 dev 流程与数据隔离不受破坏。

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const TOKEN_KEY = 'floradiy_token'
const UID_KEY = 'floradiy_uid'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setSession(token, userId) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(UID_KEY, userId)
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(UID_KEY)
}

export function isLoggedIn() {
  return !!getToken()
}

// 统一用户标识：登录态用令牌对应的 user_id；未登录用匿名 uid（兼容旧版 floradiy_uid）。
export function getUserId() {
  const uid = localStorage.getItem(UID_KEY)
  if (uid) return uid
  let anon = localStorage.getItem('floradiy_uid')
  if (!anon) {
    anon = 'h5_' + Math.random().toString(36).slice(2, 10)
    localStorage.setItem('floradiy_uid', anon)
  }
  return anon
}

export function authHeaders() {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export async function register({ username, password, nickname }) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, nickname }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`注册失败 ${res.status}：${text.slice(0, 200)}`)
  }
  const data = await res.json()
  setSession(data.token, data.user_id)
  return data
}

export async function login({ username, password }) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`登录失败 ${res.status}：${text.slice(0, 200)}`)
  }
  const data = await res.json()
  setSession(data.token, data.user_id)
  return data
}

export async function getProfile() {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`获取资料失败 ${res.status}`)
  const data = await res.json()
  return data.user
}
