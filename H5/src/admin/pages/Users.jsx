// 用户管理（M2）：列表 + 关键词/角色/状态筛选 + 禁用/启用 + 提权。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Pager } from '../App'

const ROLES = [
  { v: '', label: '全部角色' },
  { v: 'user', label: '普通用户' },
  { v: 'merchant', label: '商家' },
  { v: 'admin', label: '管理员' },
]

export function Users() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [limit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const data = await api.get('/admin/users', { keyword, role, status, limit, offset })
    setRows(data.users)
    setTotal(data.total)
  }, [keyword, role, status, limit, offset])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const act = async (uid, fn, okMsg) => {
    if (busy) return
    setBusy(uid)
    setMsg('')
    try {
      await fn()
      setMsg(okMsg)
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  const changeRole = (uid, next) =>
    act(uid, () => api.post(`/admin/users/${uid}/role`, { role: next }), `已设置角色 ${next}`)

  const toggleBan = (u) =>
    act(
      u.status === 'banned' ? u.id : u.id,
      () => api.post(`/admin/users/${u.id}/${u.status === 'banned' ? 'unban' : 'ban'}`),
      u.status === 'banned' ? '已启用' : '已禁用',
    )

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">用户管理</h2>
      <p className="mt-1 text-[12px] text-sub">禁用 / 启用账号，调整角色权限</p>

      {/* 筛选条 */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setOffset(0)
          }}
          placeholder="搜索 用户名 / 昵称 / 手机号"
          className="maison-field w-[240px] rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        />
        <select
          value={role}
          onChange={(e) => {
            setRole(e.target.value)
            setOffset(0)
          }}
          className="rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        >
          {ROLES.map((r) => (
            <option key={r.v} value={r.v}>
              {r.label}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setOffset(0)
          }}
          className="rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        >
          <option value="">全部状态</option>
          <option value="active">正常</option>
          <option value="banned">已禁用</option>
        </select>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      {/* 表格 */}
      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
        <table className="w-full min-w-[720px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
              <th className="px-4 py-3">用户名</th>
              <th className="px-4 py-3">昵称</th>
              <th className="px-4 py-3">手机号</th>
              <th className="px-4 py-3">角色</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">注册时间</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3 text-ink">{u.username || u.id.slice(0, 10)}</td>
                <td className="px-4 py-3">{u.nickname || '—'}</td>
                <td className="px-4 py-3 text-sub">{u.phone || '—'}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-pill px-2 py-0.5 text-[11px] ${
                      u.role === 'admin' ? 'bg-burgundy/10 text-burgundy' : u.role === 'merchant' ? 'bg-gold/15 text-gold-dark' : 'bg-line/40 text-sub'
                    }`}
                  >
                    {u.role === 'admin' ? '管理员' : u.role === 'merchant' ? '商家' : '普通用户'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={u.status === 'banned' ? 'text-burgundy' : 'text-[#5b8a6a]'}>
                    {u.status === 'banned' ? '已禁用' : '正常'}
                  </span>
                </td>
                <td className="px-4 py-3 text-sub">{u.created_at}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    <select
                      value={u.role}
                      disabled={busy === u.id}
                      onChange={(e) => changeRole(u.id, e.target.value)}
                      className="rounded-[2px] border border-line bg-white px-2 py-1 text-[11px]"
                    >
                      <option value="user">user</option>
                      <option value="merchant">merchant</option>
                      <option value="admin">admin</option>
                    </select>
                    <button
                      disabled={busy === u.id}
                      onClick={() => toggleBan(u)}
                      className="press rounded-[2px] border border-line bg-white px-2.5 py-1 text-[11px] disabled:opacity-40"
                    >
                      {busy === u.id ? '处理中…' : u.status === 'banned' ? '启用' : '禁用'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sub">
                  没有匹配的用户
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Pager offset={offset} total={total} limit={limit} onChange={setOffset} />
    </div>
  )
}
