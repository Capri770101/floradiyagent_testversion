// 店铺管理（合作花店）：列表 + 新增/编辑/删除。
// 数据来自 /admin/shops CRUD；首页「合作花店」按定位距离/评分自动排序，
// 故调整 lat/lng/rating 即可影响其在首页的先后。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

const EMPTY = {
  shop_id: '',
  name: '',
  rating: '4.5',
  price_range: '50-200',
  lat: '22.55',
  lng: '114.24',
  distance_km: '1.0',
  status: '营业中',
  intro: '',
  address: '',
  hours: '09:00 - 21:00',
  plan_ids: '',
}

export function Shops() {
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [editing, setEditing] = useState(null) // null=关闭, {} = 新增, shop = 编辑
  const [form, setForm] = useState(EMPTY)

  const load = useCallback(async () => {
    const data = await api.get('/admin/shops')
    setRows(data.shops || [])
  }, [])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const openNew = () => {
    setForm(EMPTY)
    setEditing({})
  }
  const openEdit = (s) => {
    setForm({
      shop_id: s.shop_id || '',
      name: s.name || '',
      rating: String(s.rating ?? ''),
      price_range: s.price_range || '',
      lat: s.lat != null ? String(s.lat) : '',
      lng: s.lng != null ? String(s.lng) : '',
      distance_km: s.distance_km != null ? String(s.distance_km) : '',
      status: s.status || '营业中',
      intro: s.intro || '',
      address: s.address || '',
      hours: s.hours || '',
      plan_ids: (s.plan_ids || []).join(', '),
    })
    setEditing(s)
  }

  const save = async () => {
    if (busy) return
    setBusy('saving')
    setMsg('')
    const payload = {
      name: form.name,
      rating: form.rating === '' ? undefined : Number(form.rating),
      price_range: form.price_range || undefined,
      lat: form.lat === '' ? undefined : Number(form.lat),
      lng: form.lng === '' ? undefined : Number(form.lng),
      distance_km: form.distance_km === '' ? undefined : Number(form.distance_km),
      status: form.status || undefined,
      intro: form.intro || undefined,
      address: form.address || undefined,
      hours: form.hours || undefined,
      plan_ids: form.plan_ids || undefined,
    }
    try {
      if (editing && editing.shop_id) {
        await api.put(`/admin/shops/${editing.shop_id}`, payload)
        setMsg('店铺已更新')
      } else {
        payload.shop_id = form.shop_id || undefined
        await api.post('/admin/shops', payload)
        setMsg('店铺已创建')
      }
      setEditing(null)
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  const del = async (s) => {
    if (busy || !window.confirm(`删除店铺「${s.name}」？其关联方案将一并解除。`)) return
    setBusy(s.shop_id)
    setMsg('')
    try {
      await api.del(`/admin/shops/${s.shop_id}`)
      setMsg('店铺已删除')
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  const field = (k) => (
    <input
      value={form[k]}
      onChange={(e) => setForm({ ...form, [k]: e.target.value })}
      placeholder="—"
      className="maison-field rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
    />
  )

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif-cn text-[22px] font-normal text-ink">店铺管理</h2>
          <p className="mt-1 text-[12px] text-sub">
            合作花店即首页「合作花店」数据源。调整 lat/lng（定位距离）与 rating（评分）可改变其在首页的先后。
          </p>
        </div>
        <button
          onClick={openNew}
          className="press rounded-[2px] bg-gold px-4 py-2 text-[12px] font-medium tracking-[1px] text-[#FAF8F5]"
        >
          ＋ 新增店铺
        </button>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      {/* 表格 */}
      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
        <table className="w-full min-w-[860px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">名称</th>
              <th className="px-4 py-3">评分</th>
              <th className="px-4 py-3">定位(lat/lng)</th>
              <th className="px-4 py-3">距离km</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">方案数</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.shop_id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3 text-sub">{s.shop_id}</td>
                <td className="px-4 py-3 text-ink">{s.name}</td>
                <td className="px-4 py-3">{s.rating}</td>
                <td className="px-4 py-3 text-sub">
                  {s.lat != null ? `${s.lat}, ${s.lng}` : '—'}
                </td>
                <td className="px-4 py-3 text-sub">{s.distance_km}</td>
                <td className="px-4 py-3">
                  <span className={s.status === '营业中' ? 'text-[#5b8a6a]' : 'text-burgundy'}>
                    {s.status || '营业中'}
                  </span>
                </td>
                <td className="px-4 py-3 text-sub">{(s.plan_ids || []).length}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      disabled={busy === s.shop_id}
                      onClick={() => openEdit(s)}
                      className="press rounded-[2px] border border-line bg-white px-2.5 py-1 text-[11px] disabled:opacity-40"
                    >
                      编辑
                    </button>
                    <button
                      disabled={busy === s.shop_id}
                      onClick={() => del(s)}
                      className="press rounded-[2px] border border-burgundy/40 bg-white px-2.5 py-1 text-[11px] text-burgundy disabled:opacity-40"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sub">
                  暂无店铺
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 新增 / 编辑表单 */}
      {editing !== null && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-6">
          <div className="w-full max-w-[560px] rounded-card border border-line bg-white p-5 shadow-card">
            <div className="flex items-center justify-between">
              <h3 className="font-serif-cn text-[18px] font-normal text-ink">
                {editing.shop_id ? '编辑店铺' : '新增店铺'}
              </h3>
              <button
                onClick={() => setEditing(null)}
                className="press text-[20px] leading-none text-sub"
                aria-label="关闭"
              >
                ×
              </button>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <label className="text-[11px] text-sub">
                店铺ID（新增可留空自动生成）
                {field('shop_id')}
              </label>
              <label className="text-[11px] text-sub">
                名称 *
                {field('name')}
              </label>
              <label className="text-[11px] text-sub">
                评分 0-5
                {field('rating')}
              </label>
              <label className="text-[11px] text-sub">
                价位区间（如 50-200）
                {field('price_range')}
              </label>
              <label className="text-[11px] text-sub">
                纬度 lat（影响首页距离排序）
                {field('lat')}
              </label>
              <label className="text-[11px] text-sub">
                经度 lng
                {field('lng')}
              </label>
              <label className="text-[11px] text-sub">
                兜底距离 km
                {field('distance_km')}
              </label>
              <label className="text-[11px] text-sub">
                状态
                {field('status')}
              </label>
              <label className="col-span-2 text-[11px] text-sub">
                营业时间
                {field('hours')}
              </label>
              <label className="col-span-2 text-[11px] text-sub">
                地址
                {field('address')}
              </label>
              <label className="col-span-2 text-[11px] text-sub">
                简介
                {field('intro')}
              </label>
              <label className="col-span-2 text-[11px] text-sub">
                关联方案 ID（逗号分隔）
                {field('plan_ids')}
              </label>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setEditing(null)}
                className="press rounded-[2px] border border-line bg-white px-4 py-2 text-[12px] text-sub"
              >
                取消
              </button>
              <button
                onClick={save}
                disabled={busy === 'saving'}
                className="press rounded-[2px] bg-gold px-5 py-2 text-[12px] font-medium tracking-[1px] text-[#FAF8F5] disabled:opacity-50"
              >
                {busy === 'saving' ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}