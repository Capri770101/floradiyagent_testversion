// 评价审核（M6）：全平台评价列表 + 隐藏/显示/删除。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Pager } from '../App'

export function Reviews() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [limit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const data = await api.get('/admin/reviews', { status, keyword, limit, offset })
    setRows(data.reviews)
    setTotal(data.total)
  }, [status, keyword, limit, offset])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const act = async (rid, fn, okMsg) => {
    if (busy) return
    setBusy(rid)
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

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">评价审核</h2>
      <p className="mt-1 text-[12px] text-sub">隐藏/显示/删除评价；隐藏后 C 端不再展示</p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setOffset(0)
          }}
          placeholder="搜索 内容 / 昵称 / 方案"
          className="maison-field w-[240px] rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setOffset(0)
          }}
          className="rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
        >
          <option value="">全部状态</option>
          <option value="visible">可见</option>
          <option value="hidden">已隐藏</option>
        </select>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
        <table className="w-full min-w-[760px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
              <th className="px-4 py-3">评分</th>
              <th className="px-4 py-3">内容</th>
              <th className="px-4 py-3">用户</th>
              <th className="px-4 py-3">关联方案</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">时间</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3 text-gold">{'★'.repeat(r.rating)}</td>
                <td className="max-w-[280px] px-4 py-3">
                  <p className="truncate">{r.content || '（无文字评价）'}</p>
                  {r.reply && <p className="mt-0.5 truncate text-[10px] text-gold-dark">商家回复：{r.reply}</p>}
                </td>
                <td className="px-4 py-3">{r.nickname || '—'}</td>
                <td className="px-4 py-3 text-sub">{r.plan_name || r.plan_id || '—'}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-pill px-2 py-0.5 text-[11px] ${
                      r.status === 'hidden' ? 'bg-line/40 text-sub' : 'bg-[#5b8a6a]/15 text-[#5b8a6a]'
                    }`}
                  >
                    {r.status === 'hidden' ? '已隐藏' : '可见'}
                  </span>
                </td>
                <td className="px-4 py-3 text-sub">{r.created_at}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    {r.status === 'hidden' ? (
                      <button
                        disabled={busy === r.id}
                        onClick={() => act(r.id, () => api.post(`/admin/reviews/${r.id}/show`), '已恢复显示')}
                        className="press rounded-[2px] border border-gold/40 bg-white px-2.5 py-1 text-[11px] text-gold disabled:opacity-40"
                      >
                        显示
                      </button>
                    ) : (
                      <button
                        disabled={busy === r.id}
                        onClick={() => act(r.id, () => api.post(`/admin/reviews/${r.id}/hide`), '已隐藏')}
                        className="press rounded-[2px] border border-line bg-white px-2.5 py-1 text-[11px] text-sub disabled:opacity-40"
                      >
                        隐藏
                      </button>
                    )}
                    <button
                      disabled={busy === r.id}
                      onClick={() => {
                        if (!window.confirm('确定删除这条评价？')) return
                        act(r.id, () => api.del(`/admin/reviews/${r.id}`), '已删除')
                      }}
                      className="press rounded-[2px] border border-line bg-white px-2.5 py-1 text-[11px] text-burgundy disabled:opacity-40"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sub">
                  没有匹配的评价
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
