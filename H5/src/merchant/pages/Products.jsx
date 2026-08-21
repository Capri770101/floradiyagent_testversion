// 商家商品管理：商品列表 + 新增/编辑表单 + 上下架/批量 + 分类管理。
import React, { useCallback, useEffect, useState } from 'react'
import {
  merchantBatchToggle,
  merchantCategories,
  merchantCreateCategory,
  merchantCreatePlan,
  merchantDeleteCategory,
  merchantDeletePlan,
  merchantPlans,
  merchantRenameCategory,
  merchantStats,
  merchantTogglePlan,
  merchantUpdatePlan,
  merchantUpload,
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

  useEffect(() => {
    loadShops()
    loadCategories()
  }, [loadShops, loadCategories])

  useEffect(() => {
    loadPlans()
  }, [loadPlans])

  const catName = (id) => (categories.find((c) => c.id === id) || {}).name || ''

  const toggleSelect = (id) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  }

  const toggleAll = (on) => setSelected(on ? plans.map((p) => p.plan_id) : [])

  const openForm = (p = null) => {
    setEditing(p)
    setForm(
      p
        ? { name: p.name || '', price: String(p.price ?? ''), desc: p.desc || '', style: p.style || '', tags: (p.tags || []).join('，'), effect_image_url: p.effect_image_url || '', category_id: p.category_id || '' }
        : { ...EMPTY_FORM, category_id: categories[0]?.id || '' },
    )
    setFormOpen(true)
  }

  const uploadImage = async (file) => {
    if (imgBusy) return
    if (file.size > 5 * 1024 * 1024) {
      setErr('图片不能超过 5MB')
      return
    }
    if (!/\.(jpe?g|png|webp|gif)$/i.test(file.name)) {
      setErr('仅支持 jpg/png/webp/gif 格式')
      return
    }
    setImgBusy(true)
    try {
      const url = await merchantUpload(file)
      setForm((f) => ({ ...f, effect_image_url: url }))
    } catch (e) {
      setErr(e.message || '上传失败')
    } finally {
      setImgBusy(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    if (busy || !shopId) return
    if (!form.name.trim() || !Number(form.price) || Number(form.price) <= 0) {
      setErr('请填写商品名称和正确的价格')
      return
    }
    setBusy(true)
    setErr('')
    try {
      const payload = {
        name: form.name.trim(),
        price: Number(form.price),
        desc: form.desc.trim(),
        style: form.style.trim(),
        tags: form.tags.split(/[，,]/).map((t) => t.trim()).filter(Boolean),
        effect_image_url: form.effect_image_url,
        category_id: form.category_id || 'cat_daily',
      }
      if (editing) {
        await merchantUpdatePlan(shopId, editing.plan_id, payload)
      } else {
        await merchantCreatePlan(shopId, payload)
      }
      setFormOpen(false)
      await loadPlans()
    } catch (e2) {
      setErr(e2.message || '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const togglePlan = async (p) => {
    if (busy) return
    setBusy(true)
    try {
      await merchantTogglePlan(shopId, p.plan_id)
      await loadPlans()
    } catch (e2) {
      setErr(e2.message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const removePlan = async (p) => {
    if (!window.confirm(`确定删除「${p.name}」吗？删除后将从本店下架。`)) return
    if (busy) return
    setBusy(true)
    try {
      await merchantDeletePlan(shopId, p.plan_id)
      setSelected((s) => s.filter((x) => x !== p.plan_id))
      await loadPlans()
    } catch (e2) {
      setErr(e2.message || '删除失败')
    } finally {
      setBusy(false)
    }
  }

  const batchToggle = async (on) => {
    if (!shopId || selected.length === 0 || busy) return
    setBusy(true)
    try {
      await merchantBatchToggle(shopId, selected, on)
      setSelected([])
      await loadPlans()
    } catch (e2) {
      setErr(e2.message || '批量操作失败')
    } finally {
      setBusy(false)
    }
  }

  // ---- 分类 ----
  const addCategory = async () => {
    const name = catDraft.trim()
    if (!name || catBusy) return
    setCatBusy(true)
    try {
      await merchantCreateCategory(name)
      setCatDraft('')
      await loadCategories()
    } catch (e2) {
      setErr(e2.message || '新增失败')
    } finally {
      setCatBusy(false)
    }
  }

  const renameCategory = async (cat, name) => {
    const next = (name || '').trim()
    if (!next || next === cat.name) return
    setCatBusy(true)
    try {
      await merchantRenameCategory(cat.id, next)
      setEditingCat(null)
      await loadCategories()
    } catch (e2) {
      setErr(e2.message || '改名失败')
    } finally {
      setCatBusy(false)
    }
  }

  const removeCategory = async (cat) => {
    if (cat.plan_count > 0 && !window.confirm(`「${cat.name}」下还有 ${cat.plan_count} 件商品，删除后它们将归入默认分类，确定删除？`)) return
    if (cat.plan_count === 0 && !window.confirm(`确定删除分类「${cat.name}」？`)) return
    setCatBusy(true)
    try {
      await merchantDeleteCategory(cat.id)
      await loadCategories()
    } catch (e2) {
      setErr(e2.message || '删除失败')
    } finally {
      setCatBusy(false)
    }
  }

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">商品管理</h2>
        <button
          onClick={() => openForm()}
          className="press rounded-[2px] bg-gold px-4 py-2 text-[12px] tracking-[1px] text-[#FAF8F5]"
        >
          上架新商品
        </button>
      </div>

      {/* 店铺切换 */}
      {shops.length > 1 && (
        <div className="mt-4 flex gap-1.5">
          {shops.map((s) => (
            <button
              key={s.id}
              onClick={() => setShopId(s.id)}
              className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${
                shopId === s.id ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      {/* 批量操作 */}
      {selected.length > 0 && (
        <div className="mt-3 flex items-center gap-2 rounded-card border border-gold/30 bg-gold/5 p-2">
          <span className="text-[11px] text-sub">已选 {selected.length} 件</span>
          <button onClick={() => batchToggle(true)} className="press rounded-[2px] bg-gold px-3 py-1 text-[11px] text-[#FAF8F5]">
            批量上架
          </button>
          <button onClick={() => batchToggle(false)} className="press rounded-[2px] border border-line bg-white px-3 py-1 text-[11px] text-sub">
            批量下架
          </button>
          <button onClick={() => setSelected([])} className="press ml-auto text-[11px] text-sub">取消选择</button>
        </div>
      )}

      {/* 商品列表 */}
      <div className="mt-4 rounded-card border border-line bg-white">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <button onClick={() => toggleAll(!(selected.length === plans.length && plans.length > 0))} className="text-[11px] text-sub">
            {selected.length === plans.length && plans.length > 0 ? '取消全选' : '全选'}
          </button>
          <span className="text-[11px] text-sub">共 {plans.length} 件</span>
        </div>
        {loading ? (
          <p className="p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : plans.length === 0 ? (
          <p className="p-8 text-center text-[12px] text-sub">本店暂无商品</p>
        ) : (
          <ul className="divide-y divide-line/60">
            {plans.map((p) => (
              <li key={p.plan_id} className="flex items-center gap-3 px-4 py-3">
                <input
                  type="checkbox"
                  checked={selected.includes(p.plan_id)}
                  onChange={() => toggleSelect(p.plan_id)}
                  className="accent-gold"
                />
                {p.effect_image_url ? (
                  <img src={p.effect_image_url} alt="" className="h-12 w-12 rounded-[2px] border border-line object-cover" />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-[2px] bg-bg text-[10px] text-sub">无图</div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-[13px] text-ink">{p.name}</p>
                    {p.shop_status === 'off' && (
                      <span className="rounded-pill bg-bg px-2 py-0.5 text-[9px] text-sub">已下架</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] text-sub">
                    {fmtMoney(p.price)} · {catName(p.category_id) || '默认分类'}
                    {p.sold > 0 ? ` · 已售 ${p.sold}` : ''}
                  </p>
                </div>
                <button onClick={() => togglePlan(p)} className="press rounded-[2px] border border-line px-2.5 py-1 text-[11px] text-sub">
                  {p.shop_status === 'off' ? '上架' : '下架'}
                </button>
                <button onClick={() => openForm(p)} className="press rounded-[2px] border border-gold/40 px-2.5 py-1 text-[11px] text-gold">
                  编辑
                </button>
                <button onClick={() => removePlan(p)} className="press rounded-[2px] px-2 py-1 text-[11px] text-burgundy">
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 商品表单弹层 */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onClick={() => setFormOpen(false)}>
          <form
            onSubmit={submit}
            onClick={(e) => e.stopPropagation()}
            className="max-h-[85vh] w-[440px] overflow-y-auto rounded-card border border-line bg-white p-6 shadow-card"
          >
            <p className="eyebrow">Product</p>
            <h3 className="mt-1 font-serif-cn text-[20px] font-normal text-ink">
              {editing ? `编辑「${editing.name}」` : '上架新商品'}
            </h3>
            <div className="mt-5 space-y-3">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="商品名称"
                className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.price}
                  onChange={(e) => setForm({ ...form, price: e.target.value })}
                  placeholder="价格（元）"
                  className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
                />
                <input
                  value={form.style}
                  onChange={(e) => setForm({ ...form, style: e.target.value })}
                  placeholder="风格（如 韩式/日式）"
                  className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
                />
              </div>
              <textarea
                value={form.desc}
                onChange={(e) => setForm({ ...form, desc: e.target.value })}
                placeholder="商品描述"
                rows={2}
                className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
              />
              <input
                value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
                placeholder="标签（逗号分隔，如 玫瑰,情人节）"
                className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
              />
              <select
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2.5 text-[13px]"
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <div className="flex items-center gap-3">
                {form.effect_image_url ? (
                  <img src={form.effect_image_url} alt="" className="h-16 w-16 rounded-[2px] border border-line object-cover" />
                ) : (
                  <div className="flex h-16 w-16 items-center justify-center rounded-[2px] bg-bg text-[10px] text-sub">无图</div>
                )}
                <label className="press cursor-pointer rounded-[2px] border border-line px-3 py-2 text-[11px] text-sub">
                  {imgBusy ? '上传中…' : '上传商品图'}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && uploadImage(e.target.files[0])}
                  />
                </label>
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
                  className="press flex-1 rounded-[2px] border border-line py-2.5 text-[12px] text-sub"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className="press flex-1 rounded-[2px] bg-gold py-2.5 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                >
                  {busy ? '保存中…' : editing ? '保存修改' : '确认上架'}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* 分类管理 */}
      <div className="mt-6 rounded-card border border-line bg-white p-5">
        <p className="text-[13px] font-medium text-ink">商品分类</p>
        <div className="mt-3 flex gap-2">
          <input
            value={catDraft}
            onChange={(e) => setCatDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addCategory()}
            placeholder="新分类名称"
            className="maison-field flex-1 rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]"
          />
          <button
            onClick={addCategory}
            disabled={catBusy || !catDraft.trim()}
            className="press rounded-[2px] bg-gold px-4 py-2 text-[11px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
          >
            新增
          </button>
        </div>
        <ul className="mt-3 space-y-2">
          {categories.map((c) => (
            <li key={c.id} className="flex items-center justify-between rounded-[2px] border border-line px-3 py-2">
              {editingCat === c.id ? (
                <input
                  autoFocus
                  defaultValue={c.name}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') renameCategory(c, e.target.value)
                    if (e.key === 'Escape') setEditingCat(null)
                  }}
                  onBlur={(e) => renameCategory(c, e.target.value)}
                  className="maison-field flex-1 rounded-[2px] border border-gold bg-bg/40 px-2 py-1 text-[12px]"
                />
              ) : (
                <>
                  <span className="text-[12px] text-ink">{c.name}</span>
                  <span className="text-[10px] text-sub">{c.plan_count ?? 0} 件商品</span>
                  <div className="flex gap-2">
                    <button onClick={() => setEditingCat(c.id)} className="press text-[11px] text-sub">改名</button>
                    <button onClick={() => removeCategory(c)} className="press text-[11px] text-burgundy">删除</button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}