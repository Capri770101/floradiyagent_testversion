// 统一 HTTP 客户端：API_BASE + 请求封装（Bearer / 超时 / 错误友好化）+ 图片 URL 前缀。
// 各业务 api 文件（shop/chat/image/notify/recommend）统一引用，消除重复的 fetch 封装。

import { authHeaders, handleAuthFailure } from './auth'

export const API_BASE = import.meta.env.VITE_API_BASE || '/api'

/**
 * 统一请求封装：自动携带 Bearer、10s 超时、401 会话失效处理、错误文案友好化。
 * body 为 FormData 时不强制 Content-Type（交由浏览器边界）。
 */
export async function api(path, options = {}) {
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData
  const headers = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...authHeaders(),
    ...(options.headers || {}),
  }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 10000)
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: ctrl.signal })
    if (!res.ok) {
      handleAuthFailure(res)
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

// 后端图片 URL（/generated/xxx）需经 Vite 代理补 /api 前缀，否则打到 5173 端口 404
export function withApiUrl(u) {
  return u && !u.startsWith('/api') ? `/api${u}` : u
}
