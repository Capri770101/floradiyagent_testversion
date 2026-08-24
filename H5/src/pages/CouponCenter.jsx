import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import Reveal from '../components/Reveal'
import { toast } from '../utils/toast'
import { listCoupons, getPoints, listCouponOffers, claimCouponOffer } from '../api/shop'
import { isLoggedIn } from '../api/auth'

// 领券中心：免费领 + 积分兑换（积分商城）；我的券 tab 展示持有与使用状态
// 支持 ?tab=mine / ?tab=offers 直达（个人中心「优惠券/积分」模块卡跳转用）
export default function CouponCenter() {
  const nav = useNavigate()
  const location = useLocation()
  const [tab, setTab] = useState(() =>
    new URLSearchParams(location.search).get('tab') === 'mine' ? 'mine' : 'offers',
  )
  const [offers, setOffers] = useState([])
  const [coupons, setCoupons] = useState([])
  const [points, setPoints] = useState(0)
  const [busyId, setBusyId] = useState('')
  const loggedIn = isLoggedIn()

  const loadOffers = useCallback(async () => {
    try {
      const data = await listCouponOffers()
      setOffers(data.offers || [])
    } catch (e) {
      toast(e.message || '加载失败', 'error')
    }
  }, [])

  const loadMine = useCallback(async () => {
    if (!loggedIn) return
    try {
      const [cs, ps] = await Promise.all([listCoupons(), getPoints()])
      setCoupons(cs)
      setPoints(ps.balance || 0)
    } catch (e) {
      toast(e.message || '加载失败', 'error')
    }
  }, [loggedIn])

  useEffect(() => {
    loadOffers()
  }, [loadOffers])

  useEffect(() => {
    if (loggedIn) loadMine()
  }, [loggedIn, loadMine])

  const claim = async (offer) => {
    if (!loggedIn) {
      nav('/profile', { state: { from: '/coupons' } })
      return
    }
    if (busyId) return
    setBusyId(offer.id)
    try {
      const coupon = await claimCouponOffer(offer.id)
      toast(offer.points_cost > 0 ? `兑换成功：${coupon.title}` : `领取成功：${coupon.title}`)
      await Promise.all([loadOffers(), loadMine()])
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="领券中心" />
      <div className="flex gap-2 px-4 pt-4">
        <Button variant={tab === 'offers' ? 'primary' : 'secondary'} className="flex-1" onClick={() => setTab('offers')}>
          领券中心
        </Button>
        <Button variant={tab === 'mine' ? 'primary' : 'secondary'} className="flex-1" onClick={() => setTab('mine')}>
          我的券（{coupons.length}）
        </Button>
      </div>
      {loggedIn && tab === 'mine' && (
        <p className="px-4 pt-3 text-[11px] text-sub">当前积分：{points}（支付每 ¥1 返 1 积分）</p>
      )}
      <div className="flex-1 overflow-y-auto px-4 pt-3 pb-6">
        {tab === 'offers' ? (
          offers.length === 0 ? (
            <Reveal>
              <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
                暂无可领取的优惠券
              </p>
            </Reveal>
          ) : (
            offers.map((o, i) => {
              const soldOut = o.stock === 0
              return (
                <Reveal key={o.id} delay={i * 140}>
                  <div className="mb-3 flex items-center gap-3 rounded-card bg-white p-4 border border-line">
                    <div className="min-w-0 flex-1">
                      <p className="text-[14px] font-medium text-dark">{o.title}</p>
                      <p className="mt-0.5 text-[11px] text-sub">
                        {o.min_spend > 0 ? `满 ¥${o.min_spend} 可用` : '无门槛'}
                        {o.points_cost > 0 ? ` · ${o.points_cost} 积分` : ' · 免费领取'}
                        {o.stock > 0 ? ` · 剩 ${o.stock}` : o.stock === 0 ? ' · 已抢光' : ''}
                      </p>
                      <p className="mt-0.5 text-[16px] font-medium text-ink">¥{Number(o.discount).toFixed(2)}</p>
                    </div>
                    <Button
                      className="!h-[30px] !rounded-pill !px-4 !text-[12px]"
                      disabled={o.claimed || soldOut || busyId === o.id}
                      onClick={() => claim(o)}
                    >
                      {o.claimed ? '已领取' : soldOut ? '已抢光' : o.points_cost > 0 ? '积分兑换' : '立即领取'}
                    </Button>
                  </div>
                </Reveal>
              )
            })
          )
        ) : loggedIn ? (
          coupons.length === 0 ? (
            <Reveal>
              <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
                还没有优惠券，去领券中心看看吧
              </p>
            </Reveal>
          ) : (
            coupons.map((c, i) => (
              <Reveal key={c.id} delay={i * 140}>
                <div className="mb-3 flex items-center justify-between rounded-card bg-white p-4 border border-line">
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-dark">{c.title}</p>
                    <p className="mt-0.5 text-[11px] text-sub">
                      {c.min_spend > 0 ? `满 ¥${c.min_spend} 可用` : '无门槛'}
                      {c.order_id ? ` · 订单 ${c.order_id}` : ''}
                    </p>
                    <p className="mt-0.5 text-[14px] font-medium text-ink">¥{Number(c.discount).toFixed(2)}</p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] ${
                      c.status === 'unused' ? 'bg-pink/10 text-pink' : 'bg-line text-sub'
                    }`}
                  >
                    {c.status === 'unused' ? '未使用' : '已使用'}
                  </span>
                </div>
              </Reveal>
            ))
          )
        ) : (
          <Reveal>
            <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
              登录后查看我的券
            </p>
          </Reveal>
        )}
      </div>
    </div>
  )
}