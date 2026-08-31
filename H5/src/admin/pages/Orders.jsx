// 全局订单管理（M3）：筛选 + 分页 + 详情抽屉 + 状态干预。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Pager } from '../App'
import { fmtMoney } from '../../utils/price'

const STATUS_META = {
  created: { label: '待付款', cls: 'bg-pink/10 text-pink' },
  pending_payment: { label: '待付款', cls: 'bg-pink/10 text-pink' },
  paid: { label: '待发货', cls: 'bg-pink/10 text-pink' },
  shipped: { label: '配送中', cls: 'bg-pink/10 text-pink' },
  done: { label: '已完成', cls: 'bg-line/40 text-sub' },
  canceled: { label: '已取消', cls: 'bg-line/40 text-sub' },
}
const CAN_SET = ['created', 'paid', 'shipped', 'done', 'canceled']

export function Orders() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [limit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [detail, setDetail] = useState(null)
  const [nextStatus, setNextStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const data = await api.get('/admin/orders', { status, keyword, limit, offset })
    setRows(data.orders)
    setTotal(data.total)
  }, [status, keyword, limit, offset])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const openDetail = async (oid) => {
    setMsg('')
    try {
      const data = await api.get(`/admin/orders/${oid}`)
      setDetail(data.order)
      setNextStatus(data.order.status)
    } catch (e) {
      setMsg(e.message)
    }
  }

  const applyStatus = async () => {
    if (!detail || !nextStatus || busy) return
    setBusy(true)
    setMsg('')
    try {
      await api.post(`/admin/orders/${detail.order_id}/status`, { status: nextStatus })
      setMsg(`订单 ${detail.order_id} 已改为 ${STATUS_META[nextStatus]?.label || nextStatus}`)
      setDetail(null)
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">订单管理</h2>
      <p className="mt-1 text-[12px] text-sub">全平台订单视角，可强制干预订单状态</p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setOffset(0)
          }}
          placeholder="搜索 订单号 / 收货人 / 手机号"
          className="maison-field w-[240px] rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setOffset(0)
          }}
          className="rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        >
          <option value="">全部状态</option>
          {Object.entries(STATUS_META).map(([k, m]) => (
            <option key={k} value={k}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
        <table className="w-full min-w-[760px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
              <th className="px-4 py-3">订单号</th>
              <th className="px-4 py-3">商品</th>
              <th className="px-4 py-3">金额</th>
              <th className="px-4 py-3">收货人</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">下单时间</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => {
              const meta = STATUS_META[o.status] || { label: o.status, cls: 'bg-line/40 text-sub' }
              const r = o.recipient || {}
              return (
                <tr key={o.order_id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3 text-ink">{o.order_id}</td>
                  <td className="max-w-[220px] px-4 py-3">
                    <p className="truncate">{(o.items || []).map((i) => i.name).join('、')}</p>
                  </td>
                  <td className="px-4 py-3">{fmtMoney(o.paid_amount ?? o.total_price)}</td>
                  <td className="px-4 py-3 text-sub">{r.name || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-pill px-2 py-0.5 text-[11px] ${meta.cls}`}>{meta.label}</span>
                  </td>
                  <td className="px-4 py-3 text-sub">{o.created_at}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => openDetail(o.order_id)}
                      className="press rounded-[2px] border border-gold/40 bg-white px-2.5 py-1 text-[11px] text-gold"
                    >
                      详情 / 改状态
                    </button>
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sub">
                  没有匹配的订单
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Pager offset={offset} total={total} limit={limit} onChange={setOffset} />

      {/* 详情抽屉 */}
      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setDetail(null)}>
          <div
            className="h-full w-[420px] overflow-y-auto bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-serif-cn text-[18px] font-normal text-ink">订单详情</h3>
              <button onClick={() => setDetail(null)} className="press text-[12px] text-sub">
                关闭 ✕
              </button>
            </div>
            <p className="mt-1 text-[11px] text-sub">{detail.order_id}</p>

            <p className="eyebrow mt-5">商品明细</p>
            <div className="mt-2 space-y-2">
              {(detail.items || []).map((it) => (
                <div key={it.plan_id} className="flex items-center justify-between rounded-[2px] bg-bg px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-[12px] text-ink">{it.name}</p>
                    <p className="text-[10px] text-sub">
                      {fmtMoney(it.price)} × {it.qty}
                      {it.shop ? ` · ${it.shop}` : ''}
                    </p>
                  </div>
                  <p className="text-[12px] text-gold">{fmtMoney(it.price * it.qty)}</p>
                </div>
              ))}
            </div>

            <p className="eyebrow mt-5">收货信息</p>
            <div className="mt-2 space-y-1 rounded-[2px] bg-bg px-3 py-2 text-[12px]">
              <p>
                {detail.recipient?.name || '—'} {detail.recipient?.phone || ''}
              </p>
              <p className="text-sub">{detail.recipient?.address || '—'}</p>
              {detail.delivery_time && <p className="text-sub">送达：{detail.delivery_time}</p>}
              {detail.note && <p className="text-sub">备注：{detail.note}</p>}
            </div>

            <p className="eyebrow mt-5">支付与状态</p>
            <div className="mt-2 space-y-1 text-[12px]">
              <p>
                金额：<span className="text-gold">{fmtMoney(detail.paid_amount ?? detail.total_price)}</span>
                {detail.paid ? '（已支付）' : '（未支付）'}
              </p>
              <p>
                当前状态：
                <span className="ml-1 rounded-pill bg-pink/10 px-2 py-0.5 text-[11px] text-pink">
                  {(STATUS_META[detail.status] || {}).label || detail.status}
                </span>
              </p>
              {detail.paid_at && <p className="text-sub">支付时间：{detail.paid_at}</p>}
            </div>

            <p className="eyebrow mt-5">强制改状态</p>
            <div className="mt-2 flex items-center gap-2">
              <select
                value={nextStatus}
                onChange={(e) => setNextStatus(e.target.value)}
                className="flex-1 rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
              >
                {CAN_SET.map((s) => (
                  <option key={s} value={s}>
                    {(STATUS_META[s] || {}).label || s}
                  </option>
                ))}
              </select>
              <button
                onClick={applyStatus}
                disabled={busy}
                className="press rounded-[2px] bg-gold px-4 py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
              >
                {busy ? '保存中…' : '保存'}
              </button>
            </div>
            <p className="mt-2 text-[10px] text-sub/70">说明：管理员干预会绕过用户/商家流程直接落库。</p>
          </div>
        </div>
      )}
    </div>
  )
}
