// 管理后台登录页：账号密码 → /auth/login → 校验 role=admin。
import React, { useState } from 'react'
import { fetchProfile, login } from '../api'

export function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await login(username.trim(), password)
      const u = await fetchProfile()
      // 非管理员：后端登录成功但无后台权限
      if (!u || u.role !== 'admin') {
        setErr('该账号不是管理员，无法进入后台')
        setBusy(false)
        return
      }
      onLogin(u)
    } catch (ex) {
      setErr(ex.message || '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <form
        onSubmit={submit}
        className="w-[340px] rounded-card border border-line bg-white p-8 shadow-card"
      >
        <p className="eyebrow">Flora Console</p>
        <h1 className="mt-1 font-serif-cn text-[24px] font-normal text-ink">平台管理后台</h1>
        <p className="mt-1 text-[11px] text-sub">请使用管理员账号登录</p>
        <div className="mt-6 space-y-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="用户名"
            autoComplete="username"
            className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="密码"
            autoComplete="current-password"
            className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
          />
          {err && <p className="text-[12px] text-burgundy">{err}</p>}
          <button
            type="submit"
            disabled={busy || !username.trim() || !password}
            className="press w-full rounded-[2px] bg-gold py-2.5 text-[13px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
          >
            {busy ? '登录中…' : '登 录'}
          </button>
        </div>
      </form>
    </div>
  )
}
