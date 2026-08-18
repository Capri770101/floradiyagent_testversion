// ShopDetail 渲染测试：验证店铺详情字段真实渲染自后端契约结构
// （distance_km / delivery_time / 经营信息 / 分类菜单），防止前端回退硬编码。
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ShopDetail from './ShopDetail'

const SHOP = {
  id: 'S001',
  name: '花漾工坊(盐田店)',
  rating: '4.8',
  status: '营业中',
  distance_km: 1.2, // 详情接口 _shop_full 返回 distance_km 数值（列表接口返回 dist，见 Agent 卡片）
  intro: '专注鲜花定制与同城速递，包装精致、准时送达。',
  sales: 520,
  min_delivery: 100,
  delivery_fee: 3,
  delivery_time: '约15分钟',
  hours: '09:00 - 21:00',
  address: '深圳市盐田区海景路 8 号（示例地址）',
  notice: '今日母亲节订花高峰，请提前 2 小时下单',
  image: '',
  cover: '',
  logo: '',
  menu: [
    {
      id: 'cat_holiday',
      name: '节日祝福',
      items: [
        {
          id: 'P001',
          name: '康乃馨感恩花束',
          price: 199,
          desc: '11 支粉色康乃馨 + 满天星，适合送给母亲表达感恩。',
          sales: 300,
          tags: [],
          style: '韩式',
          label: 'New',
          image: '',
        },
      ],
    },
  ],
  recommend: [{ id: 'P001', name: '康乃馨感恩花束', price: 199 }],
}

const json = (body) => ({ ok: true, json: async () => body })

function renderShop() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  root.render(
    <MemoryRouter initialEntries={['/shop/S001']}>
      <Routes>
        <Route path="/shop/:id" element={<ShopDetail />} />
      </Routes>
    </MemoryRouter>,
  )
  return { container, root }
}

describe('ShopDetail 字段契约渲染', () => {
  beforeEach(() => {
    localStorage.clear()
    globalThis.fetch = vi.fn(async (url) => {
      const u = String(url)
      if (u.includes('/api/shops/S001')) return json({ shop: SHOP })
      if (u.includes('/api/cart')) return json({ items: [] })
      return json({})
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('渲染距离 / 配送时长 / 经营信息 / 菜单（均来自后端结构）', async () => {
    const { container, root } = renderShop()
    // 等待异步数据加载（fetch promise 链 + setState）
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    const text = container.textContent
    expect(text).toContain('花漾工坊')
    expect(text).toContain('4.8')
    expect(text).toContain('月售 520')
    expect(text).toContain('1.2km') // distance_km 数值由后端下发
    expect(text).toContain('起送 ¥100')
    expect(text).toContain('配送 ¥3')
    expect(text).toContain('约15分钟') // delivery_time 由后端下发（shops 表）
    expect(text).toContain('今日母亲节订花高峰')
    expect(text).toContain('节日祝福')
    expect(text).toContain('康乃馨感恩花束')
    expect(text).toContain('¥199')
    root.unmount()
    container.remove()
  })
})