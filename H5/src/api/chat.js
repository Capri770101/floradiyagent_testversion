// /chat 客户端：经由 Vite 代理 /api → localhost:8080（避免跨域，无需改后端）。
// 后端契约见 DESIGN_SPEC_H5.md §4（ui: text/plan_card/dialog_options/shop_card/pay_jump）。
// 身份统一来自 auth.js（登录态用令牌身份，未登录用匿名 uid），并自动携带 Bearer 令牌。

import { getUserId, authHeaders, handleAuthFailure } from './auth'
import { getLocation } from '../utils/location'
import { API_BASE, withApiUrl } from './client'

export { getUserId }
export { withApiUrl }

export async function sendChat({ message, sessionId, userId, shopId }) {
  const loc = getLocation()
  const body = {
    user_id: userId,
    message,
    session_id: sessionId || undefined,
  }
  if (shopId) body.shop_id = shopId
  if (loc?.lat != null && loc?.lng != null) body.location = { lat: loc.lat, lng: loc.lng }
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    handleAuthFailure(res)
    const text = await res.text().catch(() => '')
    throw new Error(`后端返回 ${res.status}：${text.slice(0, 200)}`)
  }
  return res.json()
}

/**
 * SSE 流式对话：实时推送 agent 思考过程、工具调用、文本回复和结构化卡片。
 *
 * @param {Object} params
 * @param {string} params.message - 用户消息
 * @param {string} [params.sessionId] - 会话 ID
 * @param {string} params.userId - 用户 ID
 * @param {function} params.onText - 文本片段回调 (text: string) => void
 * @param {function} [params.onToolCall] - 工具调用回调 ({name, status}) => void
 * @param {function} [params.onCard] - 结构化卡片回调 ({ui, data}) => void
 * @param {function} [params.onDone] - 流结束回调 ({sessionId}) => void
 * @param {function} [params.onError] - 错误回调 (message: string) => void
 * @returns {function} abort - 调用可中断 SSE 连接
 */
export function sendChatStream({ message, sessionId, userId, shopId, onText, onToolCall, onCard, onDone, onError }) {
  const loc = getLocation()
  const body = {
    user_id: userId,
    message,
    session_id: sessionId || undefined,
  }
  if (shopId) body.shop_id = shopId
  if (loc?.lat != null && loc?.lng != null) body.location = { lat: loc.lat, lng: loc.lng }

  const ctrl = new AbortController()

  fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal: ctrl.signal,
  }).then(async (res) => {
    if (!res.ok) {
      handleAuthFailure(res)
      const text = await res.text().catch(() => '')
      onError?.(`后端返回 ${res.status}：${text.slice(0, 200)}`)
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 事件（按 \n\n 分割）
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''  // 最后一段可能不完整，保留

      for (const raw of events) {
        if (!raw.trim()) continue
        let eventType = 'message'
        let eventData = ''

        for (const line of raw.split('\n')) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6)
          }
        }

        if (!eventData) continue

        try {
          const data = JSON.parse(eventData)
          switch (eventType) {
            case 'text':
              onText?.(data.content || '')
              break
            case 'tool_call':
              onToolCall?.({ name: data.name, status: data.status })
              break
            case 'card':
              onCard?.({ ui: data.ui, data: data.data })
              break
            case 'done':
              onDone?.({ sessionId: data.session_id })
              break
            case 'error':
              onError?.(data.message || '未知错误')
              break
            default:
              // thinking 等其他事件，暂不处理
              break
          }
        } catch {
          // JSON 解析失败，忽略
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') {
      onError?.(err.message || 'SSE 连接失败')
    }
  })

  return () => ctrl.abort()
}

// 以下为「类 ChatGPT」多会话管理接口（详见后端 /conversations 系列端点）。

export async function listConversations(userId) {
  const res = await fetch(
    `${API_BASE}/conversations?user_id=${encodeURIComponent(userId)}`,
    { headers: authHeaders() }
  )
  if (!res.ok) {
    handleAuthFailure(res)
    throw new Error(`加载会话列表失败 ${res.status}`)
  }
  const data = await res.json()
  return data.conversations || []
}

export async function createConversation(userId, title) {
  const res = await fetch(`${API_BASE}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ user_id: userId, title: title || '新对话' }),
  })
  if (!res.ok) {
    handleAuthFailure(res)
    throw new Error(`新建会话失败 ${res.status}`)
  }
  const data = await res.json()
  return data.conversation_id
}

export async function getMessages(convId, userId) {
  const res = await fetch(
    `${API_BASE}/conversations/${encodeURIComponent(convId)}/messages?user_id=${encodeURIComponent(userId)}`,
    { headers: authHeaders() }
  )
  if (!res.ok) {
    handleAuthFailure(res)
    throw new Error(`加载消息失败 ${res.status}`)
  }
  const data = await res.json()
  return data.messages || []
}

export async function deleteConversation(convId, userId) {
  const res = await fetch(
    `${API_BASE}/conversations/${encodeURIComponent(convId)}?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE', headers: authHeaders() }
  )
  if (!res.ok) {
    handleAuthFailure(res)
    throw new Error(`删除会话失败 ${res.status}`)
  }
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
  if (!res.ok) {
    handleAuthFailure(res)
    throw new Error(`重命名失败 ${res.status}`)
  }
  return true
}

// 生图任务轮询（后端契约：{task_id, status: pending|done|failed, result_url}）
export async function getImageTask(taskId) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    handleAuthFailure(res)
    throw new Error(`查询生图任务失败 ${res.status}`)
  }
  return res.json()
}
