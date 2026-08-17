import React, { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import SmartImage from '../components/SmartImage'
import { planImage } from '../assets/imageMap'
import { listOrders } from '../api/shop'
import { toast } from '../utils/toast'

// 状态筛选 tab（键与后端 order.status 对齐）
const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'created', label: '待付款' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '配送中' },
  { key: 'done', label: '已完成' },
  { key: 'canceled', label: '已取消' },
]

const STATUS_META = {
  created: { label: '待付款', cls: 'bg-pink/10 text-pink' },
  pending_payment: { label: '待付款', cls: 'bg-pink/10 text-pink' },
  paid: { label: '待发货', cls: 'bg-amber-50 text-amber-600' },
  shipped: { label: '配送中', cls: 'bg-blue-50 text-blue-600' },
  done: { label: '已完成', cls: 'bg-green-50 text-green-600' },
  canceled: { label: '已取消', cls: 'bg-line/40 text-sub' },
}

const fmtMoney = (v) => `¥${Number(v || 0).toFixed(2)}`

// 我的订单：状态筛选 + 订单卡片列表；点击进入物流追踪（含订单概要 + 时间线）
export default function Orders() {
  const nav = useNavigate()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('all')

  useEffect(() => {
    listOrders()
      .then(setOrders)
      .catch((e) => toast(e.message || '订单加载失败', 'error'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(
    () => (tab === 'all' ? orders : orders.filter((o) => o.status === tab)),
    [orders, tab],
  )

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="我的订单" />
      {/* 状态筛选 tab：横向滚动，避免窄屏换行 */}
      <div className="flex shrink-0 gap-2 overflow-x-auto px-4 py-3">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
            className={`press shrink-0 rounded-pill px-3.5 py-1.5 text-[12px] tracking-[1px] ${
              tab === t.key ? 'bg-ink text-[#FAF8F5]' : 'bg-white text-sub border border-line'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-6">
        {loading ? (
          <p className="mt-6 rounded-card bg-white p-8 text-center text-[12px] text-sub border border-line">
            加载中…
          </p>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center">
            <p className="font-serif-cn text-[18px] font-normal text-ink">
              {tab === 'all' ? '还没有订单' : '该状态下暂无订单'}
            </p>
            <p className="mt-2 text-[11px] text-sub">去首页挑一束心仪的花吧</p>
            <button
              type="button"
              onClick={() => nav('/')}
              className="press mt-5 rounded-[2px] bg-dark px-8 py-2.5 text-[12px] font-medium tracking-[1px] text-[#FAF8F5]"
            >
              去逛逛
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((o) => {
              const meta = STATUS_META[o.status] || { label: o.status, cls: 'bg-line/40 text-sub' }
              const items = o.items || []
              const total = o.total_price != null
                ? o.total_price
                : items.reduce((s, it) => s + (it.price || 0) * (it.qty || 1), 0)
              const count = items.reduce((s, it) => s + (it.qty || 1), 0)
              return (
                <button
                  key={o.order_id}
                  type="button"
                  onClick={() => nav(`/logistics/${o.order_id}`)}
                  className="press block w-full overflow-hidden rounded-card bg-white border border-line text-left"
                >
                  <div className="flex items-center justify-between border-b border-line px-4 py-3">
                    <span className="text-[11px] text-sub">{o.order_id}</span>
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                      {meta.label}
                    </span>
                  </div>
                  {items.slice(0, 2).map((it) => (
                    <div key={it.plan_id} className="flex items-center gap-3 px-4 py-2.5">
                      <SmartImage
                        src={planImage(it)}
                        imgKey="home_rec_1"
                        className="h-[44px] w-[44px] shrink-0 rounded-[4px]"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] text-dark">{it.name}</p>
                        <p className="text-[11px] text-sub">
                          ¥{it.price} × {it.qty}
                          {it.shop ? ` · ${it.shop}` : ''}
                        </p>
                      </div>
                    </div>
                  ))}
                  {items.length > 2 && (
                    <p className="px-4 pb-2.5 text-[11px] text-sub">等 {items.length} 件商品</p>
                  )}
                  <div className="flex items-center justify-between border-t border-line px-4 py-3">
                    <span className="text-[11px] text-sub">共 {count} 件</span>
                    <span className="font-serif-cn text-[15px] font-normal text-ink">
                      合计 {fmtMoney(total)}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
