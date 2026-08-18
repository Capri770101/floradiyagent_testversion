// 内容管理（M9 + M7 分类）：FAQ 编辑 / 公告编辑 / 分类 CRUD 三个页签。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

export function Content() {
  const [tab, setTab] = useState('faqs')
  return (
    <div>
      <div className="flex items-center gap-6">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">内容管理</h2>
        <div className="flex gap-1">
          {[
            { k: 'faqs', l: '常见问题' },
            { k: 'announcements', l: '平台公告' },
            { k: 'categories', l: '商品分类' },
          ].map((t) => (
            <button
              key={t.k}
              onClick={() => setTab(t.k)}
              className={`press rounded-pill px-4 py-1.5 text-[12px] ${tab === t.k ? 'bg-gold/15 font-medium text-gold' : 'text-sub'}`}
            >
              {t.l}
            </button>
          ))}
        </div>
      </div>
      {tab === 'faqs' && <FaqEditor />}
      {tab === 'announcements' && <AnnouncementEditor />}
      {tab === 'categories' && <CategoryManager />}
    </div>
  )
}

const fieldCls = 'maison-field rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]'

// ---------- FAQ 编辑 ----------
function FaqEditor() {
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const d = await api.get('/admin/content/faqs')
    setItems(d.faqs || [])
  }, [])
  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const setItem = (i, k, v) => setItems((arr) => arr.map((x, idx) => (idx === i ? { ...x, [k]: v } : x)))
  const add = () => setItems((arr) => [...arr, { q: '', a: '' }])
  const remove = (i) => setItems((arr) => arr.filter((_, idx) => idx !== i))

  const save = async () => {
    if (busy) return
    setBusy(true)
    setMsg('')
    try {
      await api.put('/admin/content/faqs', { faqs: items })
      setMsg('常见问题已保存')
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 max-w-[640px]">
      {msg && <p className="mb-2 text-[12px] text-gold-dark">{msg}</p>}
      <div className="space-y-3 rounded-card border border-line bg-white p-4 shadow-card">
        {items.map((f, i) => (
          <div key={i} className="rounded-[2px] border border-line p-3">
            <input
              value={f.q}
              onChange={(e) => setItem(i, 'q', e.target.value)}
              placeholder="问题"
              maxLength={100}
              className={`${fieldCls} w-full`}
            />
            <textarea
              value={f.a}
              onChange={(e) => setItem(i, 'a', e.target.value)}
              placeholder="回答"
              maxLength={500}
              rows={2}
              className={`${fieldCls} mt-2 w-full resize-none`}
            />
            <button onClick={() => remove(i)} className="press mt-2 text-[11px] text-sub">
              删除此条
            </button>
          </div>
        ))}
        <button onClick={add} className="press rounded-[2px] border border-gold/40 px-3 py-1.5 text-[12px] text-gold">
          + 添加 FAQ
        </button>
        <button
          onClick={save}
          disabled={busy}
          className="press ml-2 rounded-[2px] bg-gold px-6 py-1.5 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
        >
          {busy ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  )
}

// ---------- 公告编辑 ----------
function AnnouncementEditor() {
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const d = await api.get('/admin/content/announcements')
    setItems(d.announcements || [])
  }, [])
  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const setItem = (i, v) => setItems((arr) => arr.map((x, idx) => (idx === i ? { ...x, content: v } : x)))
  const add = () => setItems((arr) => [...arr, { content: '' }])
  const remove = (i) => setItems((arr) => arr.filter((_, idx) => idx !== i))

  const save = async () => {
    if (busy) return
    setBusy(true)
    setMsg('')
    try {
      await api.put('/admin/content/announcements', { announcements: items })
      setMsg('公告已保存')
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 max-w-[640px]">
      {msg && <p className="mb-2 text-[12px] text-gold-dark">{msg}</p>}
      <div className="space-y-3 rounded-card border border-line bg-white p-4 shadow-card">
        {items.map((a, i) => (
          <div key={i} className="flex items-start gap-2">
            <textarea
              value={a.content}
              onChange={(e) => setItem(i, e.target.value)}
              placeholder="公告内容（显示在 C 端客服中心页）"
              maxLength={200}
              rows={2}
              className={`${fieldCls} flex-1 resize-none`}
            />
            <button onClick={() => remove(i)} className="press mt-1 shrink-0 text-[11px] text-sub">
              删除
            </button>
          </div>
        ))}
        <div>
          <button onClick={add} className="press rounded-[2px] border border-gold/40 px-3 py-1.5 text-[12px] text-gold">
            + 添加公告
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="press ml-2 rounded-[2px] bg-gold px-6 py-1.5 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
          >
            {busy ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------- 分类管理 ----------
function CategoryManager() {
  const [rows, setRows] = useState([])
  const [draft, setDraft] = useState('')
  const [editingId, setEditingId] = useState('')
  const [editName, setEditName] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const d = await api.get('/admin/categories')
    setRows(d.categories || [])
  }, [])
  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const act = async (fn, okMsg) => {
    if (busy) return
    setBusy(true)
    setMsg('')
    try {
      await fn()
      setMsg(okMsg)
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  const create = () =>
    act(() => api.post('/admin/categories', { name: draft.trim() }), '已新增分类').then(() => setDraft(''))

  return (
    <div className="mt-4 max-w-[640px]">
      {msg && <p className="mb-2 text-[12px] text-gold-dark">{msg}</p>}
      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={20}
          placeholder="新分类名"
          className={`${fieldCls} w-[240px]`}
        />
        <button
          onClick={create}
          disabled={busy || !draft.trim()}
          className="press rounded-[2px] bg-gold px-5 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
        >
          新增
        </button>
      </div>
      <div className="mt-3 space-y-2 rounded-card border border-line bg-white p-4 shadow-card">
        {rows.map((c) => (
          <div key={c.id} className="flex items-center justify-between rounded-[2px] border border-line px-3 py-2">
            {editingId === c.id ? (
              <>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  maxLength={20}
                  className={`${fieldCls} flex-1`}
                />
                <div className="ml-2 flex shrink-0 gap-2">
                  <button
                    className="press text-[12px] text-gold"
                    onClick={() => {
                      act(() => api.put(`/admin/categories/${c.id}`, { name: editName.trim() }), '已改名').then(() =>
                        setEditingId(''),
                      )
                    }}
                  >
                    保存
                  </button>
                  <button className="press text-[12px] text-sub" onClick={() => setEditingId('')}>
                    取消
                  </button>
                </div>
              </>
            ) : (
              <>
                <div>
                  <p className="text-[13px] text-ink">{c.name}</p>
                  <p className="text-[10px] text-sub">{c.plan_count ?? 0} 件商品</p>
                </div>
                <div className="flex shrink-0 gap-3">
                  <button
                    className="press text-[12px] text-gold"
                    onClick={() => {
                      setEditingId(c.id)
                      setEditName(c.name)
                    }}
                  >
                    改名
                  </button>
                  <button
                    className="press text-[12px] text-burgundy"
                    onClick={() => {
                      if (!window.confirm(`删除分类「${c.name}」？挂靠商品将归入默认分类。`)) return
                      act(() => api.del(`/admin/categories/${c.id}`), '已删除')
                    }}
                  >
                    删除
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {rows.length === 0 && <p className="py-6 text-center text-[12px] text-sub">暂无分类</p>}
      </div>
    </div>
  )
}
