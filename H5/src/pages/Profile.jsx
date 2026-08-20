import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import SmartImage from '../components/SmartImage'
import { Button } from '../components/Button'
import { IconArrow } from '../components/icons'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'
import SectionTitle from '../components/SectionTitle'
import { toast } from '../utils/toast'
import { getLocation, setLocation } from '../utils/location'
import LocationPicker from '../components/LocationPicker'
import Reveal from '../components/Reveal'
import { listOrders, listCoupons, listFavorites } from '../api/shop'
import { unreadCount } from '../api/notify'
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
// 四模块卡（收藏/订单/优惠券/积分）：仅作功能导航，点击跳转对应页面，具体内容不内嵌

// 四模块功能导航（点击跳转，不内嵌内容）：优惠券/积分合并（领券中心同页含积分商城）
const MODULES = [
  { label: '收藏', path: '/favorites', key: 'fav' },
  { label: '订单', path: '/orders', key: 'order' },
  { label: '优惠券', path: '/coupons?tab=mine', key: 'coupon' },
  { label: '消息', path: '/notifications', key: 'notify' },
]
const FUNCTIONS = [
  { label: '我的地址', path: '/addresses' },
  { label: '我的售后', path: '/my-aftersales' },
  { label: '领券中心', path: '/coupons' },
  { label: '客服中心', path: '/service' },
  { label: '关于跳舞兰', path: '/about' },
  { label: '设置', path: '/settings' },
]

// 管理类入口（三端独立架构：商家工作台已迁独立入口 merchant.html，admin 走 admin.html）
const ROLE_FUNCTIONS = []

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
  const [orderCount, setOrderCount] = useState(0)
  const [couponCount, setCouponCount] = useState(0)
  const [favCount, setFavCount] = useState(0)
  const [notifyCount, setNotifyCount] = useState(0)
  const [showLoc, setShowLoc] = useState(false) // 登录后首次选择定位

  useEffect(() => {
    if (isLoggedIn()) {
      getProfile().then(setUser).catch(() => setUser({ id: getUserId(), nickname: '' }))
    }
  }, [])

  // 登录成功后的去向：优先跳回被守卫拦截的页面；否则留在个人中心
  const redirectAfterLogin = () => {
    const from = location.state?.from
    if (from && from !== '/profile') {
      nav(from, { replace: true })
    }
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
          redirectAfterLogin()
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
          redirectAfterLogin()
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
          redirectAfterLogin()
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
      setOrderCount(orders.length)
    } catch (e) {
      toast(e.message || '订单加载失败', 'error')
    }
  }, [])

  useEffect(() => {
    loadOrders()
  }, [loadOrders])

  useEffect(() => {
    if (!isLoggedIn()) return
    Promise.all([listCoupons(), listFavorites(), unreadCount()])
      .then(([cs, favs, unread]) => {
        setCouponCount(cs.filter((c) => c.status === 'unused').length)
        setFavCount(favs.count || 0)
        setNotifyCount(unread || 0)
      })
      .catch(() => {})
  }, [])

  return (
    <div className="min-h-full bg-bg pb-8">
      {/* 头部文艺色带：暖渐变 + 角落花枝 + 衬线标题 */}
      <div className="animate-hero hero-flora relative px-5 pb-5 pt-7 shadow-soft" style={{ animationDelay: '0ms' }}>
        <FloraCorner
          className="pointer-events-none absolute -right-2 -top-1 text-white/50"
          style={{ width: 92, height: 92 }}
        />
        <h1 className="font-serif-cn text-[26px] font-normal text-ink">我的</h1>
        <p className="mt-1 text-[12px] text-sub">专属花艺，温柔收藏</p>
      </div>

      {/* 用户区：登录态显示资料，未登录显示登录/注册入口 */}
      <Reveal delay={80}>
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
      </Reveal>

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
      <Reveal delay={160}>
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
            <p className="text-[13px] font-medium text-white">跳舞兰 · {user?.nickname || '花友'}</p>
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
      </Reveal>

      {/* 四模块功能导航（收藏/订单/优惠券/消息）：仅显示数字徽标，点击跳转对应页面 */}
      <Reveal delay={240}>
        <div className="mx-5 mt-5 grid grid-cols-4 gap-2">
        {MODULES.map((m) => {
          const count =
            m.key === 'order'
              ? orderCount
              : m.key === 'coupon'
                ? couponCount
                : m.key === 'notify'
                  ? notifyCount
                  : favCount
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => nav(m.path)}
              className="press flex flex-col items-center rounded-[4px] border border-ink/10 bg-white py-4 shadow-soft"
            >
              <span className="text-[18px] font-medium text-ink">{count}</span>
              <span className="mt-1 text-[11px] tracking-[1px] text-sub">{m.label}</span>
            </button>
          )
        })}
        </div>
      </Reveal>

      {/* 常用功能 */}
      <div className="mt-9 px-5">
        <Reveal delay={320}>
          <SectionTitle title="常用功能" />
        </Reveal>
        <Reveal delay={400}>
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
                if ((e.key === 'Enter' || e.key === ' ') && f.path) {
                  e.preventDefault()
                  nav(f.path)
                }
              }}
              className={`flex cursor-pointer items-center justify-between px-4 py-3.5 ${
                i < all.length - 1 ? 'border-b border-line' : ''
              }`}
            >
              <span className="text-[12px] text-ink">{f.label}</span>
              <span className="flex items-center gap-2">
                {f.badge === 'notify' && notifyCount > 0 && (
                  <span className="flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-pink px-1.5 text-[10px] leading-none text-white">
                    {notifyCount > 99 ? '99+' : notifyCount}
                  </span>
                )}
                <IconArrow width={16} height={16} className="text-sub" />
              </span>
            </div>
          ))}
        </div>
        </Reveal>
      </div>

      {/* 退出登录（仅登录态显示；底部独立入口，避免头像栏拥挤） */}
      {user && (
        <Reveal delay={480}>
          <div className="mt-6 px-5">
            <button
              onClick={logout}
              className="w-full rounded-[4px] border border-line bg-white py-3 text-center text-[13px] tracking-wide text-burgundy"
            >
              退出登录
            </button>
          </div>
        </Reveal>
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
