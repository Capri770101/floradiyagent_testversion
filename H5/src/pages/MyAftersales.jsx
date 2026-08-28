// 我的售后（M4 用户侧）：售后单列表、进度时间轴，并支持从此页发起售后。
import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import Reveal from '../components/Reveal'
import { myAftersales, listOrders, orderAftersale } from '../api/shop'
import { toast } from '../utils/toast'

const AS_STATUS = {
  pending: { label: '待审核', cls: 'bg-pink/10 text-pink' },
  approved: { label: '已通过', cls: 'bg-gold/15 text-gold-dark' },
  rejected: { label: '已拒绝', cls: 'bg-line/40 text-sub' },
  refunded: { label: '已退款', cls: 'bg-green/20 text-[#5b8a6a]' },
  closed: { label: '已关闭', cls: 'bg-line/40 text-sub' },
}
const AS_TYPE = { refund: '退款', return: '退货', exchange: '换货' }
const ELIGIBLE = ['paid', 'shipped', 'done']
const REASONS = ['七日无理由退货', '商品破损/缺漏', '与描述不符', '错发/漏发', '其他']

const STEPS = {
  pending: { list: ['提交申请', '平台审核'], active: 0 },
  approved: { list: ['提交申请', '审核通过', '处理中'], active: 1 },
  rejected: { list: ['提交申请', '审核不通过'], active: 1 },
  refunded: { list: ['提交申请', '审核通过', '已退款'], active: 2 },
  closed: { list: ['提交申请', '已关闭'], active: 1 },
}

