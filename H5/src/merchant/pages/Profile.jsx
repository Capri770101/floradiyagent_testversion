// 商家店铺设置：资料编辑（含封面/Logo/图片上传）+ 评价回复管理。
import React, { useCallback, useEffect, useState } from 'react'
import {
  merchantReplyReview,
  merchantReviews,
  merchantStats,
  merchantUpdateShop,
  merchantUpload,
} from '../api'

function Field({ label, hint, value, onChange, textarea }) {
  return (
    <div>
      <label className="block text-[12px] text-sub">
        {label}
        {hint && <span className="ml-1 text-[10px] text-sub/60">{hint}</span>}
      </label>
      {textarea ? (
        <textarea
          value={value || ''}
          onChange={onChange}
          rows={2}
          className="maison-field mt-1 w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[13px]"
        />
      ) : (
        <input
          value={value || ''}
          onChange={onChange}
          className="maison-field mt-1 w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[13px]"
        />
      )}
    </div>
  )
}

export function Profile() {
  const [shops, setShops] = useState([])
  const [shop, setShop] = useState(null)
  const [saving, setSaving] = useState(false)
  const [imgBusy, setImgBusy] = useState(false)
  const [reviews, setReviews] = useState([])
  const [replyOpen, setReplyOpen] = useState('')
  const [replyDraft, setReplyDraft] = useState({})
  const [replyBusy, setReplyBusy] = useState('')
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  const loadShops = useCallback(async () => {
    try {
      const st = await merchantStats()
      const list = (st.shops || []).map((s) => (typeof s === 'string' ? { id: s, name: s } : s))
      setShops(list)
      setShop((prev) => prev || list[0] || null)
    } catch (e) {
      setErr(e.message || '店铺加载失败')
    }
  }, [])

  const loadReviews = useCallback(async () => {
    try {
      setReviews(await merchantReviews())
    } catch (e) {
      setErr(e.message || '评价加载失败')
    }
  }, [])

  useEffect(() => {
    loadShops()
    loadReviews()
    setLoading(false)
  }, [loadShops, loadReviews])

  const changeShop = (s) => {
    setShop(s)
    setErr('')
  }

  const save = async () => {
    if (!shop || saving) return
    setSaving(true)
    setErr('')
    try {
      const updated = await merchantUpdateShop(shop.id || shop.shop_id, {
        name: shop.name?.trim(),
        intro: shop.intro?.trim(),
        price_range: shop.price_range?.trim(),
        status: shop.status,
        image: shop.image || '',
        cover: shop.cover || '',
        logo: shop.logo || '',
        hours: shop.hours || '',
        address: shop.address || '',
        notice: shop.notice || '',
      })
      setShop(updated)
    } catch (e) {
      setErr(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const upload = async (file, target) => {
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
      setShop((s) => (s ? { ...s, [target]: url } : s))
    } catch (e) {
      setErr(e.message || '上传失败')
    } finally {
      setImgBusy(false)
    }
  }

  const submitReply = async (r) => {
    const text = (replyDraft[r.id] || '').trim()
    if (!text) {
      setErr('请输入回复内容')
      return
    }
    if (replyBusy) return
    setReplyBusy(r.id)
    try {
      await merchantReplyReview(r.id, text)
      setReplyOpen('')
      setReplyDraft((d) => ({ ...d, [r.id]: '' }))
      await loadReviews()
    } catch (e) {
      setErr(e.message || '回复失败')
    } finally {
      setReplyBusy('')
    }
  }

  const uploadBlock = ({ field, label, previewCls }) => (
    <div>
      <p className="text-[12px] text-sub">{label}</p>
      {shop?.[field] ? (
        <img src={shop[field]} alt={label} className={`mt-1 rounded-[2px] border border-line object-cover ${previewCls || 'h-20 w-32'}`} />
      ) : (
        <div className={`mt-1 flex items-center justify-center rounded-[2px] bg-bg text-[10px] text-sub ${previewCls || 'h-20 w-32'}`}>暂无图片</div>
      )}
      <label className="press mt-1 inline-block cursor-pointer rounded-[2px] border border-line px-2.5 py-1 text-[11px] text-sub">
        {imgBusy ? '上传中…' : '上传'}
        <input
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], field)}
        />
      </label>
    </div>
  )

  if (loading) {
    return <p className="text-[12px] text-sub">加载中…</p>
  }

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">店铺设置</h2>
      <p className="mt-1 text-[12px] text-sub">资料与装修同步展示在顾客端门店页</p>

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      {shops.length > 1 && (
        <div className="mt-4 flex gap-1.5">
          {shops.map((s) => (
            <button
              key={s.id}
              onClick={() => changeShop(s)}
              className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${
                shop?.id === s.id ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {!shop ? (
        <p className="mt-4 rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">
          暂无绑定店铺，请联系平台管理员开通
        </p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* 资料 */}
          <div className="rounded-card border border-line bg-white p-5">
            <p className="text-[13px] font-medium text-ink">店铺资料</p>
            <div className="mt-4 space-y-3">
              <Field label="店铺名称" value={shop.name} onChange={(e) => setShop({ ...shop, name: e.target.value })} />
              <Field label="简介" value={shop.intro} onChange={(e) => setShop({ ...shop, intro: e.target.value })} />
              <div className="grid grid-cols-2 gap-3">
                <Field label="人均消费档位" hint="如 50-100" value={shop.price_range} onChange={(e) => setShop({ ...shop, price_range: e.target.value })} />
                <Field label="营业时间" hint="如 09:00 - 21:00" value={shop.hours} onChange={(e) => setShop({ ...shop, hours: e.target.value })} />
              </div>
              <Field label="地址" value={shop.address} onChange={(e) => setShop({ ...shop, address: e.target.value })} />
              <Field label="公告" textarea value={shop.notice} onChange={(e) => setShop({ ...shop, notice: e.target.value })} />
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3">
              {uploadBlock({ field: 'cover', label: '封面横幅' })}
              {uploadBlock({ field: 'logo', label: '店铺 Logo', previewCls: 'h-20 w-20 rounded-full' })}
              {uploadBlock({ field: 'image', label: '店铺照片' })}
            </div>
            <button
              onClick={save}
              disabled={saving}
              className="press mt-5 w-full rounded-[2px] bg-gold py-2.5 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
            >
              {saving ? '保存中…' : '保存资料'}
            </button>
          </div>

          {/* 评价回复 */}
          <div className="rounded-card border border-line bg-white p-5">
            <p className="text-[13px] font-medium text-ink">顾客评价</p>
            {reviews.length === 0 ? (
              <p className="mt-4 text-center text-[12px] text-sub">暂无评价</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {reviews.map((r) => (
                  <li key={r.id} className="rounded-[2px] border border-line p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] text-ink">{r.nickname || '顾客'}</span>
                      <span className="text-[11px] text-gold">{'★'.repeat(Math.max(1, Math.min(5, r.rating || 5)))}</span>
                    </div>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink">{r.content}</p>
                    {r.reply ? (
                      <p className="mt-2 rounded-[2px] bg-bg/50 px-2 py-1.5 text-[11px] text-sub">
                        商家回复：{r.reply}
                      </p>
                    ) : replyOpen === r.id ? (
                      <div className="mt-2">
                        <textarea
                          autoFocus
                          value={replyDraft[r.id] || ''}
                          onChange={(e) => setReplyDraft((d) => ({ ...d, [r.id]: e.target.value }))}
                          rows={2}
                          placeholder="回复这条评价…"
                          className="maison-field w-full rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]"
                        />
                        <div className="mt-1.5 flex justify-end gap-2">
                          <button onClick={() => setReplyOpen('')} className="press rounded-[2px] border border-line px-3 py-1 text-[11px] text-sub">
                            取消
                          </button>
                          <button
                            onClick={() => submitReply(r)}
                            disabled={!!replyBusy}
                            className="press rounded-[2px] bg-gold px-3 py-1 text-[11px] text-[#FAF8F5] disabled:opacity-40"
                          >
                            {replyBusy === r.id ? '发送中…' : '发布回复'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button onClick={() => setReplyOpen(r.id)} className="press mt-2 text-[11px] text-gold">
                        回复评价
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}