import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import SmartImage from '../components/SmartImage'
import { Button } from '../components/Button'
import { IconArrow } from '../components/icons'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'
import SectionTitle from '../components/SectionTitle'
import { planImage } from '../assets/imageMap'
import { toast } from '../utils/toast'
import { statusMeta } from '../utils/status'
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
  sendPhoneCode,
  phoneLogin,
  wxLogin,
} from '../api/auth'

// 微信图标（品牌绿，经典双气泡）
const WeChatIcon = (p) => (
  <svg viewBox="0 0 24 24" width={p.width || 15} height={p.height || 15} fill="#07C160" aria-hidden="true">
    <path d="M8.7 4C4.9 4 2 6.6 2 9.9c0 1.9 1 3.6 2.7 4.7l-.7 2.1 2.4-1.2c.8.2 1.6.4 2.4.4.3 0 .6 0 .9-.1-.1-.6-.2-1.2-.2-1.9 0-3.2 2.9-5.7 6.5-5.7h.5C15.4 5.9 12.3 4 8.7 4zM6.3 8.4a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8zm5 0a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8zM22 13.9c0-2.8-2.5-5-5.6-5s-5.6 2.2-5.6 5 2.5 5 5.6 5c.7 0 1.4-.1 2-.3l2 1-.6-1.8c1.4-.9 2.2-2.3 2.2-3.9zm-7.4-.7a.8.8 0 1 1 0-1.5.8.8 0 0 1 0 1.5zm3.6 0a.8.8 0 1 1 0-1.5.8.8 0 0 1 0 1.5z" />
  </svg>
)

// 手机图标（lucide 风格）
const PhoneIcon = (p) => (
  <svg
    viewBox="0 0 24 24"
    width={p.width || 15}
    height={p.height || 15}
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
  </svg>
)

// 08 我的
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
  { label: '我的售后', path: '/my-aftersales' },
  { label: '领券中心', path: '/coupons' },
  { label: '客服中心', path: '/service' },
  { label: '关于跳舞兰', path: '/about' },
  { label: '设置', path: '/settings' },
]

// 管理类入口仅对对应角色展示（商家工作台→merchant；admin 走独立管理后台 /admin.html）
const ROLE_FUNCTIONS = [
  { role: 'merchant', label: '商家工作台', path: '/merchant' },
]