export default function MyAftersales() {
  const nav = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [orders, setOrders] = useState([])
  const [pick, setPick] = useState('')
  const [type, setType] = useState('refund')
  const [reason, setReason] = useState(REASONS[0])
  const [desc, setDesc] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const load = () => {
    myAftersales()
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const openCreate = async () => {
    setCreating(true)
    setPick('')
    setType('refund')
    setReason(REASONS[0])
    setDesc('')
    try {
      const os = await listOrders()
      setOrders((os || []).filter((o) => ELIGIBLE.includes(o.status)))
    } catch {
      setOrders([])
    }
  }

  const submit = async () => {
    if (!pick) return toast('请选择要售后的订单', 'error')
    setSubmitting(true)
    try {
      await orderAftersale(pick, { type, reason, description: desc.trim() })
      toast('售后申请已提交')
      setCreating(false)
      load()
    } catch (e) {
      toast(e.message || '提交失败', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="我的售后" right={loading ? null : (
        <button onClick={openCreate} className="press text-[12px] text-gold-dark">发起售后</button>
      )} />
      <div className="flex-1 overflow-y-auto px-4 pb-8">
        {loading ? (
          <p className="mt-6 rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : rows.length === 0 ? (
          <Reveal>
            <div className="py-16 text-center">
              <p className="font-serif-cn text-[18px] font-normal text-ink">还没有售后记录</p>
              <p className="mt-2 text-[11px] text-sub">已支付订单可在「我的订单」中发起退款/退货/换货</p>
              <button
                onClick={() => nav('/orders')}
                className="press mt-5 rounded-[2px] bg-dark px-8 py-2.5 text-[12px] font-medium tracking-[1px] text-[#FAF8F5]"
              >
                去订单页
              </button>
            </div>
          </Reveal>
        ) : (
          <div className="mt-3 space-y-3">
            {rows.map((a, i) => (
              <Reveal key={a.id} delay={i * 140}>
                <AftersaleCard a={a} />
              </Reveal>
            ))}
          </div>
        )}
      </div>

      {creating && (
        <div className="fixed inset-0 z-30 flex flex-col bg-bg">
          <TopBar title="发起售后" onBack={() => setCreating(false)} />
          <div className="flex-1 overflow-y-auto px-4 py-4">
            <p className="text-[12px] text-sub">选择订单</p>
            <div className="mt-2 space-y-2">
              {orders.length === 0 && (
                <p className="rounded-card border border-line bg-white p-5 text-center text-[12px] text-sub">
                  没有可售后的订单（仅已支付/已发货/已完成的订单可申请）
                </p>
              )}
              {orders.map((o) => {
                const first = (o.items && o.items[0]) || {}
                return (
                  <button
                    key={o.order_id}
                    onClick={() => setPick(o.order_id)}
                    className={`flex w-full items-center justify-between rounded-card border p-3 text-left ${
                      pick === o.order_id ? 'border-gold bg-gold/5' : 'border-line bg-white'
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[12px] text-ink">{first.name || o.order_id}</p>
                      <p className="mt-0.5 text-[10px] text-sub">{o.order_id}</p>
                    </div>
                    <span className="shrink-0 text-[11px] text-gold-dark">
                      ¥{(o.total_price || 0).toFixed(2)}
                    </span>
                  </button>
                )
              })}
            </div>

            <p className="mt-5 text-[12px] text-sub">售后类型</p>
            <div className="mt-2 flex gap-2">
              {Object.entries(AS_TYPE).map(([k, v]) => (
                <button
                  key={k}
                  onClick={() => setType(k)}
                  className={`press flex-1 rounded-pill border py-2 text-[12px] ${
                    type === k ? 'border-gold bg-gold text-[#FAF8F5]' : 'border-line bg-white text-ink'
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>

            <p className="mt-5 text-[12px] text-sub">原因</p>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="maison-field mt-2 w-full !text-[12px]"
            >
              {REASONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>

            <p className="mt-5 text-[12px] text-sub">补充说明</p>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={3}
              maxLength={500}
              placeholder="可补充具体情况（选填）"
              className="maison-field mt-2 w-full !h-auto !text-[12px]"
            />
          </div>
          <div className="flex gap-3 border-t border-line bg-white px-4 py-3">
            <button
              onClick={() => setCreating(false)}
              className="press rounded-[2px] border border-line px-6 py-2.5 text-[12px] text-ink"
            >
              取消
            </button>
            <button
              onClick={submit}
              disabled={submitting || !pick}
              className="press flex-1 rounded-[2px] bg-dark py-2.5 text-[12px] font-medium tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
            >
              {submitting ? '提交中…' : '提交申请'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function AftersaleCard({ a }) {
  const m = AS_STATUS[a.status] || { label: a.status, cls: 'bg-line/40 text-sub' }
  const steps = STEPS[a.status] || { list: ['提交申请'], active: 0 }
  return (
    <div className="rounded-card border border-line bg-white p-4">
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-sub">{a.id}</p>
        <span className={`rounded-pill px-2 py-0.5 text-[10px] font-medium ${m.cls}`}>{m.label}</span>
      </div>
      <div className="mt-2 space-y-1 text-[12px]">
        <p className="text-ink">
          {AS_TYPE[a.type] || a.type} · 订单 <span className="text-sub">{a.order_id}</span>
        </p>
        {a.reason && <p className="text-sub">原因：{a.reason}</p>}
        {a.description && <p className="text-sub">说明：{a.description}</p>}
        {a.refund_amount != null && <p className="text-gold-dark">退款金额：¥{a.refund_amount}</p>}
        {a.review_note && <p className="text-burgundy">平台备注：{a.review_note}</p>}
      </div>

      {/* 进度时间轴 */}
      <div className="mt-3 flex items-center gap-1 border-t border-line pt-3">
        {steps.list.map((s, i) => {
          const done = i < steps.active
          const cur = i === steps.active
          return (
            <React.Fragment key={s}>
              <div className="flex flex-col items-center gap-1">
                <span
                  className={`h-2 w-2 rounded-full ${done ? 'bg-gold' : cur ? 'bg-gold/50' : 'bg-line'}`}
                />
                <span className={`text-[9px] ${done || cur ? 'text-ink' : 'text-sub/60'}`}>{s}</span>
              </div>
              {i < steps.list.length - 1 && (
                <span className={`h-px flex-1 ${i < steps.active ? 'bg-gold' : 'bg-line'}`} />
              )}
            </React.Fragment>
          )
        })}
      </div>

      <p className="mt-2 text-[10px] text-sub/70">{a.created_at}</p>
    </div>
  )
}
