// 提现管理：列表 + 审核（通过 / 标记已打款 / 拒绝）。资金由平台线下结算。
import React, { useCallback, useEffect, useState } from 'react'
import { adminWithdrawals, adminWithdrawalAct } from '../api'
import { Pager } from '../App'

const W_STATUS = {
  pending: { label: '待审核', cls: 'bg-gold/15 text-gold' },
  approved: { label: '已通过·待打款', cls: 'bg-teal/15 text-teal' },
  paid: { label: '已打款', cls: 'bg-ink/10 text-ink' },
  rejected: { label: '已拒绝', cls: 'bg-line/40 text-sub' },
}
const W_ACCOUNT = { wechat: '微信', alipay: '支付宝', bank: '银行卡' }

export function Withdrawals() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [limit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [detail, setDetail] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const data = await adminWithdrawals(status, limit, offset)
    setRows(data.withdrawals)
    setTotal(data.total)
  }, [status, limit, offset])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const openDetail = (w) => {
    setDetail(w)
    setNote('')
    setMsg('')
  }

  const act = async (wdId, action, okMsg) => {
    if (busy) return
    setBusy(true)
    setMsg('')
    try {
      await adminWithdrawalAct(wdId, action, note.trim())
      setMsg(okMsg)
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
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">提现管理</h2>
      <p className="mt-1 text-[12px] text-sub">审核商家提现申请（资金结算为线下打款，此处仅登记流转）</p>

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
          {Object.entries(W_STATUS).map(([k, m]) => (
            <option key={k} value={k}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
        <table className="w-full min-w-[820px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
              <th className="px-4 py-3">提现单</th>
              <th className="px-4 py-3">店铺</th>
              <th className="px-4 py-3">商家</th>
              <th className="px-4 py-3">金额</th>
              <th className="px-4 py-3">收款方式</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">提交时间</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((w) => {
              const m = W_STATUS[w.status] || { label: w.status, cls: 'bg-line/40 text-sub' }
              return (
                <tr key={w.id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3 text-ink">{w.id}</td>
                  <td className="px-4 py-3">{w.shop_name || w.shop_id || '—'}</td>
                  <td className="px-4 py-3">{w.nickname || '—'}</td>
                  <td className="px-4 py-3 text-ink">¥{Number(w.amount).toFixed(2)}</td>
                  <td className="px-4 py-3">{W_ACCOUNT[w.account_type] || w.account_type}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-pill px-2 py-0.5 text-[11px] ${m.cls}`}>{m.label}</span>
                  </td>
                  <td className="px-4 py-3 text-sub">{w.created_at}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => openDetail(w)}
                      className="press rounded-[2px] border border-gold/40 bg-white px-2.5 py-1 text-[11px] text-gold"
                    >
                      处理
                    </button>
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sub">
                  没有提现申请
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Pager offset={offset} total={total} limit={limit} onChange={setOffset} />

      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setDetail(null)}>
          <div
            className="h-full w-[420px] overflow-y-auto bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-serif-cn text-[18px] font-normal text-ink">提现处理</h3>
              <button onClick={() => setDetail(null)} className="press text-[12px] text-sub">
                关闭 ✕
              </button>
            </div>
            <p className="mt-1 text-[11px] text-sub">{detail.id}</p>

            <p className="eyebrow mt-5">申请信息</p>
            <div className="mt-2 space-y-1 rounded-[2px] bg-bg px-3 py-2 text-[12px]">
              <p>
                店铺：<span className="text-ink">{detail.shop_name || detail.shop_id || '—'}</span>
                <span className="ml-2 rounded-pill bg-gold/15 px-2 py-0.5 text-[11px] text-gold">
                  {(W_STATUS[detail.status] || {}).label || detail.status}
                </span>
              </p>
              <p>商家：{detail.nickname || '—'} {detail.phone || ''}</p>
              <p>金额：¥{Number(detail.amount).toFixed(2)}</p>
              <p>收款方式：{W_ACCOUNT[detail.account_type] || detail.account_type}</p>
              {detail.account && <p>收款账号：{detail.account}</p>}
              {detail.review_note && <p className="text-sub">备注：{detail.review_note}</p>}
            </div>

            {detail.status === 'pending' && (
              <>
                <p className="eyebrow mt-5">审核备注 / 打款凭证号</p>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={500}
                  placeholder="拒绝时填原因；打款后填转账凭证号（选填）"
                  className="maison-field mt-2 w-full resize-none rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]"
                  rows={2}
                />
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <button
                    onClick={() => act(detail.id, 'approve', '已通过，等待打款')}
                    disabled={busy}
                    className="press rounded-[2px] border border-gold/40 bg-white py-2 text-[12px] text-gold disabled:opacity-40"
                  >
                    通过
                  </button>
                  <button
                    onClick={() => act(detail.id, 'reject', '已拒绝')}
                    disabled={busy}
                    className="press rounded-[2px] border border-line bg-white py-2 text-[12px] text-sub disabled:opacity-40"
                  >
                    拒绝
                  </button>
                  <button
                    onClick={() => act(detail.id, 'paid', '已标记打款')}
                    disabled={busy}
                    className="press rounded-[2px] bg-gold py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                  >
                    标记打款
                  </button>
                </div>
              </>
            )}

            {detail.status === 'approved' && (
              <>
                <p className="eyebrow mt-5">打款凭证号</p>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={500}
                  placeholder="填写平台转账凭证号后标记已打款"
                  className="maison-field mt-2 w-full resize-none rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]"
                  rows={2}
                />
                <button
                  onClick={() => act(detail.id, 'paid', '已标记打款')}
                  disabled={busy}
                  className="press mt-3 w-full rounded-[2px] bg-gold py-2 text-[13px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                >
                  标记已打款
                </button>
              </>
            )}

            {detail.status !== 'pending' && detail.status !== 'approved' && (
              <p className="mt-5 text-[12px] text-sub">
                {detail.handled_by ? `处理人：${detail.handled_by}` : ''}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
