import React, { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import SmartImage from '../components/SmartImage'
import { planImage } from '../assets/imageMap'
import { listOrders, orderAftersale } from '../api/shop'
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

import { statusMeta } from '../utils/status'

const fmtMoney = (v) => `¥${Number(v || 0).toFixed(2)}`

// 我的订单：状态筛选 + 订单卡片列表；点击进入物流追踪（含订单概要 + 时间线）
export default function Orders() {
  const nav = useNavigate()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('all')
  const [asTarget, setAsTarget] = useState(null) // 申请售后的订单
  const [asType, setAsType] = useState('refund')
  const [asReason, setAsReason] = useState('')
  const [asBusy, setAsBusy] = useState(false)

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

  // 售后：已支付且未取消的订单可发起
  const canAftersale = (o) => o.paid && o.status !== 'canceled'

  const submitAftersale = async (e) => {
    e.preventDefault()
    if (asBusy || !asTarget) return
    if (!asReason.trim()) {
      toast('请填写售后原因', 'error')
      return
    }
    setAsBusy(true)
    try {
      await orderAftersale(asTarget.order_id, { type: asType, reason: asReason.trim() })
      toast('售后申请已提交，等待平台审核')
      setAsTarget(null)
      setAsReason('')
      setAsType('refund')
    } catch (err) {
      toast(err.message || '提交失败', 'error')
    } finally {
      setAsBusy(false)
    }
  }

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
              const meta = statusMeta(o.status)
              const items = o.items || []
              const total = o.total_price != null
                ? o.total_price
                : items.reduce((s, it) => s + (it.price || 0) * (it.qty || 1), 0)
              const count = items.reduce((s, it) => s + (it.qty || 1), 0)
              return (
                <div
                  key={o.order_id}
                  className="block w-full overflow-hidden rounded-card bg-white border border-line text-left"
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
                    <div className="flex items-center gap-3">
                      {canAftersale(o) && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAsTarget(o)
                            setAsReason('')
                            setAsType('refund')
                          }}
                          className="press rounded-[2px] border border-gold/40 px-2.5 py-1 text-[11px] tracking-[1px] text-gold"
                        >
                          申请售后
                        </button>
                      )}
                      <span className="font-serif-cn text-[15px] font-normal text-ink">
                        合计 {fmtMoney(total)}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => nav(`/logistics/${o.order_id}`)}
                    className="press block w-full border-t border-line bg-bg/50 py-2 text-center text-[11px] tracking-[1px] text-sub"
                  >
                    查看物流跟踪
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 申请售后弹层 */}
      {asTarget && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setAsTarget(null)}
        >
          <form
            onSubmit={submitAftersale}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-h5 rounded-t-[20px] bg-white px-5 pb-8 pt-5"
          >
            <div className="mx-auto mb-4 h-[2px] w-9 bg-gold" />
            <h3 className="font-serif-cn text-[19px] font-normal text-ink">申请售后</h3>
            <p className="mt-1 text-[11px] text-sub">
              订单 {asTarget.order_id} · 合计 {fmtMoney(asTarget.total_price)}
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-[11px] text-sub">售后类型</label>
                <div className="flex gap-2">
                  {[
                    { v: 'refund', l: '退款' },
                    { v: 'return', l: '退货' },
                    { v: 'exchange', l: '换货' },
                  ].map((t) => (
                    <button
                      key={t.v}
                      type="button"
                      onClick={() => setAsType(t.v)}
                      className={`press flex-1 rounded-[2px] border py-2.5 text-[12px] tracking-[1px] ${
                        asType === t.v ? 'border-gold bg-gold/10 text-gold' : 'border-line bg-white text-sub'
                      }`}
                    >
                      {t.l}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">原因 *</label>
                <textarea
                  value={asReason}
                  onChange={(e) => setAsReason(e.target.value)}
                  maxLength={200}
                  rows={3}
                  placeholder="请描述售后原因"
                  className="maison-field w-full resize-none"
                />
              </div>
              <button
                type="submit"
                disabled={asBusy}
                className="press w-full rounded-[2px] bg-dark py-3 text-[12px] font-medium tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
              >
                {asBusy ? '提交中…' : '提交申请'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
