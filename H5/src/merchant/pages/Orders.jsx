// 商家订单管理：列表筛选 + 订单展开（方案卡）+ 发货 + 物流 + 联系顾客。
import React, { useCallback, useEffect, useState } from 'react'
import {
  merchantAddLogistics,
  merchantOrderDetail,
  merchantOrders,
  merchantShip,
  merchantStats,
} from '../api'
import { fmtMoney } from '../../utils/price'

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '配送中' },
  { key: 'done', label: '已完成' },
  { key: 'canceled', label: '已取消' },
]

const STATUS_META = {
  created: { label: '待付款', cls: 'bg-bg text-sub' },
  pending_payment: { label: '待付款', cls: 'bg-bg text-sub' },
  paid: { label: '待发货', cls: 'bg-gold/15 text-gold' },
  shipped: { label: '配送中', cls: 'bg-teal/15 text-teal' },
  done: { label: '已完成', cls: 'bg-ink/10 text-ink' },
  canceled: { label: '已取消', cls: 'bg-burgundy/10 text-burgundy' },
}

function PlanCard({ plan }) {
  if (!plan) return null
  return (
    <div className="mt-3 rounded-[2px] border border-line bg-bg/40 p-3 text-[12px] leading-relaxed text-ink">
      <p className="font-medium">{plan.name || 'DIY 方案'}</p>
      {plan.requirement && <p className="mt-1 text-sub">需求：{plan.requirement}</p>}
      {plan.difficulty && <p className="mt-1 text-sub">难度：{plan.difficulty} · {plan.est_time || '—'} 分钟 · 保鲜 {plan.shelf_life || '—'}</p>}
      {Array.isArray(plan.flowers) && plan.flowers.length > 0 && (
        <p className="mt-1 text-sub">
          花材：
          {plan.flowers.map((f) => `${f.name}${f.ratio ? ` ${f.ratio}` : ''}`).join(' · ')}
        </p>
      )}
      {plan.packaging && <p className="mt-1 text-sub">包装：{plan.packaging}</p>}
      {Array.isArray(plan.diy_steps) && plan.diy_steps.length > 0 && (
        <ol className="mt-2 list-decimal pl-4">
          {plan.diy_steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      )}
      {plan.card_message && <p className="mt-2 text-sub">卡片留言：{plan.card_message}</p>}
    </div>
  )
}

export function Orders({ onContact }) {
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [filterShop, setFilterShop] = useState('')
  const [shops, setShops] = useState([])
  const [orders, setOrders] = useState([])
  const [expandedId, setExpandedId] = useState('')
  const [plans, setPlans] = useState({})
  const [logiDraft, setLogiDraft] = useState({})
  const [busyId, setBusyId] = useState('')
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const [list, st] = await Promise.all([
        merchantOrders(filterShop, status, keyword, dateFrom, dateTo),
        merchantStats(),
      ])
      setOrders(list)
      setShops((st.shops || []).map((s) => (typeof s === 'string' ? { id: s, name: s } : s)))
    } catch (e) {
      setErr(e.message || '订单加载失败')
    } finally {
      setLoading(false)
    }
  }, [filterShop, status, keyword, dateFrom, dateTo])

  useEffect(() => {
    load()
  }, [load])

  const toggleExpand = async (o) => {
    setExpandedId(expandedId === o.order_id ? '' : o.order_id)
    if (expandedId === o.order_id) return
    if (!o.plan_id || plans[o.order_id]) return
    try {
      const detail = await merchantOrderDetail(o.order_id)
      setPlans((prev) => ({ ...prev, [o.order_id]: detail.plan || null }))
    } catch (e) {
      setPlans((prev) => ({ ...prev, [o.order_id]: null }))
    }
  }

  const ship = async (o) => {
    if (busyId) return
    setBusyId(o.order_id)
    try {
      await merchantShip(o.order_id)
      await load()
    } catch (e) {
      setErr(e.message || '发货失败')
    } finally {
      setBusyId('')
    }
  }

  const addLogistics = async (o) => {
    const text = (logiDraft[o.order_id] || '').trim()
    if (!text) return
    if (busyId) return
    setBusyId(o.order_id)
    try {
      await merchantAddLogistics(o.order_id, text)
      setLogiDraft((d) => ({ ...d, [o.order_id]: '' }))
      await load()
    } catch (e) {
      setErr(e.message || '物流更新失败')
    } finally {
      setBusyId('')
    }
  }

  const pendingShip = orders.filter((o) => o.status === 'paid')

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">订单管理</h2>
        {pendingShip.length > 0 && (
          <span className="text-[11px] text-gold">待发货 {pendingShip.length} 单</span>
        )}
      </div>

      <div className="mt-4 rounded-card border border-line bg-white p-3">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索订单号 / 收货人 / 商品名"
          className="w-full rounded-[4px] border border-line bg-bg/50 px-3 py-2 text-[12px] text-ink outline-none transition placeholder:text-sub/50 focus:border-gold"
        />
        <div className="mt-2 flex items-center gap-2">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold" />
          <span className="shrink-0 text-[10px] text-sub/60">至</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold" />
          {(keyword || dateFrom || dateTo) && (
            <button onClick={() => { setKeyword(''); setDateFrom(''); setDateTo('') }} className="press shrink-0 rounded-[4px] border border-gold/40 px-2.5 py-1.5 text-[11px] tracking-[1px] text-gold">清除</button>
          )}
        </div>
      </div>

      <div className="mt-3 flex gap-1.5">
        {STATUS_TABS.map((t) => (
          <button key={t.key} onClick={() => setStatus(t.key)} className={`flex-1 rounded-full border py-1.5 text-center text-[11px] transition ${status === t.key ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'}`}>{t.label}</button>
        ))}
      </div>
      {shops.length > 0 && (
        <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none]">
          <button onClick={() => setFilterShop('')} className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${!filterShop ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'}`}>全部店铺</button>
          {shops.map((s) => (
            <button key={s.id} onClick={() => setFilterShop(s.id)} className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${filterShop === s.id ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'}`}>{s.name}</button>
          ))}
        </div>
      )}

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      <div className="mt-4 space-y-3">
        {loading ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : orders.length === 0 ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">暂无订单</p>
        ) : (
          orders.map((o) => {
            const s = STATUS_META[o.status] || { label: o.status, cls: 'bg-bg text-sub' }
            const expanded = expandedId === o.order_id
            return (
              <div key={o.order_id} className="rounded-card border border-line bg-white p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] ${s.cls}`}>{s.label}</span>
                    <span className="text-[12px] text-ink">{fmtMoney(o.total_price)}</span>
                  </div>
                  <span className="text-[10px] text-sub">{o.created_at?.replace('T', ' ').slice(0, 16)}</span>
                </div>
                <p className="mt-1 truncate text-[11px] text-sub">{o.order_id}</p>
                {o.recipient_name && <p className="mt-0.5 text-[11px] text-sub">收货人：{o.recipient_name} {o.recipient_phone}</p>}
                <div className="mt-2 flex gap-2">
                  {o.status === 'paid' && (
                    <button onClick={() => ship(o)} disabled={busyId === o.order_id} className="rounded-[4px] bg-gold px-3 py-1 text-[11px] text-white disabled:opacity-50">{busyId === o.order_id ? '发货中…' : '确认发货'}</button>
                  )}
                  <button onClick={() => toggleExpand(o)} className="rounded-[4px] border border-line px-3 py-1 text-[11px] text-sub">{expanded ? '收起' : '详情'}</button>
                  <button onClick={() => onContact?.(o.user_id)} className="rounded-[4px] border border-line px-3 py-1 text-[11px] text-sub">联系顾客</button>
                </div>
                {expanded && (
                  <div className="mt-3 border-t border-line pt-3">
                    <PlanCard plan={plans[o.order_id]} />
                    <div className="mt-2 flex gap-2">
                      <input value={logiDraft[o.order_id] || ''} onChange={(e) => setLogiDraft((d) => ({ ...d, [o.order_id]: e.target.value }))} placeholder="物流更新（如：已揽收）" className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] outline-none focus:border-gold" />
                      <button onClick={() => addLogistics(o)} disabled={!logiDraft[o.order_id]?.trim() || busyId === o.order_id} className="rounded-[4px] border border-gold/40 px-2.5 py-1.5 text-[11px] text-gold disabled:opacity-50">更新物流</button>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
