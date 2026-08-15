import React, { useEffect, useState, useCallback } from 'react'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { Pill } from '../components/Pill'
import { toast } from '../utils/toast'
import {
  merchantStats,
  merchantOrders,
  merchantShip,
  merchantReviews,
} from '../api/shop'
import { getProfile } from '../api/auth'

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '配送中' },
  { key: 'done', label: '已完成' },
  { key: 'canceled', label: '已取消' },
]

// 商家工作台：经营数据看板 + 订单管理（代发货）+ 评价列表
export default function Merchant() {
  const [profile, setProfile] = useState(null)
  const [forbidden, setForbidden] = useState(false)
  const [stats, setStats] = useState(null)
  const [orders, setOrders] = useState([])
  const [reviews, setReviews] = useState([])
  const [status, setStatus] = useState('')
  const [tab, setTab] = useState('orders')
  const [busyId, setBusyId] = useState('')

  useEffect(() => {
    getProfile().then(setProfile).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    try {
      const [st, os, rs] = await Promise.all([
        merchantStats(),
        merchantOrders('', status),
        merchantReviews(),
      ])
      setStats(st)
      setOrders(os)
      setReviews(rs)
      setForbidden(false)
    } catch (e) {
      if (/403/.test(e.message)) {
        setForbidden(true)
      } else {
        toast(e.message || '加载失败', 'error')
      }
    }
  }, [status])

  useEffect(() => {
    load()
  }, [load])

  const ship = async (oid) => {
    if (busyId) return
    setBusyId(oid)
    try {
      await merchantShip(oid)
      toast('已代发货')
      load()
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setBusyId('')
    }
  }

  if (forbidden) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="商家工作台" />
        <div className="flex-1 px-5 pt-10 text-center">
          <p className="rounded-card bg-white p-8 text-[13px] text-sub border border-line">
            无商家权限
            <br />
            <span className="mt-1 block text-[11px] text-sub/70">
              仅 merchant / admin 角色可查看经营数据，请联系系统管理员授权
            </span>
          </p>
        </div>
      </div>
    )
  }

  const cards = [
    { label: '订单', value: stats?.order_count ?? '-' },
    { label: 'GMV', value: stats ? `¥${stats.gmv}` : '-' },
    { label: '待发货', value: stats?.pending_ship ?? '-' },
    { label: '已完成', value: stats?.done_count ?? '-' },
    { label: '评价', value: stats?.review_count ?? '-' },
  ]

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="商家工作台" />
      <div className="flex-1 overflow-y-auto px-4 pt-4 pb-6">
        <p className="text-[12px] text-sub">
          {profile?.nickname || profile?.username || '商家'} · 经营总览
        </p>
        <div className="mt-2 grid grid-cols-5 gap-2">
          {cards.map((c) => (
            <div key={c.label} className="rounded-card bg-white p-3 text-center border border-line">
              <p className="text-[15px] font-medium text-dark">{c.value}</p>
              <p className="mt-0.5 text-[10px] text-sub">{c.label}</p>
            </div>
          ))}
        </div>
        {stats?.shops?.length > 0 && (
          <p className="mt-3 text-[11px] text-sub">
            店铺：{stats.shops.map((s) => s.name || s).join(' / ')}
          </p>
        )}

        <div className="mt-5 flex gap-2">
          <Button variant={tab === 'orders' ? 'primary' : 'secondary'} className="flex-1" onClick={() => setTab('orders')}>
            订单管理
          </Button>
          <Button variant={tab === 'reviews' ? 'primary' : 'secondary'} className="flex-1" onClick={() => setTab('reviews')}>
            评价（{reviews.length}）
          </Button>
        </div>

        {tab === 'orders' ? (
          <>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {STATUS_TABS.map((t) => (
                <Pill
                  key={t.key}
                  label={t.label}
                  selected={status === t.key}
                  onClick={() => setStatus(t.key)}
                  style={{ width: 'auto', padding: '0 10px' }}
                />
              ))}
            </div>
            {orders.length === 0 ? (
              <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
                该状态下暂无订单
              </p>
            ) : (
              orders.map((o) => (
                <div key={o.order_id} className="mt-3 rounded-card bg-white p-4 border border-line">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-sub">{o.order_id}</span>
                    <span className="text-[11px] text-pink">{o.status}</span>
                  </div>
                  <p className="mt-1.5 text-[13px] font-medium text-dark">
                    {o.items?.[0]?.name || '花束'} × {o.items?.[0]?.qty || 1}
                  </p>
                  <p className="mt-0.5 text-[11px] text-sub">
                    ¥{Number(o.total_price || 0).toFixed(2)}
                    {o.shop_id ? ` · ${o.shop_id}` : ''}
                    {o.recipient?.name ? ` · ${o.recipient.name}` : ''}
                  </p>
                  <div className="mt-2 flex justify-end">
                    {o.status === 'paid' && (
                      <Button
                        className="!h-[30px] !rounded-pill !text-[12px]"
                        disabled={busyId === o.order_id}
                        onClick={() => ship(o.order_id)}
                      >
                        代发货
                      </Button>
                    )}
                  </div>
                </div>
              ))
            )}
          </>
        ) : reviews.length === 0 ? (
          <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
            暂无评价
          </p>
        ) : (
          reviews.map((r) => (
            <div key={r.id} className="mt-3 rounded-card bg-white p-4 border border-line">
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-medium text-dark">{r.nickname || '匿名用户'}</span>
                <span className="text-[11px] text-sub">{r.created_at}</span>
              </div>
              <p className="mt-1 text-[11px] text-sub">
                {'★'.repeat(r.rating)}
                {'☆'.repeat(5 - r.rating)}
                {r.plan_id ? ` · ${r.plan_id}` : ''}
              </p>
              {r.content && <p className="mt-1.5 text-[12px] leading-relaxed text-ink">{r.content}</p>}
            </div>
          ))
        )}
      </div>
    </div>
  )
}