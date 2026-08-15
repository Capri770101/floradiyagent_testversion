import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import SmartImage from '../components/SmartImage'
import { Button } from '../components/Button'
import { IconArrow } from '../components/icons'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'
import SectionTitle from '../components/SectionTitle'
import { itemImagePath } from '../assets/imageMap'
import { toast } from '../utils/toast'
import { getLocation, setLocation } from '../utils/location'
import LocationPicker from '../components/LocationPicker'
import { listOrders, orderAction, listCoupons, getPoints, listFavorites, postReview } from '../api/shop'
import { IconStar } from '../components/icons'
import {
  isLoggedIn,
  getUserId,
  login,
  register,
  getProfile,
  clearSession,
} from '../api/auth'

// 08 我的
const STATUS_META = {
  created: { label: '待付款', color: 'text-pink' },
  pending_payment: { label: '待付款', color: 'text-pink' },
  paid: { label: '待发货', color: 'text-amber-600' },
  shipped: { label: '配送中', color: 'text-blue-600' },
  done: { label: '已完成', color: 'text-green-600' },
  canceled: { label: '已取消', color: 'text-sub' },
}

// 本地静态展示数据（不再依赖 data/mock，避免 review 点名的「Profile 全 mock」）
const STATS = [
  { label: '收藏', value: 0 },
  { label: '订单', value: 0 },
  { label: '优惠券', value: 0 },
  { label: '积分', value: 0 },
]
const FUNCTIONS = [
  { label: '我的收藏', path: '/favorites' },
  { label: '我的地址', path: '/addresses' },
  { label: '领券中心', path: '/coupons' },
  { label: '客服中心', path: '/service' },
  { label: '关于 MAISON·FLORA', path: '/about' },
  { label: '设置', path: '/settings' },
]

// 管理类入口仅对对应角色展示（管理后台→admin；商家工作台→merchant 或 admin）
const ROLE_FUNCTIONS = [
  { role: 'admin', label: '管理后台', path: '/admin' },
  { role: ['merchant', 'admin'], label: '商家工作台', path: '/merchant' },
]

