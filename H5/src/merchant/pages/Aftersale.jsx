// 商家售后处理：本店售后单列表 + 通过/拒绝/退款操作。
import React, { useCallback, useEffect, useState } from 'react'
import { merchantAftersales, merchantApproveAftersale, merchantRejectAftersale, merchantRefundAftersale } from '../api'
import { fmtMoney } from '../../utils/price'

const TYPE_META = {
  refund: { label: '退款', cls: 'bg-gold/15 text-gold' },
  return: { label: '退货', cls: 'bg-teal/15 text-teal' },
  exchange: { label: '换货', cls: 'bg-ink/10 text-ink' },
}

const STATUS_META = {
  pending: { label: '待审核', cls: 'bg-gold/15 text-gold' },
  approved: { label: '已通过', cls: 'bg-teal/15 text-teal' },
  rejected: { label: '已拒绝', cls: 'bg-burgundy/10 text-burgundy' },
  refunded: { label: '已退款', cls: 'bg-ink/10 text-ink' },
  closed: { label: '已关闭', cls: 'bg-bg text-sub' },
}

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待审核' },
  { key: 'approved', label: '已通过' },
  { key: 'rejected', label: '已拒绝' },
  { key: 'refunded', label: '已退款' },
]

export function Aftersale() {
  const [status, setStatus] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [rejectTarget, setRejectTarget] = useState(null)
  const [rejectNote, setRejectNote] = useState('')
  const LIMIT = 20

  const load = useCallback(async (reset = true) => {
    setLoading(true)
    setErr('')
    try {
      const data = await merchantAftersales(status, LIMIT, reset ? 0 : items.length)
      if (reset) {
        setItems(data.aftersales || [])
      } else {
        setItems((prev) => [...prev, ...(data.aftersales || [])])
      }
      setTotal(data.total || 0)
    } catch (e) {
      setErr(e.message || '售后单加载失败')
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    load(true)
  }, [load])

  const act = async (asId, fn, okMsg) => {
    if (busy) return
    setBusy(asId)
    setMsg('')
    setErr('')
    try {
      await fn(asId)
      setMsg(okMsg)
      load(true)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy('')
    }
  }

  const doApprove = (asId) => act(asId, merchantApproveAftersale, '已通过')
  const doRefund = (asId) => act(asId, merchantRefundAftersale, '退款成功')
  const doReject = async () => {
    if (!rejectTarget || busy) return
    setBusy(rejectTarget)
    setMsg('')
    setErr('')
    try {
      await merchantRejectAftersale(rejectTarget, rejectNote)
      setMsg('已拒绝')
      setRejectTarget(null)
      setRejectNote('')
      load(true)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">售后处理</h2>
      <p className="mt-1 text-[12px] text-sub">本店售后审核：通过 / 拒绝 / 退款</p>

      <div className="mt-4 flex gap-1.5">
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

      {msg && <p className="mt-3 text-[12px] text-[#5b8a6a]">{msg}</p>}
      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      <div className="mt-4 space-y-3">
        {loading ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : items.length === 0 ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">暂无售后单</p>
        ) : (
          items.map((a) => {
            const t = TYPE_META[a.type] || { label: a.type, cls: 'bg-bg text-sub' }
            const s = STATUS_META[a.status] || { label: a.status, cls: 'bg-bg text-sub' }
            const isPending = a.status === 'pending'
            return (
              <div key={a.id} className="rounded-card border border-line bg-white p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] ${t.cls}`}>{t.label}</span>
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] ${s.cls}`}>{s.label}</span>
                  </div>
                  <span className="text-[12px] text-ink">{fmtMoney(a.refund_amount ?? a.order_total)}</span>
                </div>
                <p className="mt-2 text-[11px] text-sub">{a.order_id} · {a.created_at?.replace('T', ' ').slice(0, 16)}</p>
                {a.reason && <p className="mt-1 text-[12px] text-ink">原因：{a.reason}</p>}
                {a.description && <p className="mt-1 text-[11px] text-sub">{a.description}</p>}
                {a.review_note && (
                  <p className="mt-2 rounded-[2px] bg-bg/50 px-2 py-1 text-[11px] text-burgundy">审核备注：{a.review_note}</p>
                )}
                {Array.isArray(a.evidence_imgs) && a.evidence_imgs.length > 0 && (
                  <div className="mt-2 flex gap-2">
                    {a.evidence_imgs.map((src) => (
                      <img key={src} src={src} alt="凭证" className="h-16 w-16 rounded-[2px] border border-line object-cover" />
                    ))}
                  </div>
                )}
                {isPending && (
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={() => doApprove(a.id)}
                      disabled={!!busy}
                      className="press rounded-[2px] border border-[#5b8a6a]/40 bg-white px-3 py-1.5 text-[11px] text-[#5b8a6a] disabled:opacity-40"
                    >
                      通过
                    </button>
                    <button
                      onClick={() => doRefund(a.id)}
                      disabled={!!busy}
                      className="press rounded-[2px] bg-gold px-3 py-1.5 text-[11px] text-[#FAF8F5] disabled:opacity-40"
                    >
                      {busy === a.id ? '处理中…' : '直接退款'}
                    </button>
                    <button
                      onClick={() => { setRejectTarget(a.id); setRejectNote('') }}
                      disabled={!!busy}
                      className="press rounded-[2px] border border-burgundy/40 bg-white px-3 py-1.5 text-[11px] text-burgundy disabled:opacity-40"
                    >
                      拒绝
                    </button>
                  </div>
                )}
              </div>
            )
          })
        )}
        {!loading && items.length < total && (
          <button
            onClick={() => load(false)}
            className="w-full rounded-card border border-line bg-white py-3 text-center text-[12px] text-sub transition hover:bg-bg"
          >
            加载更多（{items.length}/{total}）
          </button>
        )}
      </div>

      {rejectTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setRejectTarget(null)}>
          <div className="w-[320px] rounded-card bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-[14px] font-medium text-ink">拒绝原因</p>
            <textarea
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
              placeholder="填写拒绝原因（选填）"
              rows={3}
              className="mt-3 w-full rounded-[2px] border border-line px-3 py-2 text-[12px]"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button onClick={() => setRejectTarget(null)} className="rounded-[2px] border border-line px-3 py-1.5 text-[11px] text-sub">取消</button>
              <button onClick={doReject} disabled={!!busy} className="rounded-[2px] bg-burgundy px-3 py-1.5 text-[11px] text-white disabled:opacity-40">
                {busy ? '提交中…' : '确认拒绝'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
