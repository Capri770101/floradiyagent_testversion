// 我的售后（M4 用户侧）：售后单列表与状态。
import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { myAftersales } from '../api/shop'

const AS_STATUS = {
  pending: { label: '待审核', cls: 'bg-pink/10 text-pink' },
  approved: { label: '已通过', cls: 'bg-gold/15 text-gold-dark' },
  rejected: { label: '已拒绝', cls: 'bg-line/40 text-sub' },
  refunded: { label: '已退款', cls: 'bg-green/20 text-[#5b8a6a]' },
  closed: { label: '已关闭', cls: 'bg-line/40 text-sub' },
}
const AS_TYPE = { refund: '退款', return: '退货', exchange: '换货' }

export default function MyAftersales() {
  const nav = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    myAftersales()
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="我的售后" />
      <div className="flex-1 overflow-y-auto px-4 pb-8">
        {loading ? (
          <p className="mt-6 rounded-card bg-white p-8 text-center text-[12px] text-sub border border-line">加载中…</p>
        ) : rows.length === 0 ? (
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
        ) : (
          <div className="mt-3 space-y-3">
            {rows.map((a) => {
              const m = AS_STATUS[a.status] || { label: a.status, cls: 'bg-line/40 text-sub' }
              return (
                <div key={a.id} className="rounded-card bg-white p-4 border border-line">
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
                    {a.review_note && <p className="text-burgundy">平台备注：{a.review_note}</p>}
                  </div>
                  <p className="mt-2 border-t border-line pt-2 text-[10px] text-sub/70">{a.created_at}</p>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
