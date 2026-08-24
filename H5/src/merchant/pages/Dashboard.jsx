import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { merchantStats, merchantShops } from '../../api/client'
import '../../App.css'

export default function MerchantDashboard() {
  const [stats, setStats] = useState(null)
  const [shops, setShops] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const nav = useNavigate()

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const [s, sh] = await Promise.all([merchantStats(), merchantShops()])
      setStats(s)
      setShops(sh)
    } catch (e) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="loading">加载中...</div>
  if (error) return <div className="error-msg">{error}</div>

  return (
    <div className="merchant-dashboard">
      <h2>商家后台</h2>
      {shops.length > 1 && (
        <div className="shop-switch">
          <span>当前店铺：</span>
          <select onChange={e => localStorage.setItem('merchant_shop', e.target.value)}>
            {shops.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      )}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-num">{stats?.total_orders ?? 0}</div>
          <div className="stat-label">总订单</div>
        </div>
        <div className="stat-card">
          <div className="stat-num">¥{stats?.total_revenue ?? 0}</div>
          <div className="stat-label">总收入</div>
        </div>
        <div className="stat-card">
          <div className="stat-num">{stats?.pending_orders ?? 0}</div>
          <div className="stat-label">待处理</div>
        </div>
        <div className="stat-card">
          <div className="stat-num">{stats?.total_plans ?? 0}</div>
          <div className="stat-label">商品数</div>
        </div>
      </div>
      <div className="quick-actions">
        <button onClick={() => nav('/merchant/orders')}>订单管理</button>
        <button onClick={() => nav('/merchant/products')}>商品管理</button>
        <button onClick={() => nav('/merchant/aftersale')}>售后管理</button>
      </div>
    </div>
  )
}