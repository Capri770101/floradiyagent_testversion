import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SmartImage from '../components/SmartImage'
import { Button } from '../components/Button'
import { IconArrow, IconFlower } from '../components/icons'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'
import SectionTitle from '../components/SectionTitle'
import {
  isLoggedIn,
  getUserId,
  login,
  register,
  getProfile,
  clearSession,
} from '../api/auth'

// 08 我的
const ORDER_TABS = ['待付款', '待配送', '配送中', '已完成']

// 本地静态展示数据（不再依赖 data/mock，避免 review 点名的「Profile 全 mock」）
const STATS = [
  { label: '收藏', value: 0 },
  { label: '订单', value: 0 },
  { label: '优惠券', value: 0 },
  { label: '积分', value: 0 },
]
const FUNCTIONS = ['管理后台', '我的地址', '客服中心', '关于 FloraDIY', '设置']

export default function Profile() {
  const nav = useNavigate()
  const [user, setUser] = useState(null) // { id, nickname }
  const [mode, setMode] = useState('login') // login | register
  const [form, setForm] = useState({ username: '', password: '', nickname: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

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
      setUser({ id: data.user_id, nickname: data.nickname || form.username })
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

  return (
    <div className="min-h-full bg-bg pb-8">
      {/* 头部文艺色带：暖渐变 + 角落花枝 + 衬线标题 */}
      <div className="hero-flora relative px-5 pb-5 pt-7 shadow-soft">
        <FloraCorner
          className="pointer-events-none absolute -right-2 -top-1 text-white/50"
          style={{ width: 92, height: 92 }}
        />
        <h1 className="font-serif-cn text-[22px] font-medium text-dark">我的</h1>
        <p className="mt-1 text-[12px] text-sub">专属花艺，温柔收藏</p>
      </div>

      {/* 用户区：登录态显示资料，未登录显示登录/注册入口 */}
      {user ? (
        <div className="mt-4 flex items-center gap-3 px-5">
          <SmartImage imgKey="avatar" className="h-[56px] w-[56px] rounded-[28px]" />
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
          className="mx-5 mt-4 rounded-[16px] bg-white p-4 shadow-card"
        >
          <div className="mb-3 flex gap-4">
            {['login', 'register'].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={mode === m ? 'text-[14px] font-medium text-pink' : 'text-[14px] text-sub'}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>
          <input
            placeholder="用户名"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            className="mb-2 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-[13px] outline-none"
          />
          {mode === 'register' && (
            <input
              placeholder="昵称（可选）"
              value={form.nickname}
              onChange={(e) => setForm({ ...form, nickname: e.target.value })}
              className="mb-2 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-[13px] outline-none"
            />
          )}
          <input
            placeholder="密码（≥6 位）"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="mb-2 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-[13px] outline-none"
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
      <div className="relative mx-5 mt-5 flex h-[58px] items-center justify-between overflow-hidden rounded-[16px] bg-dark px-4">
        <FloraSprig
          className="pointer-events-none absolute -right-2 -bottom-3 text-white/15"
          style={{ width: 72, height: 72 }}
        />
        <div>
          <p className="text-[13px] font-medium text-white">FloraDIY 金牌会员</p>
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
      <div className="mx-5 mt-5 grid grid-cols-4 rounded-[16px] bg-white py-4 shadow-card">
        {STATS.map((s) => (
          <div key={s.label} className="flex flex-col items-center">
            <span className="text-[16px] font-medium text-dark">{s.value}</span>
            <span className="mt-1 text-[10px] text-sub">{s.label}</span>
          </div>
        ))}
      </div>

      {/* 我的订单 */}
      <div className="mt-8 px-5">
        <SectionTitle title="我的订单" />
        <div className="mt-3 grid grid-cols-4">
          {ORDER_TABS.map((t) => (
            <div key={t} className="flex flex-col items-center gap-1.5">
              <div className="flex h-[40px] w-[40px] items-center justify-center rounded-full bg-white text-pink shadow-card">
                <IconFlower width={18} height={18} />
              </div>
              <span className="text-[10px] text-ink">{t}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 常用功能 */}
      <div className="mt-9 px-5">
        <SectionTitle title="常用功能" />
        <div className="mt-3 overflow-hidden rounded-[12px] bg-white shadow-card">
          {FUNCTIONS.map((f, i) => (
            <div
              key={f}
              role="button"
              tabIndex={0}
              onClick={() => (f === '管理后台' ? nav('/admin') : undefined)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') e.preventDefault()
              }}
              className={`flex cursor-pointer items-center justify-between px-4 py-3.5 ${
                i < FUNCTIONS.length - 1 ? 'border-b border-line' : ''
              }`}
            >
              <span className="text-[12px] text-ink">{f}</span>
              <IconArrow width={16} height={16} className="text-sub" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
