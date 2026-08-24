// 商家商品管理：商品列表 + 新增/编辑表单 + 上下架/批量 + 分类管理。
import React, { useCallback, useEffect, useState } from 'react'
import {
  merchantBatchToggle, merchantCategories, merchantCreateCategory,
  merchantCreatePlan, merchantDeleteCategory, merchantDeletePlan,
  merchantPlans, merchantRenameCategory, merchantStats,
  merchantTogglePlan, merchantUpdatePlan, merchantUpload,
} from '../api'
import { fmtMoney } from '../../utils/price'

const EMPTY_FORM = { name: '', price: '', desc: '', style: '', tags: '', effect_image_url: '', category_id: '' }

export function Products() {
  const [shops, setShops] = useState([])
  const [shopId, setShopId] = useState('')
  const [plans, setPlans] = useState([])
  const [categories, setCategories] = useState([])
  const [selected, setSelected] = useState([])
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)
  const [imgBusy, setImgBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [catDraft, setCatDraft] = useState('')
  const [catBusy, setCatBusy] = useState(false)
  const [editingCat, setEditingCat] = useState(null)

  const loadShops = useCallback(async () => {
    try {
      const st = await merchantStats()
      const list = (st.shops || []).map((s) => (typeof s === 'string' ? { id: s, name: s } : s))
      setShops(list)
      if (!shopId && list.length > 0) setShopId(list[0].id)
    } catch (e) {
      setErr(e.message || '店铺加载失败')
    }
  }, [shopId])

  const loadPlans = useCallback(async () => {
    if (!shopId) return
    setLoading(true)
    try {
      setPlans(await merchantPlans(shopId))
    } catch (e) {
      setErr(e.message || '商品加载失败')
    } finally {
      setLoading(false)
    }
  }, [shopId])

  const loadCategories = useCallback(async () => {
    try {
      setCategories(await merchantCategories())
    } catch (e) {
      setErr(e.message || '分类加载失败')
    }
  }, [])

  useEffect(() => { loadShops(); loadCategories() }, [loadShops, loadCategories])
  useEffect(() => { loadPlans() }, [loadPlans])

  const catName = (id) => (categories.find((c) => c.id === id) || {}).name || ''
  const toggleSelect = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const toggleAll = (on) => setSelected(on ? plans.map((p) => p.plan_id) : [])

  const openForm = (p = null) => {
    setEditing(p)
    setForm(p ? { name: p.name || '', price: String(p.price ?? ''), desc: p.desc || '', style: p.style || '', tags: (p.tags || []).join('，'), effect_image_url: p.effect_image_url || '', category_id: p.category_id || '' } : { ...EMPTY_FORM, category_id: categories[0]?.id || '' })
    setFormOpen(true)
  }

  const uploadImage = async (file) => {
    if (imgBusy) return
    if (file.size > 5 * 1024 * 1024) { setErr('图片不能超过 5MB'); return }
    setImgBusy(true)
    try {
      const res = await merchantUpload(file)
      setForm((f) => ({ ...f, effect_image_url: res.url }))
    } catch (e) {
      setErr(e.message || '上传失败')
    } finally {
      setImgBusy(false)
    }
  }

  const saveForm = async () => {
    if (busy) return
    if (!form.name.trim()) { setErr('商品名不能为空'); return }
    setBusy(true)
    setErr('')
    try {
      const data = { ...form, price: parseFloat(form.price) || 0, tags: form.tags ? form.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean) : [] }
      if (editing) {
        await merchantUpdatePlan(editing.plan_id, shopId, data)
      } else {
        await merchantCreatePlan(shopId, data)
      }
      setFormOpen(false)
      await loadPlans()
    } catch (e) {
      setErr(e.message || '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const togglePlan = async (p) => {
    try {
      await merchantTogglePlan(p.plan_id, shopId)
      await loadPlans()
    } catch (e) { setErr(e.message || '操作失败') }
  }

  const batchToggle = async (on) => {
    if (!selected.length) return
    try {
      await merchantBatchToggle(shopId, selected, on)
      setSelected([])
      await loadPlans()
    } catch (e) { setErr(e.message || '批量操作失败') }
  }

  const deletePlan = async (p) => {
    if (!confirm(`确认删除「${p.name}」？`)) return
    try {
      await merchantDeletePlan(p.plan_id, shopId)
      await loadPlans()
    } catch (e) { setErr(e.message || '删除失败') }
  }

  const addCategory = async () => {
    const name = catDraft.trim()
    if (!name || catBusy) return
    setCatBusy(true)
    try {
      await merchantCreateCategory(name)
      setCatDraft('')
      await loadCategories()
    } catch (e) { setErr(e.message || '新增分类失败') }
    finally { setCatBusy(false) }
  }

  const renameCategory = async (cat) => {
    const name = prompt('新分类名', cat.name)
    if (!name || name === cat.name) return
    try {
      await merchantRenameCategory(cat.id, name)
      await loadCategories()
    } catch (e) { setErr(e.message || '改名失败') }
  }

  const deleteCategory = async (cat) => {
    if (!confirm(`确认删除分类「${cat.name}」？挂靠商品将回落到默认分类。`)) return
    try {
      await merchantDeleteCategory(cat.id)
      await loadCategories()
    } catch (e) { setErr(e.message || '删除失败') }
  }

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">商品管理</h2>
        <button onClick={() => openForm()} className="rounded-[4px] bg-gold px-3 py-1.5 text-[11px] text-white">新增商品</button>
      </div>

      {shops.length > 1 && (
        <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
          {shops.map((s) => (
            <button key={s.id} onClick={() => setShopId(s.id)} className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${shopId === s.id ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'}`}>{s.name}</button>
          ))}
        </div>
      )}

      {/* 分类管理 */}
      <div className="mt-4 rounded-card border border-line bg-white p-3">
        <p className="text-[12px] font-medium text-ink">分类管理</p>
        <div className="mt-2 flex gap-2">
          <input value={catDraft} onChange={(e) => setCatDraft(e.target.value)} placeholder="新分类名" className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] outline-none focus:border-gold" />
          <button onClick={addCategory} disabled={!catDraft.trim() || catBusy} className="rounded-[4px] border border-gold/40 px-2.5 py-1.5 text-[11px] text-gold disabled:opacity-50">添加</button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {categories.map((c) => (
            <span key={c.id} className="group flex items-center gap-1 rounded-pill border border-line bg-bg/50 px-2.5 py-1 text-[11px] text-sub">
              {c.name} ({c.plan_count ?? 0})
              <button onClick={() => renameCategory(c)} className="ml-0.5 text-[10px] text-sub/50 hover:text-gold">改</button>
              <button onClick={() => deleteCategory(c)} className="text-[10px] text-sub/50 hover:text-burgundy">×</button>
            </span>
          ))}
        </div>
      </div>

      {/* 批量操作 */}
      {selected.length > 0 && (
        <div className="mt-3 flex gap-2">
          <button onClick={() => batchToggle(true)} className="rounded-[4px] border border-teal/40 px-3 py-1.5 text-[11px] text-teal">批量上架 ({selected.length})</button>
          <button onClick={() => batchToggle(false)} className="rounded-[4px] border border-burgundy/40 px-3 py-1.5 text-[11px] text-burgundy">批量下架 ({selected.length})</button>
        </div>
      )}

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      <div className="mt-4 space-y-3">
        {loading ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : plans.length === 0 ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">暂无商品</p>
        ) : (
          <>
            <div className="flex items-center gap-2 text-[11px] text-sub">
              <input type="checkbox" checked={selected.length === plans.length && plans.length > 0} onChange={(e) => toggleAll(e.target.checked)} className="accent-gold" />
              <span>全选</span>
            </div>
            {plans.map((p) => (
              <div key={p.plan_id} className="flex items-center gap-3 rounded-card border border-line bg-white p-3">
                <input type="checkbox" checked={selected.includes(p.plan_id)} onChange={() => toggleSelect(p.plan_id)} className="accent-gold" />
                <img src={p.effect_image_url || '/generated/placeholder.png'} alt="" className="h-[48px] w-[48px] shrink-0 rounded-[4px] border border-line object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-ink">{p.name}</p>
                  <p className="text-[11px] text-sub">{fmtMoney(p.price)} · {catName(p.category_id) || '未分类'} · {p.style || '—'}</p>
                  <p className="text-[10px] text-sub/70">{p.shop_status === 'on' ? '在售' : '已下架'}</p>
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  <button onClick={() => openForm(p)} className="rounded-[4px] border border-line px-2 py-0.5 text-[10px] text-sub">编辑</button>
                  <button onClick={() => togglePlan(p)} className={`rounded-[4px] border px-2 py-0.5 text-[10px] ${p.shop_status === 'on' ? 'border-burgundy/40 text-burgundy' : 'border-teal/40 text-teal'}`}>{p.shop_status === 'on' ? '下架' : '上架'}</button>
                  <button onClick={() => deletePlan(p)} className="rounded-[4px] border border-burgundy/40 px-2 py-0.5 text-[10px] text-burgundy">删除</button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* 新增/编辑弹窗 */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40">
          <div className="w-full max-w-md rounded-t-card bg-white p-5 pb-8">
            <div className="flex items-center justify-between">
              <p className="text-[15px] font-medium text-ink">{editing ? '编辑商品' : '新增商品'}</p>
              <button onClick={() => setFormOpen(false)} className="text-[20px] text-sub">×</button>
            </div>
            <div className="mt-4 space-y-3">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="商品名" className="maison-field" />
              <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="价格" inputMode="decimal" className="maison-field" />
              <textarea value={form.desc} onChange={(e) => setForm({ ...form, desc: e.target.value })} placeholder="描述" rows={2} className="maison-field resize-none" />
              <input value={form.style} onChange={(e) => setForm({ ...form, style: e.target.value })} placeholder="风格" className="maison-field" />
              <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="标签（逗号分隔）" className="maison-field" />
              <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} className="maison-field">
                <option value="">未分类</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <div>
                <label className="text-[11px] text-sub">效果图</label>
                <div className="mt-1 flex items-center gap-2">
                  <input type="file" accept="image/*" onChange={(e) => uploadImage(e.target.files?.[0])} className="hidden" id="img-upload" />
                  <label htmlFor="img-upload" className="cursor-pointer rounded-[4px] border border-line px-3 py-1.5 text-[11px] text-sub hover:border-gold">{imgBusy ? '上传中…' : '选择图片'}</label>
                  {form.effect_image_url && <img src={form.effect_image_url} className="h-10 w-10 rounded-[4px] border border-line object-cover" alt="" />}
                </div>
              </div>
            </div>
            <div className="mt-5 flex gap-3">
              <button onClick={() => setFormOpen(false)} className="flex-1 rounded-[4px] border border-line py-2.5 text-[13px] text-sub">取消</button>
              <button onClick={saveForm} disabled={busy} className="flex-1 rounded-[4px] bg-gold py-2.5 text-[13px] text-white disabled:opacity-50">{busy ? '保存中…' : '保存'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
