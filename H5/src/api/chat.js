// /chat 客户端：经由 Vite 代理 /api → localhost:8080（避免跨域，无需改后端）。
// 后端契约见 DESIGN_SPEC_H5.md §4（ui: text/plan_card/dialog_options/shop_card/pay_jump）。
// 身份统一来自 auth.js（登录态用令牌身份，未登录用匿名 uid），并自动携带 Bearer 令牌。

import { getUserId, authHeaders } from './auth'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export { getUserId }

export async function sendChat({ message, sessionId, userId }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      user_id: userId,
      message,
      session_id: sessionId || undefined,
    }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`后端返回 ${res.status}：${text.slice(0, 200)}`)
  }
  return res.json()
}

// 以下为「类 ChatGPT」多会话管理接口（详见后端 /conversations 系列端点）。

export async function listConversations(userId) {
  const res = await fetch(
    `${API_BASE}/conversations?user_id=${encodeURIComponent(userId)}`,
    { headers: authHeaders() }
  )
  if (!res.ok) throw new Error(`加载会话列表失败 ${res.status}`)
  const data = await res.json()
  return data.conversations || []
}

export async function createConversation(userId, title) {
  const res = await fetch(`${API_BASE}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ user_id: userId, title: title || '新对话' }),
  })
  if (!res.ok) throw new Error(`新建会话失败 ${res.status}`)
  const data = await res.json()
  return data.conversation_id
}

export async function getMessages(convId, userId) {
  const res = await fetch(
    `${API_BASE}/conversations/${encodeURIComponent(convId)}/messages?user_id=${encodeURIComponent(userId)}`,
    { headers: authHeaders() }
  )
  if (!res.ok) throw new Error(`加载消息失败 ${res.status}`)
  const data = await res.json()
  return data.messages || []
}

export async function deleteConversation(convId, userId) {
  const res = await fetch(
    `${API_BASE}/conversations/${encodeURIComponent(convId)}?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE', headers: authHeaders() }
  )
  if (!res.ok) throw new Error(`删除会话失败 ${res.status}`)
  return true
}

export async function renameConversation(convId, title, userId) {
  const res = await fetch(
    `${API_BASE}/conversations/${encodeURIComponent(convId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ user_id: userId, title }),
    }
  )
  if (!res.ok) throw new Error(`重命名失败 ${res.status}`)
  return true
}

// 生图任务轮询（后端契约：{task_id, status: pending|done|failed, result_url}）
export async function getImageTask(taskId) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`查询生图任务失败 ${res.status}`)
  return res.json()
}

// 后端图片 URL（/generated/xxx）需经 Vite 代理补 /api 前缀，否则打到 5173 端口 404
export function withApiUrl(u) {
  return u && !u.startsWith('/api') ? `/api${u}` : u
}
