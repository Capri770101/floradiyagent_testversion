// 商家数据看板：/merchant/stats 大数字卡 + 店铺列表（阶段3a 首屏，3b 并入更多业务页）。
import React, { useCallback, useEffect, useState } from 'react'
import { merchantStats } from '../api'
import { fmtMoney } from '../../utils/price'

export function Dashboard() {
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    setErr('')
    try {
      setStats(await merchantStats())
    } catch (e) {
      setErr(e.message || '加载失败')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (err) {
    return <p className="text-[12px] text-burgundy">{err}</p>
  }
  if (!stats) {
    return <p className="text-[12px] text-sub">加载中…</p>
  }

  const cards = [
    { label: '累计订单', value: String(stats.order_count) },
    { label: '累计 GMV', value: fmtMoney(stats.gmv) },
    { label: '待发货', value: String(stats.pending_ship) },
    { label: '待付款', value: String(stats.pending_payment) },
    { label: '今日订单', value: String(stats.today_order_count) },
    { label: '今日 GMV', value: fmtMoney(stats.today_gmv) },
    { label: '已完成', value: String(stats.done_count) },
    { label: '评价均分', value: Number(stats.avg_rating).toFixed(1) },
  ]

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">数据看板</h2>
      <p className="mt-1 text-[12px] text-sub">按当前账号绑定的店铺维度统计</p>

      <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-card border border-line bg-white p-5">
            <p className="text-[11px] tracking-[1px] text-sub">{c.label}</p>
            <p className="mt-2 text-[22px] leading-none text-ink">{c.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-card border border-line bg-white p-5">
        <p className="text-[12px] font-medium text-ink">我的店铺</p>
        {stats.shops.length === 0 ? (
          <p className="mt-3 text-[12px] text-sub">暂无绑定店铺，请联系平台管理员开通</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {stats.shops.map((s) => (
              <li key={s.id} className="flex items-center justify-between rounded-[2px] border border-line px-3 py-2">
                <span className="text-[13px] text-ink">{s.name}</span>
                <span className="text-[11px] text-sub">月售 {s.sales ?? 0} · 评分 {Number(s.rating ?? 0).toFixed(1)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}