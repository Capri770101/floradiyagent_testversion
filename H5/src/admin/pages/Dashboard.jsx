// 数据看板（M8）：GMV/订单/用户 统计卡 + 热销方案/店铺 + 订单趋势（自绘，无第三方图表库）。
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { fmtMoneyGrouped as fmtMoney } from '../../utils/price'

export function Dashboard() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const [days, setDays] = useState(7)

  useEffect(() => {
    api
      .get('/admin/dashboard', { days })
      .then(setD)
      .catch((e) => setMsg(e.message))
  }, [days])

  if (msg && !d) return <p className="text-[13px] text-burgundy">{msg}</p>
  if (!d) return <p className="text-[13px] text-sub">加载中…</p>

  const cards = [
    { label: '累计 GMV', value: fmtMoney(d.gmv) },
    { label: '订单总数', value: String(d.order_count) },
    { label: '注册用户', value: String(d.user_count) },
    { label: '今日新增用户', value: String(d.new_users_today), accent: true },
  ]
  const maxSold = Math.max(1, ...(d.top_plans || []).map((p) => p.sold))
  const maxSales = Math.max(1, ...(d.top_shops || []).map((s) => s.sales))
  const maxTrend = Math.max(1, ...(d.order_trend || []).map((t) => t.count))

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">数据看板</h2>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-[2px] border border-line bg-white px-3 py-1.5 text-[12px]"
        >
          <option value={7}>近 7 天</option>
          <option value={30}>近 30 天</option>
        </select>
      </div>

      <div className="mt-4 grid grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-card border border-line bg-white p-4 shadow-card">
            <p className="text-[10px] tracking-[0.15em] text-sub">{c.label}</p>
            <p className={`mt-1 font-serif-cn text-[24px] font-normal ${c.accent ? 'text-burgundy' : 'text-ink'}`}>
              {c.value}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <div className="rounded-card border border-line bg-white p-4 shadow-card">
          <p className="eyebrow">热销方案 TOP5</p>
          <div className="mt-3 space-y-2.5">
            {(d.top_plans || []).map((p) => (
              <div key={p.plan_id}>
                <div className="flex items-center justify-between text-[11px]">
                  <p className="truncate text-ink">{p.name}</p>
                  <p className="text-sub">{p.sold} 售</p>
                </div>
                <div className="mt-1 h-[6px] overflow-hidden rounded-full bg-line/30">
                  <div
                    className="h-full rounded-full bg-gold"
                    style={{ width: `${Math.max(4, (p.sold / maxSold) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
            {(d.top_plans || []).length === 0 && <p className="text-[12px] text-sub">暂无数据</p>}
          </div>
        </div>

        <div className="rounded-card border border-line bg-white p-4 shadow-card">
          <p className="eyebrow">热门店铺 TOP5</p>
          <div className="mt-3 space-y-2.5">
            {(d.top_shops || []).map((s) => (
              <div key={s.shop_id}>
                <div className="flex items-center justify-between text-[11px]">
                  <p className="truncate text-ink">{s.name}</p>
                  <p className="text-sub">月售 {s.sales}</p>
                </div>
                <div className="mt-1 h-[6px] overflow-hidden rounded-full bg-line/30">
                  <div
                    className="h-full rounded-full bg-burgundy/70"
                    style={{ width: `${Math.max(4, (s.sales / maxSales) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
            {(d.top_shops || []).length === 0 && <p className="text-[12px] text-sub">暂无数据</p>}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-card border border-line bg-white p-4 shadow-card">
        <p className="eyebrow">订单趋势（近 {days} 天）</p>
        {(d.order_trend || []).length === 0 ? (
          <p className="mt-3 text-[12px] text-sub">该区间暂无订单</p>
        ) : (
          <div className="mt-4 flex items-end gap-2">
            {(d.order_trend || []).map((t) => (
              <div key={t.date} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <p className="text-[10px] text-sub">{t.count}</p>
                <div
                  className="w-full rounded-t-[2px] bg-gold/80"
                  style={{ height: `${Math.max(6, (t.count / maxTrend) * 120)}px` }}
                  title={`${t.date} · ${t.count} 单 · ${fmtMoney(t.amount)}`}
                />
                <p className="text-[9px] text-sub/70">{t.date.slice(5)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
