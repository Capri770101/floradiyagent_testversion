// Service 渲染测试：FAQ 与公告来自后端运营配置 /config（红线2：不写死在页面）。
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import Service from './Service'

const CONFIG = {
  faqs: [{ q: '测试问题A', a: '测试答案A' }],
  announcements: [{ content: '平台公告：春节正常营业' }],
}

const json = (body) => ({ ok: true, json: async () => body })

describe('Service FAQ/公告后端下发', () => {
  beforeEach(() => {
    localStorage.clear()
    globalThis.fetch = vi.fn(async (url) => {
      const u = String(url)
      if (u.includes('/api/config')) return json(CONFIG)
      return json({})
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('渲染后端下发的 FAQ 与公告（非页面写死）', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    root.render(
      <MemoryRouter>
        <Service />
      </MemoryRouter>,
    )
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    const text = container.textContent
    expect(text).toContain('测试问题A')
    expect(text).toContain('测试答案A')
    expect(text).toContain('平台公告')
    expect(text).toContain('春节正常营业')
    root.unmount()
    container.remove()
  })
})