export default function Profile() {
  const nav = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState(null) // { id, nickname }
  const [mode, setMode] = useState('login') // login | register
  const [authTab, setAuthTab] = useState('phone') // phone | account（手机号/微信一键登录优先）
  const [loginOpen, setLoginOpen] = useState(false) // 登录方式选择弹层
  const [showForm, setShowForm] = useState(false) // 是否展开手机号/账号表单
  const [form, setForm] = useState({ username: '', password: '', nickname: '' })
  const [phoneForm, setPhoneForm] = useState({ phone: '', code: '' })
  const [countdown, setCountdown] = useState(0) // 验证码发送倒计时（秒）
  const [codeBusy, setCodeBusy] = useState(false)
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

  // 登录成功后的去向：优先跳回被守卫拦截的页面；否则商家进工作台，其余留在个人中心
  const redirectAfterLogin = (p) => {
    const from = location.state?.from
    if (from && from !== '/profile') {
      nav(from, { replace: true })
      return
    }
    if (p?.role === 'merchant') nav('/merchant', { replace: true })
  }

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const data = await (mode === 'login' ? login : register)({ ...form })
      setUser({ id: data.user_id, nickname: data.nickname || form.username, role: data.role || '' })
      getProfile()
        .then((p) => {
          setUser(p)
          redirectAfterLogin(p)
        })
        .catch(() => {})
      // 登录后首次：先选择收货位置（确定当前定位）
      if (!getLocation()) setShowLoc(true)
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
    setPhoneForm({ phone: '', code: '' })
    setShowForm(false)
    setLoginOpen(false)
  }

  // 手机号验证码倒计时
  useEffect(() => {
    if (countdown <= 0) return
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000)
    return () => clearTimeout(t)
  }, [countdown])

  const sendCode = async () => {
    if (!/^1\d{10}$/.test(phoneForm.phone)) {
      setErr('请输入正确的 11 位手机号')
      return
    }
    if (countdown > 0 || codeBusy) return
    setErr('')
    setCodeBusy(true)
    try {
      const data = await sendPhoneCode(phoneForm.phone)
      toast(data.dev_code ? `验证码：${data.dev_code}（开发模式）` : '验证码已发送')
      setCountdown(60)
    } catch (e) {
      setErr(e.message || '获取验证码失败')
    } finally {
      setCodeBusy(false)
    }
  }

  const submitPhone = async (e) => {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const data = await phoneLogin(phoneForm)
      setUser({ id: data.user_id, nickname: data.nickname || data.phone, role: data.role || '' })
      getProfile()
        .then((p) => {
          setUser(p)
          redirectAfterLogin(p)
        })
        .catch(() => {})
      if (!getLocation()) setShowLoc(true)
    } catch (e) {
      setErr(e.message || '登录失败')
    } finally {
      setBusy(false)
    }
  }

  const doWxLogin = async () => {
    setBusy(true)
    try {
      const data = await wxLogin()
      setUser({ id: data.user_id, nickname: data.nickname, role: data.role || '' })
      getProfile()
        .then((p) => {
          setUser(p)
          redirectAfterLogin(p)
        })
        .catch(() => {})
      if (!getLocation()) setShowLoc(true)
    } catch (e) {
      toast(e.message || '微信登录失败', 'error')
    } finally {
      setBusy(false)
    }
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
          <div className="min-w-0 flex-1">
            <p className="truncate text-[16px] font-medium text-ink">{user.nickname || user.id}</p>
            <p className="mt-1 truncate text-[10px] text-sub">{user.id}</p>
          </div>
          <button
            onClick={() => nav('/settings')}
            aria-label="账号与安全"
            className="press flex h-[34px] items-center gap-1 rounded-full border border-line bg-white px-3 text-[12px] text-sub"
          >
            账号与安全
            <IconArrow width={12} height={12} className="rotate-90 text-sub" />
          </button>
        </div>
      ) : showForm ? (
        <form
          onSubmit={authTab === 'phone' ? submitPhone : submit}
          className="relative mx-5 mt-4 overflow-hidden rounded-[4px] bg-white p-4 border border-line"
        >
          <FloraSprig
            className="pointer-events-none absolute -right-2 -bottom-3 text-gold/20"
            style={{ width: 64, height: 64 }}
          />
          <div className="mb-4 flex items-baseline justify-between border-b border-line pb-2.5">
            <p className="eyebrow">跳舞兰</p>
            <div className="flex gap-4">
              {[
                { key: 'phone', label: '手机号登录' },
                { key: 'account', label: '账号登录' },
              ].map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => {
                    setAuthTab(t.key)
                    setErr('')
                  }}
                  className={
                    authTab === t.key
                      ? 'border-b border-gold pb-1 text-[14px] font-medium text-gold'
                      : 'pb-1 text-[14px] text-sub'
                  }
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {authTab === 'account' ? (
            <>
              <div className="mb-2 flex gap-4">
                {['login', 'register'].map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={
                      mode === m
                        ? 'border-b border-gold pb-0.5 text-[12px] font-medium text-gold'
                        : 'pb-0.5 text-[12px] text-sub'
                    }
                  >
                    {m === 'login' ? '登录' : '注册'}
                  </button>
                ))}
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
            </>
          ) : (
            <>
              <input
                placeholder="手机号"
                inputMode="numeric"
                maxLength={11}
                value={phoneForm.phone}
                onChange={(e) => setPhoneForm({ ...phoneForm, phone: e.target.value.replace(/\D/g, '') })}
                className="maison-field mb-2"
              />
              <div className="mb-2 flex gap-2">
                <input
                  placeholder="验证码"
                  inputMode="numeric"
                  maxLength={6}
                  value={phoneForm.code}
                  onChange={(e) => setPhoneForm({ ...phoneForm, code: e.target.value.replace(/\D/g, '') })}
                  className="maison-field flex-1"
                />
                <button
                  type="button"
                  onClick={sendCode}
                  disabled={countdown > 0 || codeBusy}
                  className="press w-[104px] shrink-0 rounded-[2px] border border-gold/40 bg-white text-[12px] text-gold disabled:opacity-50"
                >
                  {countdown > 0 ? `${countdown}s 后重发` : '获取验证码'}
                </button>
              </div>
              {err && <p className="mb-2 text-[11px] text-pink">{err}</p>}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? '处理中…' : '手机号登录 / 注册'}
              </Button>
            </>
          )}
          <button
            type="button"
            onClick={() => setShowForm(false)}
            className="mt-3 w-full text-center text-[12px] text-sub"
          >
            返回登录方式
          </button>
          <p className="mt-2 text-[10px] text-sub">
            未注册的手机号 / 微信将自动创建账号，登录后对话、购物车、订单按账号隔离保存。
          </p>
        </form>
      ) : (
        <div className="relative mx-5 mt-4 overflow-hidden rounded-[4px] bg-white p-6 text-center border border-line">
          <FloraSprig
            className="pointer-events-none absolute -right-2 -bottom-3 text-gold/20"
            style={{ width: 72, height: 72 }}
          />
          <img
            src="/images/brand/logo.jpg"
            alt="跳舞兰"
            className="mx-auto h-11 w-11 rounded-full border border-line bg-white object-cover"
          />
          <p className="eyebrow mt-3">跳舞兰</p>
          <p className="mt-2 font-serif-cn text-[20px] text-ink">欢迎来到 跳舞兰</p>
          <p className="mt-1 text-[11px] text-sub">登录后对话、购物车、订单按账号隔离保存</p>
          <Button className="mt-5 w-full" onClick={() => setLoginOpen(true)}>
            手机号 / 微信登录
          </Button>
          <p className="mt-3 text-[10px] text-sub/70">未注册的手机号 / 微信将自动创建账号</p>
        </div>
      )}

      {/* 登录方式选择弹层：微信 / 手机号 */}
      {loginOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setLoginOpen(false)}
        >
          <div
            className="w-full max-w-h5 rounded-t-[4px] bg-white px-5 pb-8 pt-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-4 h-[2px] w-9 bg-gold" />
            <h3 className="text-[17px] font-medium text-ink">选择登录方式</h3>
            <p className="mt-1 text-[11px] text-sub">未注册的手机号 / 微信将自动创建账号</p>
            <button
              onClick={() => {
                setLoginOpen(false)
                doWxLogin()
              }}
              disabled={busy}
              className="press mt-5 flex h-[46px] w-full items-center justify-center gap-2 rounded-[2px] bg-[#07C160] text-[14px] font-medium tracking-wide text-white disabled:opacity-60"
            >
              <WeChatIcon width={16} height={16} />
              微信登录
            </button>
            <button
              onClick={() => {
                setLoginOpen(false)
                setAuthTab('phone')
                setShowForm(true)
              }}
              className="press mt-3 flex h-[46px] w-full items-center justify-center gap-2 rounded-[2px] bg-gold text-[14px] font-medium tracking-wide text-[#FAF8F5]"
            >
              <PhoneIcon width={15} height={15} />
              手机号登录 / 注册
            </button>
            <button onClick={() => setLoginOpen(false)} className="mt-4 w-full text-center text-[12px] text-sub">
              暂不登录，随便逛逛
            </button>
          </div>
        </div>
      )}

      {/* 会员卡 */}
      <div className="relative mx-5 mt-5 flex h-[58px] items-center justify-between overflow-hidden rounded-[4px] bg-dark px-4">
        <FloraSprig
          className="pointer-events-none absolute -right-2 -bottom-3 text-white/15"
          style={{ width: 72, height: 72 }}
        />
        <div className="flex min-w-0 items-center gap-2.5">
          <img
            src="/images/brand/logo.jpg"
            alt="跳舞兰"
            className="h-7 w-7 shrink-0 rounded-full border border-white/30 bg-white object-cover"
          />
          <div>
            <p className="text-[13px] font-medium text-white">跳舞兰 金牌会员</p>
            <p className="mt-1 text-[10px]" style={{ color: '#DDD2C8' }}>
              开通享更多专属权益
            </p>
          </div>
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
        <SectionTitle
          title="我的订单"
          action={
            <button
              type="button"
              onClick={() => nav('/orders')}
              className="press text-[12px] tracking-[1px] text-sub"
            >
              全部 ›
            </button>
          }
        />
        {isLoggedIn() ? (
          orders.length === 0 ? (
            <p className="mt-3 rounded-card bg-white p-4 text-center text-[12px] text-sub border border-line">
              还没有订单，去 Agent 页让花艺师帮你设计一束吧
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              {orders.map((o) => {
                const meta = statusMeta(o.status)
                const items = o.items || []
                return (
                  <div key={o.order_id} className="overflow-hidden rounded-card bg-white border border-line">
                    <button
                      type="button"
                      onClick={() => nav(`/logistics/${o.order_id}`)}
                      className="flex w-full items-center justify-between border-b border-line px-4 py-3 text-left"
                    >
                      <span className="text-[11px] text-sub">{o.order_id}</span>
                      <span className={`text-[12px] font-medium ${meta.cls}`}>{meta.label}</span>
                    </button>
                    {items.slice(0, 2).map((it) => (
                      <div key={it.plan_id} className="flex items-center gap-3 px-4 py-2.5">
                        <SmartImage
                          src={planImage(it)}
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
          {[
            ...ROLE_FUNCTIONS.filter((rf) => (Array.isArray(rf.role) ? rf.role.includes(user?.role) : rf.role === user?.role)),
            // 非商家用户：商家入驻入口（M5）
            ...(user && user.role !== 'merchant' && user.role !== 'admin'
              ? [{ label: '商家入驻', path: '/merchant-apply' }]
              : []),
            ...FUNCTIONS,
          ].map((f, i, all) => (
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

      {/* 退出登录（仅登录态显示；底部独立入口，避免头像栏拥挤） */}
      {user && (
        <div className="mt-6 px-5">
          <button
            onClick={logout}
            className="w-full rounded-[4px] border border-line bg-white py-3 text-center text-[13px] tracking-wide text-burgundy"
          >
            退出登录
          </button>
        </div>
      )}

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
