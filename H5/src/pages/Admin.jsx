import React, { useState, useEffect, useCallback } from 'react'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'
import { toast } from '../utils/toast'
import {
  adminListPlans,
  adminListShops,
  adminCreatePlan,
  adminUpdatePlan,
  adminDeletePlan,
  adminCreateShop,
  adminUpdateShop,
  adminDeleteShop,
} from '../api/shop'

const CATEGORIES = [
  { id: 'cat_holiday', name: '节日祝福' },
  { id: 'cat_love', name: '浪漫告白' },
  { id: 'cat_daily', name: '日常陪伴' },
]

const EMPTY_PLAN = {
  plan_id: '',
  name: '',
  price: '',
  desc: '',
  merchant_name: '',
  style: '',
  category_id: 'cat_daily',
  tags: '',
}

const EMPTY_SHOP = {
  shop_id: '',
  name: '',
  rating: '',
  distance_km: '',
  price_range: '',
  intro: '',
  plan_ids: '',
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[12px] text-sub">{label}</span>
      {children}
    </label>
  )
}

const inputCls =
  'mt-1 w-full maison-field'

function PlanForm({ initial, onDone, onCancel }) {
  const [f, setF] = useState(() => ({
    ...EMPTY_PLAN,
    ...initial,
    tags: Array.isArray(initial?.tags) ? initial.tags.join(', ') : (initial?.tags || ''),
  }))
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))

  const submit = async () => {
    if (!f.name.trim()) return toast('请填写方案名称', 'error')
    setBusy(true)
    try {
      const payload = {
        name: f.name.trim(),
        price: Number(f.price) || 0,
        desc: f.desc.trim(),
        merchant_name: f.merchant_name.trim(),
        style: f.style.trim(),
        category_id: f.category_id,
        tags: f.tags,
        ...(f.plan_id ? { plan_id: f.plan_id.trim() } : {}),
      }
      if (initial?.plan_id) {
        await adminUpdatePlan(initial.plan_id, payload)
        toast('方案已更新')
      } else {
        await adminCreatePlan(payload)
        toast('方案已创建')
      }
      onDone()
    } catch (e) {
      toast(e.message || '保存失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-card bg-white p-4 border border-line">
      <Field label="方案 ID（留空自动生成）">
        <input
          className={inputCls}
          value={f.plan_id}
          onChange={set('plan_id')}
          disabled={!!initial?.plan_id}
          placeholder="如 P007"
        />
      </Field>
      <Field label="名称 *">
        <input className={inputCls} value={f.name} onChange={set('name')} placeholder="如 满天星花束" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="价格（元）">
          <input className={inputCls} value={f.price} onChange={set('price')} inputMode="numeric" placeholder="99" />
        </Field>
        <Field label="风格">
          <input className={inputCls} value={f.style} onChange={set('style')} placeholder="自然 / 浪漫…" />
        </Field>
      </div>
      <Field label="描述">
        <input className={inputCls} value={f.desc} onChange={set('desc')} placeholder="一句话描述" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="商家名">
          <input className={inputCls} value={f.merchant_name} onChange={set('merchant_name')} placeholder="花漾工坊" />
        </Field>
        <Field label="分类">
          <select className={inputCls} value={f.category_id} onChange={set('category_id')}>
            {CATEGORIES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="标签（逗号分隔）">
        <input className={inputCls} value={f.tags} onChange={set('tags')} placeholder="母亲节, 温馨" />
      </Field>
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={onCancel}>
          取消
        </Button>
        <Button className="flex-1" disabled={busy} onClick={submit}>
          {busy ? '保存中…' : '保存'}
        </Button>
      </div>
    </div>
  )
}

function ShopForm({ initial, onDone, onCancel }) {
  const [f, setF] = useState(() => ({
    ...EMPTY_SHOP,
    ...initial,
    plan_ids: Array.isArray(initial?.plan_ids) ? initial.plan_ids.join(', ') : (initial?.plan_ids || ''),
  }))
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }))

  const submit = async () => {
    if (!f.name.trim()) return toast('请填写店铺名称', 'error')
    setBusy(true)
    try {
      const payload = {
        name: f.name.trim(),
        rating: Number(f.rating) || 4.5,
        distance_km: Number(f.distance_km) || 1,
        price_range: f.price_range.trim(),
        intro: f.intro.trim(),
        plan_ids: f.plan_ids,
        ...(f.shop_id ? { shop_id: f.shop_id.trim() } : {}),
      }
      if (initial?.shop_id) {
        await adminUpdateShop(initial.shop_id, payload)
        toast('店铺已更新')
      } else {
        await adminCreateShop(payload)
        toast('店铺已创建')
      }
      onDone()
    } catch (e) {
      toast(e.message || '保存失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-card bg-white p-4 border border-line">
      <Field label="店铺 ID（留空自动生成）">
        <input
          className={inputCls}
          value={f.shop_id}
          onChange={set('shop_id')}
          disabled={!!initial?.shop_id}
          placeholder="如 S006"
        />
      </Field>
      <Field label="名称 *">
        <input className={inputCls} value={f.name} onChange={set('name')} placeholder="如 巷陌花集" />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="评分">
          <input className={inputCls} value={f.rating} onChange={set('rating')} inputMode="decimal" placeholder="4.5" />
        </Field>
        <Field label="距离(km)">
          <input className={inputCls} value={f.distance_km} onChange={set('distance_km')} inputMode="decimal" placeholder="1.2" />
        </Field>
        <Field label="价位">
          <input className={inputCls} value={f.price_range} onChange={set('price_range')} placeholder="50-200" />
        </Field>
      </div>
      <Field label="简介">
        <input className={inputCls} value={f.intro} onChange={set('intro')} placeholder="一句话介绍" />
      </Field>
      <Field label="关联方案 ID（逗号分隔）">
        <input className={inputCls} value={f.plan_ids} onChange={set('plan_ids')} placeholder="P004, P005" />
      </Field>
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={onCancel}>
          取消
        </Button>
        <Button className="flex-1" disabled={busy} onClick={submit}>
          {busy ? '保存中…' : '保存'}
        </Button>
      </div>
    </div>
  )
}

export default function Admin() {
  const [tab, setTab] = useState('plans')
  const [plans, setPlans] = useState([])
  const [shops, setShops] = useState([])
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [forbidden, setForbidden] = useState(false)

  const load = useCallback(async () => {
    try {
      const [ps, ss] = await Promise.all([adminListPlans(), adminListShops()])
      setPlans(ps)
      setShops(ss)
      setForbidden(false)
    } catch (e) {
      if (/403/.test(e.message)) {
        setForbidden(true)
        setError('当前账号没有管理员权限，请联系管理员授权')
      } else {
        setError(e.message || '加载失败')
      }
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const del = async (kind, item) => {
    if (!window.confirm(`确定删除「${item.name}」？`)) return
    try {
      if (kind === 'plan') await adminDeletePlan(item.plan_id)
      else await adminDeleteShop(item.shop_id)
      toast('已删除')
      load()
    } catch (e) {
      toast(e.message || '删除失败', 'error')
    }
  }

  const closeForm = () => {
    setEditing(null)
    setCreating(false)
    load()
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="管理后台" />
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {error && <p className="mb-3 text-[12px] text-pink">{error}</p>}

        {forbidden ? (
          <p className="mt-10 rounded-card bg-white p-8 text-center text-[13px] text-sub border border-line">
            无管理员权限
            <br />
            <span className="mt-1 block text-[11px] text-sub/70">
              仅 admin 角色可管理方案与店铺信息，请联系系统管理员授权
            </span>
          </p>
        ) : (
          <>
            <div className="mb-4 flex gap-2">
          <Button
            variant={tab === 'plans' ? 'primary' : 'secondary'}
            className="flex-1"
            onClick={() => {
              setTab('plans')
              setEditing(null)
              setCreating(false)
            }}
          >
            方案管理（{plans.length}）
          </Button>
          <Button
            variant={tab === 'shops' ? 'primary' : 'secondary'}
            className="flex-1"
            onClick={() => {
              setTab('shops')
              setEditing(null)
              setCreating(false)
            }}
          >
            店铺管理（{shops.length}）
          </Button>
        </div>

        {(creating || editing) && (
          <div className="mb-4">
            {tab === 'plans' ? (
              <PlanForm
                initial={editing}
                onDone={closeForm}
                onCancel={() => {
                  setCreating(false)
                  setEditing(null)
                }}
              />
            ) : (
              <ShopForm
                initial={editing}
                onDone={closeForm}
                onCancel={() => {
                  setCreating(false)
                  setEditing(null)
                }}
              />
            )}
          </div>
        )}

        {!creating && !editing && (
          <Button className="mb-4 w-full" onClick={() => setCreating(true)}>
            + 新增{tab === 'plans' ? '方案' : '店铺'}
          </Button>
        )}

        <div className="space-y-2">
          {tab === 'plans' &&
            plans.map((p) => (
              <div key={p.plan_id} className="flex items-center gap-3 rounded-card bg-white p-3 border border-line">
                <SmartImage
                  src={itemImagePath('plans', p.plan_id)}
                  imgKey="home_rec_1"
                  className="h-[52px] w-[52px] shrink-0 rounded-[4px]"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-dark">{p.name}</p>
                  <p className="text-[11px] text-sub">
                    {p.plan_id} · ¥{p.price}
                    {p.style ? ` · ${p.style}` : ''}
                  </p>
                </div>
                <button
                  className="press text-[12px] text-pink"
                  onClick={() => setEditing(p)}
                >
                  编辑
                </button>
                <button className="press text-[12px] text-sub" onClick={() => del('plan', p)}>
                  删除
                </button>
              </div>
            ))}
          {tab === 'shops' &&
            shops.map((s) => (
              <div key={s.shop_id} className="flex items-center gap-3 rounded-card bg-white p-3 border border-line">
                <SmartImage
                  src={itemImagePath('shops', s.shop_id)}
                  imgKey="shop_logo"
                  className="h-[52px] w-[52px] shrink-0 rounded-[4px]"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-dark">{s.name}</p>
                  <p className="text-[11px] text-sub">
                    {s.shop_id} · {s.rating} 分 · {s.distance_km}km · ¥{s.price_range}
                  </p>
                </div>
                <button className="press text-[12px] text-pink" onClick={() => setEditing(s)}>
                  编辑
                </button>
                <button className="press text-[12px] text-sub" onClick={() => del('shop', s)}>
                  删除
                </button>
              </div>
            ))}
        </div>
          </>
        )}
      </div>
    </div>
  )
}