// 内容举报弹层（阶段5 内容审核体系）：商品/店铺/评价共用。
// 提交 POST /reports（需登录；未登录时后端 401，api 封装统一跳登录）。
import React, { useState } from 'react'
import { submitReport } from '../api/shop'

const REASONS = ['涉嫌违禁/敏感内容', '虚假宣传', '侵权盗图', '价格欺诈', '其他']

export default function ReportDialog({ open, onClose, targetType, targetId, targetTitle }) {
  const [reason, setReason] = useState('')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  if (!open) return null

  const submit = async () => {
    if (!reason) {
      setErr('请选择举报原因')
      return
    }
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await submitReport({ target_type: targetType, target_id: targetId, reason, content })
      onClose()
      setReason('')
      setContent('')
      window.alert('举报已提交，平台将尽快核实处理')
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
      onClick={() => !busy && onClose()}
    >
      <div
        className="w-full rounded-t-[12px] bg-white px-5 pb-8 pt-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1 w-9 rounded bg-line" />
        <p className="font-serif-cn text-[18px] font-normal text-ink">举报</p>
        <p className="mt-1 text-[11px] text-sub">{targetTitle}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {REASONS.map((r) => (
            <button
              key={r}
              onClick={() => {
                setReason(r)
                setErr('')
              }}
              className={`press rounded-pill px-3 py-1.5 text-[12px] ${
                reason === r ? 'bg-gold/15 font-medium text-gold' : 'border border-line text-sub'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          maxLength={500}
          placeholder="补充说明（选填，最多 500 字）"
          className="mt-3 h-20 w-full resize-none rounded-[4px] border border-line bg-bg/40 px-3 py-2 text-[12px] outline-none focus:border-gold"
        />
        {err && <p className="mt-2 text-[11px] text-burgundy">{err}</p>}
        <button
          onClick={submit}
          disabled={busy}
          className="press mt-4 w-full rounded-[4px] bg-pink py-2.5 text-[13px] tracking-[2px] text-white disabled:opacity-50"
        >
          {busy ? '提交中…' : '提交举报'}
        </button>
      </div>
    </div>
  )
}