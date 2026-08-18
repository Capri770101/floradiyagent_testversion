// 售后管理（M4）：列表 + 审核（通过 / 拒绝 / 退款，payments sandbox 联动）。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Pager } from '../App'

const AS_STATUS = {
  pending: { label: '待审核', cls: 'bg-pink/10 text-pink' },
  approved: { label: '已通过', cls: 'bg-gold/15 text-gold-dark' },
  rejected: { label: '已拒绝', cls: 'bg-line/40 text-sub' },
  refunded: { label: '已退款', cls: 'bg-[#5b8a6a]/15 text-[#5b8a6a]' },
  closed: { label: '已关闭', cls: 'bg-line/40 text-sub' },
}
const AS_TYPE = { refund: '退款', return: '退货', exchange: '换货' }

export function Aftersales() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [limit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [detail, setDetail] = useState(null)
  const [rejectNote, setRejectNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const data = await api.get('/admin/aftersales', { status, limit, offset })
    setRows(data.aftersales)
    setTotal(data.total)
  }, [status, limit, offset])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const openDetail = (a) => {
    setDetail(a)
    setRejectNote('')
  }

  const act = async (asId, path, body, okMsg) => {
    if (busy) return
    setBusy(asId)
    setMsg('')
    try {
      await api.post(`/admin/aftersales/${asId}/${path}`, body || {})
      setMsg(okMsg)
      setDetail(null)
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">售后管理</h2>
      <p className="mt-1 text-[12px] text-sub">审核退款 / 退货 / 换货申请（退款为沙箱模拟，生产接支付网关）</p>

      <div className="mt-4 flex items-center gap-2">
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setOffset(0)
          }}
          className="rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        >
          <option value="">全部状态</option>
          {Object.entries(AS_STATUS).map(([k, m]) => (
            <option key={k} value={k}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
        <table className="w-full min-w-[780px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
              <th className="px-4 py-3">售后单</th>
              <th className="px-4 py-3">订单号</th>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">申请人</th>
              <th className="px-4 py-3">原因</th>
              <th className="px-4 py-3">订单金额</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">提交时间</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const m = AS_STATUS[a.status] || { label: a.status, cls: 'bg-line/40 text-sub' }
              return (
                <tr key={a.id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3 text-ink">{a.id}</td>
                  <td className="px-4 py-3 text-sub">{a.order_id}</td>
                  <td className="px-4 py-3">{AS_TYPE[a.type] || a.type}</td>
                  <td className="px-4 py-3">{a.nickname || '—'}</td>
                  <td className="max-w-[200px] px-4 py-3">
                    <p className="truncate">{a.reason || '—'}</p>
                  </td>
                  <td className="px-4 py-3">{a.order_total ? `¥${Number(a.order_total).toFixed(2)}` : '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-pill px-2 py-0.5 text-[11px] ${m.cls}`}>{m.label}</span>
                  </td>
                  <td className="px-4 py-3 text-sub">{a.created_at}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => openDetail(a)}
                      className="press rounded-[2px] border border-gold/40 bg-white px-2.5 py-1 text-[11px] text-gold"
                    >
                      审核
                    </button>
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-sub">
                  没有售后单
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Pager offset={offset} total={total} limit={limit} onChange={setOffset} />

      {/* 审核抽屉 */}
      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setDetail(null)}>
          <div
            className="h-full w-[420px] overflow-y-auto bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-serif-cn text-[18px] font-normal text-ink">售后审核</h3>
              <button onClick={() => setDetail(null)} className="press text-[12px] text-sub">
                关闭 ✕
              </button>
            </div>
            <p className="mt-1 text-[11px] text-sub">
              {detail.id} · 订单 {detail.order_id}
            </p>

            <p className="eyebrow mt-5">申请信息</p>
            <div className="mt-2 space-y-1 rounded-[2px] bg-bg px-3 py-2 text-[12px]">
              <p>
                类型：<span className="text-ink">{AS_TYPE[detail.type] || detail.type}</span>
                <span className="ml-2 rounded-pill bg-pink/10 px-2 py-0.5 text-[11px] text-pink">
                  {(AS_STATUS[detail.status] || {}).label || detail.status}
                </span>
              </p>
              <p>
                申请人：{detail.nickname || '—'} {detail.phone || ''}
              </p>
              <p>原因：{detail.reason || '—'}</p>
              {detail.description && <p className="text-sub">描述：{detail.description}</p>}
              <p>订单金额：{detail.order_total ? `¥${Number(detail.order_total).toFixed(2)}` : '—'}</p>
              {detail.review_note && <p className="text-sub">审核备注：{detail.review_note}</p>}
            </div>

            {(detail.evidence_imgs || []).length > 0 && (
              <>
                <p className="eyebrow mt-5">凭证图片</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {detail.evidence_imgs.map((img, i) => (
                    <img
                      key={i}
                      src={img}
                      alt="凭证"
                      className="h-[72px] w-[72px] rounded-[4px] border border-line object-cover"
                    />
                  ))}
                </div>
              </>
            )}

            {detail.status === 'pending' && (
              <>
                <p className="eyebrow mt-5">拒绝备注</p>
                <textarea
                  value={rejectNote}
                  onChange={(e) => setRejectNote(e.target.value)}
                  maxLength={500}
                  placeholder="填写拒绝原因（可选）"
                  className="maison-field mt-2 w-full resize-none rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]"
                  rows={2}
                />
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <button
                    onClick={() => act(detail.id, 'approve', {}, '已通过，等待退款')}
                    disabled={busy}
                    className="press rounded-[2px] border border-gold/40 bg-white py-2 text-[12px] text-gold disabled:opacity-40"
                  >
                    通过
                  </button>
                  <button
                    onClick={() => act(detail.id, 'reject', { note: rejectNote }, '已拒绝')}
                    disabled={busy}
                    className="press rounded-[2px] border border-line bg-white py-2 text-[12px] text-sub disabled:opacity-40"
                  >
                    拒绝
                  </button>
                  <button
                    onClick={() => act(detail.id, 'refund', {}, '已退款（沙箱）')}
                    disabled={busy}
                    className="press rounded-[2px] bg-gold py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                  >
                    直接退款
                  </button>
                </div>
              </>
            )}

            {detail.status !== 'pending' && (
              <p className="mt-5 text-[12px] text-sub">
                {detail.handled_by ? `处理人：${detail.handled_by}` : ''}
                {detail.handled_at ? ` · ${detail.handled_at}` : ''}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