export default function Profile() {
  const nav = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState(null) // { id, nickname }
  const [mode, setMode] = useState('login') // login | register
  const [form, setForm] = useState({ username: '', password: '', nickname: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [orders, setOrders] = useState([])
  const [expanded, setExpanded] = useState(null)
  const [couponCount, setCouponCount] = useState(0)
  const [points, setPoints] = useState(0)
  const [favCount, setFavCount] = useState(0)
  const [reviewTarget, setReviewTarget] = useState(null) // 待评价订单
  const [reviewRating, setReviewRating] = useState(5)
  const [reviewContent, setReviewContent] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)
  const [showLoc, setShowLoc] = useState(false) // 登录后首次选择定位

  useEffect(() => {
    if (isLoggedIn()) {
      getProfile().then(setUser).catch(() => setUser({ id: getUserId(), nickname: '' }))
    }
  }, [])

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const data = await (mode === 'login' ? login : register)({ ...form })
      setUser({ id: data.user_id, nickname: data.nickname || form.username, role: data.role || '' })
      getProfile().then(setUser).catch(() => {})
      // 登录后首次：先选择收货位置（确定当前定位）
      if (!getLocation()) setShowLoc(true)
      // 登录守卫场景：登录成功后跳回原来要访问的页面
      const from = location.state?.from
      if (from && from !== '/profile') nav(from, { replace: true })
    } catch (e) {
      setErr(e.message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    clearSession()
    setUser(null)
    setForm({ username: '', password: '', nickname: '' })
  }

  const loadOrders = useCallback(async () => {
    if (!isLoggedIn()) return
    try {
      const orders = await listOrders()
      setOrders(orders)
    } catch (e) {
      toast(e.message || '订单加载失败', 'error')
    }
  }, [])

  useEffect(() => {
    loadOrders()
  }, [loadOrders])

  useEffect(() => {
    if (!isLoggedIn()) return
    Promise.all([listCoupons(), getPoints(), listFavorites()])
      .then(([cs, ps, favs]) => {
        setCouponCount(cs.filter((c) => c.status === 'unused').length)
        setPoints(ps.balance)
        setFavCount(favs.count || 0)
      })
      .catch(() => {})
  }, [])

  const act = async (oid, action) => {
    try {
      await orderAction(oid, action)
      toast(action === 'ship' ? '已模拟发货' : action === 'complete' ? '已确认收货' : '订单已取消')
      loadOrders()
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    }
  }

  const goPay = (oid) => nav('/pay', { state: { orderId: oid } })

  const openReview = (o) => {
    setReviewTarget(o)
    setReviewRating(5)
    setReviewContent('')
  }

  const submitReview = async () => {
    if (reviewBusy || !reviewTarget) return
    setReviewBusy(true)
    try {
      await postReview({
        order_id: reviewTarget.order_id,
        rating: reviewRating,
        content: reviewContent.trim(),
      })
      toast('评价成功，感谢你的反馈')
      setReviewTarget(null)
      loadOrders()
    } catch (e) {
      toast(e.message || '评价失败', 'error')
    } finally {
      setReviewBusy(false)
    }
  }

  return (
    <div className="min-h-full bg-bg pb-8">
      {/* 头部文艺色带：暖渐变 + 角落花枝 + 衬线标题 */}
      <div className="hero-flora relative px-5 pb-5 pt-7 shadow-soft">
        <FloraCorner
          className="pointer-events-none absolute -right-2 -top-1 text-white/50"
          style={{ width: 92, height: 92 }}
        />
        <h1 className="font-serif-cn text-[26px] font-normal text-ink">我的</h1>
        <p className="mt-1 text-[12px] text-sub">专属花艺，温柔收藏</p>
      </div>

      {/* 用户区：登录态显示资料，未登录显示登录/注册入口 */}
      {user ? (
        <div className="mt-4 flex items-center gap-3 px-5">
          <SmartImage imgKey="avatar" className="h-[56px] w-[56px] rounded-full" />
          <div className="flex-1">
            <p className="text-[16px] font-medium text-ink">{user.nickname || user.id}</p>
            <p className="mt-1 text-[10px] text-sub">{user.id}</p>
          </div>
          <Button
            variant="secondary"
            className="!h-[30px] !rounded-pill !border-line !text-[12px] !text-sub"
            onClick={logout}
          >
            退出
          </Button>
        </div>
      ) : (
        <form
          onSubmit={submit}
          className="relative mx-5 mt-4 overflow-hidden rounded-[4px] bg-white p-4 border border-line"
        >
          <FloraSprig
            className="pointer-events-none absolute -right-2 -bottom-3 text-gold/20"
            style={{ width: 64, height: 64 }}
          />
          <div className="mb-4 flex items-baseline justify-between border-b border-line pb-2.5">
            <p className="eyebrow">Atelier</p>
            <div className="flex gap-4">
              {['login', 'register'].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={
                    mode === m
                      ? 'border-b border-gold pb-1 text-[14px] font-medium text-gold'
                      : 'pb-1 text-[14px] text-sub'
                  }
                >
                  {m === 'login' ? '登录' : '注册'}
                </button>
              ))}
            </div>
          </div>
          <input
            placeholder="用户名"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            className="maison-field mb-2"
          />
          {mode === 'register' && (
            <input
              placeholder="昵称（可选）"
              value={form.nickname}
              onChange={(e) => setForm({ ...form, nickname: e.target.value })}
              className="maison-field mb-2"
            />
          )}
          <input
            placeholder="密码（≥6 位）"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="maison-field mb-2"
          />
          {err && <p className="mb-2 text-[11px] text-pink">{err}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? '处理中…' : mode === 'login' ? '登录' : '注册并登录'}
          </Button>
          <p className="mt-2 text-[10px] text-sub">
            登录后，你的对话、购物车、订单都将按账号隔离保存。
          </p>
        </form>
      )}

      {/* 会员卡 */}
      <div className="relative mx-5 mt-5 flex h-[58px] items-center justify-between overflow-hidden rounded-[4px] bg-dark px-4">
        <FloraSprig
          className="pointer-events-none absolute -right-2 -bottom-3 text-white/15"
          style={{ width: 72, height: 72 }}
        />
        <div>
          <p className="text-[13px] font-medium text-white">MAISON·FLORA 金牌会员</p>
          <p className="mt-1 text-[10px]" style={{ color: '#DDD2C8' }}>
            开通享更多专属权益
          </p>
        </div>
        <Button
          variant="secondary"
          className="!h-[30px] !rounded-pill !border-white/40 !text-[12px] !text-white"
          style={{ background: 'transparent' }}
        >
          立即开通
        </Button>
      </div>

      {/* 数据 */}
      <div className="mx-5 mt-5 grid grid-cols-4 rounded-[4px] bg-white py-4 border border-line">
        {STATS.map((s) => (
          <div key={s.label} className="flex flex-col items-center">
            <span className="text-[16px] font-medium text-dark">
              {s.label === '订单'
                ? orders.length
                : s.label === '优惠券'
                  ? couponCount
                  : s.label === '积分'
                    ? points
                    : s.label === '收藏'
                      ? favCount
                      : s.value}
            </span>
            <span className="mt-1 text-[10px] text-sub">{s.label}</span>
          </div>
        ))}
      </div>

      {/* 我的订单（真实数据：状态流转 + 物流时间线） */}
      <div className="mt-8 px-5">
        <SectionTitle title="我的订单" />
        {isLoggedIn() ? (
          orders.length === 0 ? (
            <p className="mt-3 rounded-card bg-white p-4 text-center text-[12px] text-sub border border-line">
              还没有订单，去 Agent 页让花艺师帮你设计一束吧
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              {orders.map((o) => {
                const meta = STATUS_META[o.status] || { label: o.status, color: 'text-sub' }
                const items = o.items || []
                return (
                  <div key={o.order_id} className="overflow-hidden rounded-card bg-white border border-line">
                    <div className="flex items-center justify-between border-b border-line px-4 py-3">
                      <span className="text-[11px] text-sub">{o.order_id}</span>
                      <span className={`text-[12px] font-medium ${meta.color}`}>{meta.label}</span>
                    </div>
                    {items.slice(0, 2).map((it) => (
                      <div key={it.plan_id} className="flex items-center gap-3 px-4 py-2.5">
                        <SmartImage
                          src={itemImagePath('plans', it.plan_id)}
                          imgKey="home_rec_1"
                          className="h-[44px] w-[44px] shrink-0 rounded-[4px]"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] text-dark">{it.name}</p>
                          <p className="text-[11px] text-sub">
                            ¥{it.price} × {it.qty}
                            {it.shop ? ` · ${it.shop}` : ''}
                          </p>
                        </div>
                      </div>
                    ))}
                    <div className="flex items-center justify-between px-4 py-2.5">
                      <button
                        className="press text-[12px] text-pink"
                        onClick={() => setExpanded(expanded === o.order_id ? null : o.order_id)}
                      >
                        {expanded === o.order_id ? '收起物流' : '查看物流'}
                      </button>
                      <p className="text-[13px] font-medium text-dark">
                        共 ¥{Number(o.total_price || 0).toFixed(2)}
                      </p>
                    </div>

                    {expanded === o.order_id && (
                      <div className="border-t border-line px-4 py-3">
                        {(o.logistics || []).map((e, i) => (
                          <div key={e.seq} className="flex gap-3">
                            <div className="flex flex-col items-center">
                              <span
                                className={`mt-1 h-2 w-2 rounded-full ${
                                  i === 0 ? 'bg-pink' : 'bg-line'
                                }`}
                              />
                              {i < (o.logistics || []).length - 1 && (
                                <span className="w-px flex-1 bg-line" />
                              )}
                            </div>
                            <div className="pb-3">
                              <p
                                className={`text-[12px] ${
                                  i === 0 ? 'font-medium text-dark' : 'text-sub'
                                }`}
                              >
                                {e.text}
                              </p>
                              <p className="text-[10px] text-sub/70">{e.created_at}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex justify-end gap-2 border-t border-line px-4 py-3">
                      {(o.status === 'created' || o.status === 'pending_payment') && (
                        <>
                          <Button
                            variant="secondary"
                            className="!h-[30px] !rounded-pill !text-[12px]"
                            onClick={() => act(o.order_id, 'cancel')}
                          >
                            取消订单
                          </Button>
                          <Button className="!h-[30px] !rounded-pill !text-[12px]" onClick={() => goPay(o.order_id)}>
                            去支付
                          </Button>
                        </>
                      )}
                      {o.status === 'paid' && (
                        <Button className="!h-[30px] !rounded-pill !text-[12px]" onClick={() => act(o.order_id, 'ship')}>
                          模拟发货
                        </Button>
                      )}
                      {o.status === 'shipped' && (
                        <Button className="!h-[30px] !rounded-pill !text-[12px]" onClick={() => act(o.order_id, 'complete')}>
                          确认收货
                        </Button>
                      )}
                      {o.status === 'done' && (
                        <Button className="!h-[30px] !rounded-pill !text-[12px]" onClick={() => openReview(o)}>
                          评价
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )
        ) : (
          <p className="mt-3 rounded-card bg-white p-4 text-center text-[12px] text-sub border border-line">
            登录后查看你的订单
          </p>
        )}
      </div>

      {/* 常用功能 */}
      <div className="mt-9 px-5">
        <SectionTitle title="常用功能" />
        <div className="mt-3 overflow-hidden rounded-[4px] bg-white border border-line">
          {[...ROLE_FUNCTIONS.filter((rf) => (Array.isArray(rf.role) ? rf.role.includes(user?.role) : rf.role === user?.role)), ...FUNCTIONS].map((f, i, all) => (
            <div
              key={f.label}
              role="button"
              tabIndex={0}
              onClick={() => (f.path ? nav(f.path) : undefined)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') e.preventDefault()
              }}
              className={`flex cursor-pointer items-center justify-between px-4 py-3.5 ${
                i < all.length - 1 ? 'border-b border-line' : ''
              }`}
            >
              <span className="text-[12px] text-ink">{f.label}</span>
              <IconArrow width={16} height={16} className="text-sub" />
            </div>
          ))}
        </div>
      </div>

      {/* 评价弹窗 */}
      {reviewTarget && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setReviewTarget(null)}
        >
          <div
            className="w-full max-w-[430px] rounded-t-[20px] bg-white p-5 pb-7"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-center text-[16px] font-medium text-dark">评价订单</h3>
            <p className="mt-1 text-center text-[11px] text-sub">
              订单 {reviewTarget.order_id} · 已完成，欢迎分享你的体验
            </p>
            <div className="mt-4 flex justify-center gap-2">
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  aria-label={`${s} 星`}
                  onClick={() => setReviewRating(s)}
                  className="p-1"
                >
                  <IconStar
                    width={26}
                    height={26}
                    filled={s <= reviewRating}
                    className={s <= reviewRating ? 'text-pink' : 'text-line'}
                  />
                </button>
              ))}
            </div>
            <textarea
              value={reviewContent}
              onChange={(e) => setReviewContent(e.target.value)}
              placeholder="说说这束花的体验吧（选填）"
              maxLength={500}
              rows={3}
              className="mt-4 w-full resize-none rounded-[4px] border border-line bg-bg p-3 text-[12px] text-ink outline-none placeholder:text-sub/60 focus:border-pink"
            />
            <Button className="mt-4 w-full" onClick={submitReview} disabled={reviewBusy}>
              {reviewBusy ? '提交中…' : '提交评价'}
            </Button>
          </div>
        </div>
      )}

      {/* 登录后首次定位选择 */}
      <LocationPicker
        open={showLoc}
        onConfirm={(loc) => {
          setLocation(loc)
          setShowLoc(false)
        }}
        onClose={() => setShowLoc(false)}
      />
    </div>
  )
}
