// 消息通知中心接口客户端（NEW_FEATURES 模块一）。
// 契约见 routers/notify.py：列表（type/is_read 过滤 + 分页）/ 未读总数 / 标记已读 / 运营广播。
// 沿用统一请求封装（Bearer / 超时 / 错误友好化）。

import { api } from './client'

// ---------------- 通知列表 / 未读 / 已读 ----------------

export async function listNotifications({ type = '', isRead = null, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (type) params.set('type', type)
  if (isRead === 0 || isRead === 1) params.set('is_read', String(isRead))
  if (limit) params.set('limit', String(limit))
  if (offset) params.set('offset', String(offset))
  const q = params.toString()
  const data = await api(`/notifications${q ? `?${q}` : ''}`)
  return data.notifications
}

export async function unreadCount() {
  const data = await api('/notifications/unread-count')
  return data.unread
}

export async function getNotification(id) {
  const data = await api(`/notifications/${encodeURIComponent(id)}`)
  return data.notification
}

export async function markRead(ids) {
  const data = await api('/notifications/mark-read', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  })
  return data
}

export async function markAllRead() {
  const data = await api('/notifications/mark-read', {
    method: 'POST',
    body: JSON.stringify({ all: true }),
  })
  return data
}
