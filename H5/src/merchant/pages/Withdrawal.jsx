// 商家提现：发起提现申请 + 查看提现记录（资金结算由平台线下完成）。
import React, { useCallback, useEffect, useState } from 'react'
import { merchantApplyWithdrawal, merchantWithdrawals } from '../api'
import { fmtMoney } from '../../utils/price'

const ACCOUNT_META = {
  wechat: { label: '微信', placeholder: '微信收款账号 / 手机号' },
  alipay: { label: '支付宝', placeholder: '支付宝账号 / 手机号' },
  bank: { label: '银行卡', placeholder: '开户行 + 卡号 + 持卡人' },
}

const STATUS_META = {
  pending: { label: '待审核', cls: 'bg-gold/15 text-gold' },
  approved: { label: '已通过·待打款', cls: 'bg-teal/15 text-teal' },
  paid: { label: '已打款', cls: 'bg-ink/10 text-ink' },
  rejected: { label: '已拒绝', cls: 'bg-burgundy/10 text-burgundy' },
}

export function Withdrawal() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [showForm, setShowForm] = useState(false)

  // 表单态
  const [amount, setAmount] = useState('')
  const [accountType, setAccountType] = useState('wechat')
  const [account, setAccount] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [formMsg, setFormMsg] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const list = await merchantWithdrawals(50, 0)
      setItems(list)
    } catch (e) {
      setErr(e.message || '提现记录加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const submit = async () => {
    setFormMsg('')
    const amt = Number(amount)
    if (!amt || amt <= 0) {
      setFormMsg('请输入大于 0 的提现金额')
      return
    }
    if (!account.trim()) {
      setFormMsg('请填写收款账号信息')
      return
    }
    setBusy(true)
    try {
      await merchantApplyWithdrawal({
        amount: amt,
        account_type: accountType,
        account: account.trim(),
        note: note.trim(),
      })
      setFormMsg('提现申请已提交，等待平台审核')
      setAmount('')
      setAccount('')
      setNote('')
      setShowForm(false)
      load()
    } catch (e) {
      setFormMsg(e.message || '提交失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif-cn text-[22px] font-normal text-ink">余额提现</h2>
          <p className="mt-1 text-[12px] text-sub">发起提现申请，资金由平台线下结算打款</p>
        </div>
        <button
          onClick={() => {
            setShowForm((v) => !v)
            setFormMsg('')
          }}
          className="press rounded-[2px] bg-gold px-4 py-2 text-[12px] tracking-[1px] text-[#FAF8F5]"
        >
          {showForm ? '取消' : '申请提现'}
        </button>
      </div>

      {showForm && (
        <div className="mt-4 rounded-card border border-line bg-white p-4">
          <div className="space-y-3">
            <div>
              <label className="text-[11px] text-sub">提现金额（元）</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                className="maison-field mt-1 w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[14px] outline-none focus:border-gold"
              />
            </div>
            <div>
              <label className="text-[11px] text-sub">收款方式</label>
              <div className="mt-1 flex gap-1.5">
                {Object.entries(ACCOUNT_META).map(([k, m]) => (
                  <button
                    key={k}
                    onClick={() => setAccountType(k)}
                    className={`flex-1 rounded-full border py-1.5 text-center text-[11px] transition ${
                      accountType === k ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[11px] text-sub">收款账号</label>
              <input
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                placeholder={ACCOUNT_META[accountType].placeholder}
                className="maison-field mt-1 w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px] outline-none focus:border-gold"
              />
            </div>
            <div>
              <label className="text-[11px] text-sub">备注（选填）</label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={200}
                rows={2}
                placeholder="如：对公账户、到账时效要求等"
                className="maison-field mt-1 w-full resize-none rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px] outline-none focus:border-gold"
              />
            </div>
            {formMsg && <p className="text-[12px] text-burgundy">{formMsg}</p>}
            <button
              onClick={submit}
              disabled={busy}
              className="press w-full rounded-[2px] bg-gold py-2.5 text-[13px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
            >
              {busy ? '提交中…' : '提交申请'}
            </button>
          </div>
        </div>
      )}

      <div className="mt-5 space-y-3">
        {loading ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : err ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-burgundy">{err}</p>
        ) : items.length === 0 ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">暂无提现记录</p>
        ) : (
          items.map((w) => {
            const s = STATUS_META[w.status] || { label: w.status, cls: 'bg-bg text-sub' }
            return (
              <div key={w.id} className="rounded-card border border-line bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className={`rounded-pill px-2 py-0.5 text-[10px] ${s.cls}`}>{s.label}</span>
                  <span className="font-serif-cn text-[16px] text-ink">{fmtMoney(w.amount)}</span>
                </div>
                <p className="mt-2 text-[11px] text-sub">
                  {ACCOUNT_META[w.account_type]?.label || w.account_type} · {w.created_at?.replace('T', ' ').slice(0, 16)}
                </p>
                {w.account && <p className="mt-1 text-[11px] text-sub">收款：{w.account}</p>}
                {w.review_note && (
                  <p className="mt-2 rounded-[2px] bg-bg/50 px-2 py-1 text-[11px] text-burgundy">备注：{w.review_note}</p>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
