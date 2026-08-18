// 商家入驻申请（M5 用户侧）：填写资料提交，查看审核进度。
import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { toast } from '../utils/toast'
import { merchantApply, merchantUpload, myMerchantApplication } from '../api/shop'
import { getProfile } from '../api/auth'

const STATUS_META = {
  pending: { label: '待审核', cls: 'bg-pink/10 text-pink' },
  approved: { label: '已通过', cls: 'bg-green/20 text-[#5b8a6a]' },
  rejected: { label: '已拒绝', cls: 'bg-line/40 text-sub' },
}

export default function MerchantApply() {
  const nav = useNavigate()
  const [form, setForm] = useState({
    shop_name: '',
    contact_name: '',
    contact_phone: '',
    license_no: '',
    license_img: '',
    address: '',
    intro: '',
  })
  const [apps, setApps] = useState([])
  const [busy, setBusy] = useState(false)
  const [imgBusy, setImgBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    myMerchantApplication()
      .then(setApps)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const onUpload = async (file) => {
    if (imgBusy) return
    if (file.size > 5 * 1024 * 1024) {
      toast('图片不能超过 5MB', 'error')
      return
    }
    setImgBusy(true)
    try {
      const url = await merchantUpload(file)
      setForm((f) => ({ ...f, license_img: url }))
      toast('执照图片已上传')
    } catch (e) {
      toast(e.message || '上传失败', 'error')
    } finally {
      setImgBusy(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    if (!form.shop_name.trim()) {
      toast('请填写店铺名称', 'error')
      return
    }
    setBusy(true)
    try {
      await merchantApply({
        shop_name: form.shop_name.trim(),
        contact_name: form.contact_name.trim(),
        contact_phone: form.contact_phone.trim(),
        license_no: form.license_no.trim(),
        license_img: form.license_img,
        address: form.address.trim(),
        intro: form.intro.trim(),
      })
      toast('入驻申请已提交，等待平台审核')
      setApps(await myMerchantApplication())
      setForm((f) => ({ ...f, shop_name: '', contact_name: '', contact_phone: '', license_no: '', address: '', intro: '' }))
    } catch (err) {
      toast(err.message || '提交失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  const pending = apps.some((a) => a.status === 'pending')

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="商家入驻" />
      <div className="flex-1 overflow-y-auto px-4 pb-8">
        {/* 审核进度 */}
        {apps.length > 0 && (
          <div className="mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">申请进度</p>
            <div className="mt-2 space-y-2">
              {apps.map((a) => {
                const m = STATUS_META[a.status] || { label: a.status, cls: 'bg-line/40 text-sub' }
                return (
                  <div key={a.id} className="flex items-center justify-between rounded-[2px] bg-bg px-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-[12px] text-ink">{a.shop_name}</p>
                      <p className="text-[10px] text-sub">{a.created_at}</p>
                      {a.review_note && <p className="mt-0.5 text-[10px] text-burgundy">备注：{a.review_note}</p>}
                    </div>
                    <span className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] ${m.cls}`}>{m.label}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {loading ? (
          <p className="mt-6 rounded-card bg-white p-8 text-center text-[12px] text-sub border border-line">加载中…</p>
        ) : pending ? (
          <p className="mt-3 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
            已有待审核的申请，请耐心等待平台审核
          </p>
        ) : (
          <form onSubmit={submit} className="mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">入驻资料</p>
            <p className="mt-1 text-[11px] text-sub">审核通过后将成为商家，可管理自己的店铺</p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-[11px] text-sub">店铺名称 *</label>
                <input value={form.shop_name} onChange={set('shop_name')} maxLength={40} placeholder="如 花漾工坊" className="maison-field w-full" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">联系人</label>
                <input value={form.contact_name} onChange={set('contact_name')} maxLength={30} placeholder="姓名" className="maison-field w-full" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">联系电话</label>
                <input value={form.contact_phone} onChange={set('contact_phone')} maxLength={20} placeholder="手机号" className="maison-field w-full" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">营业执照号</label>
                <input value={form.license_no} onChange={set('license_no')} maxLength={40} placeholder="统一社会信用代码" className="maison-field w-full" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">营业执照图片</label>
                <div className="flex items-center gap-3">
                  {form.license_img ? (
                    <img src={form.license_img} alt="执照" className="h-[64px] w-[96px] rounded-[4px] border border-line object-cover" />
                  ) : (
                    <div className="flex h-[64px] w-[96px] items-center justify-center rounded-[4px] border border-dashed border-line bg-bg text-[10px] text-sub/60">
                      未上传
                    </div>
                  )}
                  <label className="press inline-block cursor-pointer rounded-[4px] border border-line bg-bg px-3 py-2 text-[11px] text-sub">
                    {imgBusy ? '上传中…' : '上传'}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/gif"
                      className="hidden"
                      disabled={imgBusy}
                      onChange={(e) => {
                        const f = e.target.files?.[0]
                        if (f) onUpload(f)
                        e.target.value = ''
                      }}
                    />
                  </label>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">门店地址</label>
                <input value={form.address} onChange={set('address')} maxLength={120} placeholder="详细地址" className="maison-field w-full" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">店铺简介</label>
                <textarea value={form.intro} onChange={set('intro')} maxLength={200} rows={3} placeholder="一句话介绍你的花店特色" className="maison-field w-full resize-none" />
              </div>
            </div>
            <button
              type="submit"
              disabled={busy}
              className="press mt-5 w-full rounded-[2px] bg-dark py-3 text-[12px] font-medium tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
            >
              {busy ? '提交中…' : '提交入驻申请'}
            </button>
          </form>
        )}

        <button onClick={() => nav('/profile')} className="press mt-4 text-center text-[11px] tracking-[1px] text-sub">
          返回个人中心
        </button>
      </div>
    </div>
  )
}
