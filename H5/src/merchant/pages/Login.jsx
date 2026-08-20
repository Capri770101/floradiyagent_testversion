// 商家登录/注册页：手机号+密码 → /auth/merchant-login 或 /auth/merchant-register（role=merchant）。
import React, { useState } from 'react'
import { fetchProfile, merchantLogin, merchantRegister } from '../api'

export function Login({ onLogin }) {
  const [mode, setMode] = useState('login') // login | register
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [shopName, setShopName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      if (mode === 'register') {
        await merchantRegister(phone.trim(), password, shopName.trim())
      } else {
        await merchantLogin(phone.trim(), password)
      }
      const u = await fetchProfile()
      if (!u || u.role !== 'merchant') {
        setErr('该账号不是商家，无法进入商家端')
        setBusy(false)
        return
      }
      onLogin(u)
    } catch (ex) {
      setErr(ex.message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const canSubmit = phone.trim().length >= 6 && password.length >= 6 && (mode === 'login' || !busy)

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <form
        onSubmit={submit}
        className="w-[360px] rounded-card border border-line bg-white p-8 shadow-card"
      >
        <p className="eyebrow">Flora Merchant</p>
        <h1 className="mt-1 font-serif-cn text-[24px] font-normal text-ink">商家工作台</h1>
        <p className="mt-1 text-[11px] text-sub">
          {mode === 'login' ? '使用商家手机号登录' : '注册成为商家（手机号全局唯一）'}
        </p>

        <div className="mt-6 space-y-3">
          {mode === 'register' && (
            <input
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              placeholder="店铺名称（选填）"
              className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
            />
          )}
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="手机号"
            autoComplete="username"
            className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="密码（至少 6 位）"
            autoComplete="current-password"
            className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
          />
          {err && <p className="text-[12px] text-burgundy">{err}</p>}
          <button
            type="submit"
            disabled={!canSubmit}
            className="press w-full rounded-[2px] bg-gold py-2.5 text-[13px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
          >
            {busy ? '提交中…' : mode === 'login' ? '登 录' : '注册并登录'}
          </button>
        </div>

        <button
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setErr('')
          }}
          className="press mt-4 w-full text-center text-[12px] tracking-[1px] text-sub"
        >
          {mode === 'login' ? '还没有商家账号？立即注册' : '已有商家账号？返回登录'}
        </button>
      </form>
    </div>
  )
}