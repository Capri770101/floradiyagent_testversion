// 商家订单管理：列表筛选 + 订单展开（方案卡）+ 发货 + 物流 + 联系顾客。
import React, { useCallback, useEffect, useState } from 'react'
import {
  merchantAcceptOrder,
  merchantAddLogistics,
  merchantOrderDetail,
  merchantOrders,
  merchantRejectOrder,
  merchantShip,
  merchantStats,
} from '../api'
import { fmtMoney } from '../../utils/price'

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'paid', label: '待确认' },
  { key: 'shipped', label: '配送中' },
  { key: 'done', label: '已完成' },
  { key: 'canceled', label: '已取消' },
]

const STATUS_META = {
  created: { label: '待付款', cls: 'bg-bg text-sub' },
  pending_payment: { label: '待付款', cls: 'bg-bg text-sub' },
  paid: { label: '待确认', cls: 'bg-gold/15 text-gold' },
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

  const accept = async (o) => {
    if (busyId) return
    setBusyId(o.order_id)
    try {
      await merchantAcceptOrder(o.order_id)
      await load()
    } catch (e) {
      setErr(e.message || '接单失败')
    } finally {
      setBusyId('')
    }
  }

  const reject = async (o) => {
    if (busyId) return
    const reason = window.prompt('拒单原因（可选）：') ?? ''
    if (reason === null) return
    setBusyId(o.order_id)
    try {
      await merchantRejectOrder(o.order_id, reason.trim())
      await load()
    } catch (e) {
      setErr(e.message || '拒单失败')
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

  const pendingConfirm = orders.filter((o) => o.status === 'paid' && !o.merchant_status)

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">订单管理</h2>
        {pendingConfirm.length > 0 && (
          <span className="text-[11px] text-gold">待确认 {pendingConfirm.length} 单</span>
        )}
      </div>

      {/* 筛选 */}
      <div className="mt-4 rounded-card border border-line bg-white p-3">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索订单号 / 收货人 / 商品名"
          className="w-full rounded-[4px] border border-line bg-bg/50 px-3 py-2 text-[12px] text-ink outline-none transition placeholder:text-sub/50 focus:border-gold"
        />
        <div className="mt-2 flex items-center gap-2">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold"
          />
          <span className="shrink-0 text-[10px] text-sub/60">至</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold"
          />
          {(keyword || dateFrom || dateTo) && (
            <button
              onClick={() => {
                setKeyword('')
                setDateFrom('')
                setDateTo('')
              }}
              className="press shrink-0 rounded-[4px] border border-gold/40 px-2.5 py-1.5 text-[11px] tracking-[1px] text-gold"
            >
              清除
            </button>
          )}
        </div>
      </div>

      {/* 状态 + 店铺筛选 */}
      <div className="mt-3 flex gap-1.5">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setStatus(t.key)}
            className={`flex-1 rounded-full border py-1.5 text-center text-[11px] transition ${
              status === t.key ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {shops.length > 0 && (
        <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none]">
          <button
            onClick={() => setFilterShop('')}
            className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${
              !filterShop ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
            }`}
          >
            全部店铺
          </button>
          {shops.map((s) => (
            <button
              key={s.id}
              onClick={() => setFilterShop(s.id)}
              className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${
                filterShop === s.id ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      {/* 订单列表 */}
      <div className="mt-4 space-y-3">
        {loading ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : orders.length === 0 ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">暂无订单</p>
        ) : (
          orders.map((o) => {
            const meta = STATUS_META[o.status] || { label: o.status, cls: 'bg-bg text-sub' }
            const expanded = expandedId === o.order_id
            return (
              <div key={o.order_id} className="rounded-card border border-line bg-white p-4">
                <button onClick={() => toggleExpand(o)} className="w-full text-left">
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] text-ink">
                        {o.recipient_name || '顾客'} · {o.shop_id || '—'}
                      </p>
                      <p className="mt-0.5 text-[10px] text-sub">{o.order_id}</p>
                    </div>
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] ${meta.cls}`}>{meta.label}</span>
                  </div>
                  <div className="mt-2 flex items-baseline justify-between text-[11px] text-sub">
                    <span>{o.created_at?.replace('T', ' ').slice(0, 16) || ''}</span>
                    <span className="text-[13px] text-ink">{fmtMoney(o.total_price)}</span>
                  </div>
                </button>

                {expanded && (
                  <div className="mt-3 border-t border-line pt-3">
                    <PlanCard plan={plans[o.order_id]} />
                    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-sub">
                      <p>收货：{o.recipient_name} {o.recipient_phone}</p>
                      <p>地址：{o.recipient_address || '—'}</p>
                      {o.note && <p className="col-span-2">备注：{o.note}</p>}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {o.status === 'paid' && !o.merchant_status && (
                        <>
                          <button
                            onClick={() => accept(o)}
                            disabled={!!busyId}
                            className="press rounded-[4px] bg-gold px-4 py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                          >
                            {busyId === o.order_id ? '处理中…' : '接单'}
                          </button>
                          <button
                            onClick={() => reject(o)}
                            disabled={!!busyId}
                            className="press rounded-[4px] border border-burgundy/40 px-4 py-2 text-[12px] tracking-[1px] text-burgundy disabled:opacity-40"
                          >
                            {busyId === o.order_id ? '处理中…' : '拒单'}
                          </button>
                        </>
                      )}
                      {o.status === 'paid' && o.merchant_status === 'accepted' && (
                        <button
                          onClick={() => ship(o)}
                          disabled={!!busyId}
                          className="press rounded-[4px] bg-gold px-4 py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                        >
                          {busyId === o.order_id ? '处理中…' : '发货'}
                        </button>
                      )}
                      {o.merchant_status === 'rejected' && (
                        <span className="self-center text-[11px] text-burgundy">已拒单并退款</span>
                      )}
                      {o.user_id && (
                        <button
                          onClick={() => onContact && onContact(o)}
                          className="press rounded-[4px] border border-gold/40 px-4 py-2 text-[12px] tracking-[1px] text-gold"
                        >
                          联系顾客
                        </button>
                      )}
                      {o.status === 'shipped' && (
                        <div className="flex items-center gap-1.5">
                          <input
                            value={logiDraft[o.order_id] || ''}
                            onChange={(e) => setLogiDraft((d) => ({ ...d, [o.order_id]: e.target.value }))}
                            placeholder="更新物流信息"
                            className="w-44 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none focus:border-gold"
                          />
                          <button
                            onClick={() => addLogistics(o)}
                            disabled={!!busyId}
                            className="press rounded-[4px] border border-line px-3 py-1.5 text-[11px] text-sub disabled:opacity-40"
                          >
                            更新
                          </button>
                        </div>
                      )}
                    </div>
                    {o.logistics && o.logistics.length > 0 && (
                      <div className="mt-3 space-y-1 border-t border-line pt-3">
                        {o.logistics.map((lg, i) => (
                          <p key={i} className="text-[10px] text-sub">
                            {lg.time} {lg.text}
                          </p>
                        ))}
                      </div>
                    )}
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