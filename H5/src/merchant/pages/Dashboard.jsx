// 商家数据看板：/merchant/stats 统计看板 + 门店列表；阶段3a: 首页统计；3b: 门店经营数据概览页面
import React, { useCallback, useEffect, useState } from 'react'
import { merchantStats } from '../api'
import { fmtMoney } from '../../utils/price'
import { useNavigate } from 'react-router-dom'

export default function MerchantDashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const nav = useNavigate()

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await merchantStats()
      setStats(data)
    } catch (e) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="flex h-full items-center justify-center text-sub">加载中...</div>
  if (error) return <div className="flex h-full items-center justify-center text-burgundy">{error}</div>

  return (
    <div className="p-4 pb-24">
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">经营概览</h2>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-card border border-line bg-white p-4">
          <p className="text-[11px] text-sub">今日订单</p>
          <p className="mt-1 text-[24px] font-medium text-ink">{stats?.today_orders ?? 0}</p>
        </div>
        <div className="rounded-card border border-line bg-white p-4">
          <p className="text-[11px] text-sub">今日收入</p>
          <p className="mt-1 text-[24px] font-medium text-ink">{fmtMoney(stats?.today_revenue ?? 0)}</p>
        </div>
        <div className="rounded-card border border-line bg-white p-4">
          <p className="text-[11px] text-sub">待处理订单</p>
          <p className="mt-1 text-[24px] font-medium text-gold">{stats?.pending_orders ?? 0}</p>
        </div>
        <div className="rounded-card border border-line bg-white p-4">
          <p className="text-[11px] text-sub">在售商品</p>
          <p className="mt-1 text-[24px] font-medium text-ink">{stats?.active_plans ?? 0}</p>
        </div>
      </div>

      <div className="mt-6 space-y-2">
        <h3 className="text-[14px] font-medium text-ink">快捷操作</h3>
        <button onClick={() => nav('/merchant/orders')} className="w-full rounded-card border border-line bg-white p-3 text-left text-[13px] text-ink">订单管理</button>
        <button onClick={() => nav('/merchant/products')} className="w-full rounded-card border border-line bg-white p-3 text-left text-[13px] text-ink">商品管理</button>
        <button onClick={() => nav('/merchant/aftersale')} className="w-full rounded-card border border-line bg-white p-3 text-left text-[13px] text-ink">售后管理</button>
      </div>
    </div>
  )
}
