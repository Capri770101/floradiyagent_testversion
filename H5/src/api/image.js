// 生图接口客户端：经由 Vite 代理 /api → 后端（localhost:8080），无需改后端 CORS。
// 契约见后端 POST /image/generate（提交）与 GET /tasks/{task_id}（轮询）。
// 后端已对下载地址做 SSRF 白名单 + 私网 IP 校验，前端只负责提交 prompt 与轮询结果。

import { authHeaders, handleAuthFailure } from './auth'

export const API_BASE = import.meta.env.VITE_API_BASE || '/api'

// 提交生图任务，立即返回 task_id；随后轮询 GET /tasks/{task_id} 取结果。
// prompt 通常来自 DIY 方案的 effect_prompt（与花材/色彩/包装一致）。
export async function generateEffectImage(prompt) {
  const res = await fetch(`${API_BASE}/image/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) {
    handleAuthFailure(res)
    const text = await res.text().catch(() => '')
    throw new Error(`生图请求失败 ${res.status}：${text.slice(0, 200)}`)
  }
  return res.json() // { task_id, status, poll }
}

// 轮询生图任务直到 done（返回带 result_url）或 failed，或超时（默认 60s）。
// 后端 result_url 形如 /generated/xxx.png，需拼接 API_BASE 经代理访问。
export async function pollImageTask(taskId, { timeoutMs = 60000, intervalMs = 2000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}`, {
      headers: authHeaders(),
    })
    if (!res.ok) {
      handleAuthFailure(res)
      throw new Error(`轮询生图失败 ${res.status}`)
    }
    const data = await res.json()
    if (data.status === 'done' && data.result_url) return data
    if (data.status === 'failed') throw new Error('生图失败，请重试')
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error('生图超时，请稍后重试')
}
