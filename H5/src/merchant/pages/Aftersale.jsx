// 商家售后查看：本店售后单只读列表（处理动作在平台管理端完成）。
import React, { useCallback, useEffect, useState } from 'react'
import { merchantAftersales } from '../api'
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
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const data = await merchantAftersales(status)
      setItems(data.aftersales || [])
    } catch (e) {
      setErr(e.message || '售后单加载失败')
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">售后处理</h2>
      <p className="mt-1 text-[12px] text-sub">
        本店售后单查询（通过/拒绝/退款由平台管理端统一处理）
      </p>

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
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}