import React, { useEffect, useState } from 'react'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { IconPlus } from '../components/icons'
import { toast } from '../utils/toast'
import {
  listAddresses,
  addAddress,
  updateAddress,
  deleteAddress,
} from '../api/shop'

// 09 收货地址管理：列表 + 新增/编辑表单 + 删除 + 默认地址
const EMPTY = { name: '', phone: '', address: '', is_default: false }

export default function Addresses() {
  const [addresses, setAddresses] = useState([])
  const [editing, setEditing] = useState(null) // null=收起表单；{} 新增
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setAddresses(await listAddresses())
    } catch (e) {
      toast(e.message || '地址加载失败', 'error')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const startAdd = () => {
    setForm(EMPTY)
    setEditing({})
  }
  const startEdit = (a) => {
    setForm({ name: a.name, phone: a.phone, address: a.address, is_default: !!a.is_default })
    setEditing(a)
  }

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    if (!form.name.trim() || !form.phone.trim() || !form.address.trim()) {
      toast('请填写完整收货信息', 'error')
      return
    }
    setBusy(true)
    try {
      if (editing?.id) {
        await updateAddress(editing.id, form)
        toast('地址已更新')
      } else {
        await addAddress(form)
        toast('地址已添加')
      }
      setEditing(null)
      await load()
    } catch (e) {
      toast(e.message || '保存失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  const setDefault = async (a) => {
    if (a.is_default) return
    try {
      await updateAddress(a.id, { is_default: true })
      await load()
    } catch (e) {
      toast(e.message || '设置失败', 'error')
    }
  }

  const remove = async (a) => {
    if (!window.confirm(`删除地址「${a.address}」？`)) return
    try {
      await deleteAddress(a.id)
      toast('地址已删除')
      await load()
    } catch (e) {
      toast(e.message || '删除失败', 'error')
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="我的地址" right={editing ? null : undefined} />
      <div className="flex-1 overflow-y-auto px-4 pt-3 pb-6">
        {addresses.length === 0 && !editing && (
          <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub shadow-card">
            还没有收货地址，添加后下单即可一键选择
          </p>
        )}

        {addresses.map((a) => (
          <div
            key={a.id}
            className="mb-3 rounded-card bg-white p-4 shadow-card"
          >
            <div className="flex items-center gap-2">
              <p className="text-[14px] font-medium text-dark">{a.name}</p>
              <p className="text-[12px] text-sub">{a.phone}</p>
              {a.is_default ? (
                <span className="rounded-full bg-pink/10 px-2 py-0.5 text-[10px] text-pink">
                  默认
                </span>
              ) : (
                <button className="press text-[10px] text-sub" onClick={() => setDefault(a)}>
                  设为默认
                </button>
              )}
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-ink">{a.address}</p>
            <div className="mt-3 flex justify-end gap-3">
              <button className="press text-[12px] text-sub" onClick={() => startEdit(a)}>
                编辑
              </button>
              <button className="press text-[12px] text-pink" onClick={() => remove(a)}>
                删除
              </button>
            </div>
          </div>
        ))}

        {editing !== null && (
          <form onSubmit={submit} className="mt-2 rounded-card bg-white p-4 shadow-card">
            <p className="mb-3 text-[13px] font-medium text-dark">
              {editing?.id ? '编辑地址' : '新增地址'}
            </p>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="收货人姓名"
              className="mb-2 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-[12px] outline-none"
            />
            <input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="手机号"
              inputMode="tel"
              className="mb-2 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-[12px] outline-none"
            />
            <input
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder="详细地址（省市区 + 街道门牌）"
              className="mb-2 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-[12px] outline-none"
            />
            <label className="mb-3 flex items-center gap-2 text-[12px] text-ink">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              />
              设为默认地址
            </label>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                className="!h-[34px] !text-[12px]"
                type="button"
                onClick={() => setEditing(null)}
              >
                取消
              </Button>
              <Button className="!h-[34px] !text-[12px]" type="submit" disabled={busy}>
                {busy ? '保存中…' : '保存'}
              </Button>
            </div>
          </form>
        )}

        {!editing && (
          <Button className="mt-4 w-full" onClick={startAdd}>
            <IconPlus width={16} height={16} className="mr-1" /> 新增地址
          </Button>
        )}
      </div>
    </div>
  )
}