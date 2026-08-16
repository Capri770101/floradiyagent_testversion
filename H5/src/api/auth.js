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

// 统一把 HTTP 状态码映射为对用户友好的文案：不透传后端 detail/JSON，避免技术性报错露给用户。
// 各接口对业务状态码（如 401 验证码错误、409 用户名已存在）单独给出更精准的文案。
function friendly(status, fallback) {
  const map = {
    400: '输入有误，请检查后重试',
    403: '没有权限执行该操作',
    404: '内容不存在或已被删除',
    422: '输入格式不正确，请检查后重试',
    502: '服务暂时不可用，请稍后重试',
    503: '服务暂不可用，请稍后重试',
  }
  return map[status] || fallback
}

export async function register({ username, password, nickname }) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, nickname }),
  })
  if (!res.ok) {
    throw new Error(
      res.status === 409 ? '该用户名已被注册，请换一个' : friendly(res.status, '注册失败，请稍后重试'),
    )
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
    throw new Error(
      res.status === 401 ? '用户名或密码错误，请重新输入' : friendly(res.status, '登录失败，请稍后重试'),
    )
  }
  const data = await res.json()
  setSession(data.token, data.user_id)
  return data
}

export async function getProfile() {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() })
  if (!res.ok) {
    throw new Error(res.status === 401 ? '登录已过期，请重新登录' : friendly(res.status, '获取资料失败，请稍后重试'))
  }
  const data = await res.json()
  return data.user
}

// ---- 手机号验证码登录 / 微信登录绑定 ----

export async function sendPhoneCode(phone) {
  const res = await fetch(`${API_BASE}/auth/phone-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone }),
  })
  if (!res.ok) {
    throw new Error(friendly(res.status, '验证码发送失败，请稍后重试'))
  }
  return res.json()
}

export async function phoneLogin({ phone, code }) {
  const res = await fetch(`${API_BASE}/auth/phone-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, code }),
  })
  if (!res.ok) {
    throw new Error(
      res.status === 401 ? '验证码错误或已过期，请重新获取' : friendly(res.status, '登录失败，请稍后重试'),
    )
  }
  const data = await res.json()
  setSession(data.token, data.user_id)
  return data
}

// 微信环境内取一次性 code（微信内置浏览器/小程序 web-view 提供 window.wx.login）
function wxLoginCode() {
  return new Promise((resolve, reject) => {
    const wx = window.wx
    if (wx && typeof wx.login === 'function') {
      wx.login({
        success: (res) => (res.code ? resolve(res.code) : reject(new Error('微信登录未返回 code'))),
        fail: () => reject(new Error('微信登录失败')),
      })
    } else {
      reject(new Error('请在微信中打开本页面，或使用手机号 / 账号登录'))
    }
  })
}

export async function wxLogin() {
  const code = await wxLoginCode()
  const res = await fetch(`${API_BASE}/auth/wx-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) {
    throw new Error(
      res.status === 503
        ? '微信登录暂不可用，请使用手机号登录'
        : friendly(res.status, '微信登录失败，请稍后重试'),
    )
  }
  const data = await res.json()
  setSession(data.token, data.user_id)
  return data
}

// 已登录账号绑定微信：把当前账号与微信 openid 关联，此后可直接微信登录
export async function wxBind() {
  const code = await wxLoginCode()
  const res = await fetch(`${API_BASE}/auth/wx-bind`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) {
    throw new Error(
      res.status === 409
        ? '该微信已绑定其他账号'
        : res.status === 503
          ? '微信绑定暂不可用，请稍后重试'
          : friendly(res.status, '微信绑定失败，请稍后重试'),
    )
  }
  return res.json()
}

// 当前是否运行在微信内置浏览器中（微信登录/绑定入口的可用性判断）
export function inWeChat() {
  return /MicroMessenger/i.test(navigator.userAgent)
}
