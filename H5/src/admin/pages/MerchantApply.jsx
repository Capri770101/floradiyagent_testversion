// 商家入驻审核（M5）：申请列表 + 审核（通过=提权+建店 / 拒绝带备注）+ 已入驻商家。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Pager } from '../App'

const APP_STATUS = {
  pending: { label: '待审核', cls: 'bg-pink/10 text-pink' },
  approved: { label: '已通过', cls: 'bg-[#5b8a6a]/15 text-[#5b8a6a]' },
  rejected: { label: '已拒绝', cls: 'bg-line/40 text-sub' },
}

export function MerchantApply() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [limit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [detail, setDetail] = useState(null)
  const [rejectNote, setRejectNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [merchants, setMerchants] = useState([])
  const [tab, setTab] = useState('apply') // apply | merchants

  const load = useCallback(async () => {
    const data = await api.get('/admin/merchant-applications', { status, limit, offset })
    setRows(data.applications)
    setTotal(data.total)
  }, [status, limit, offset])

  useEffect(() => {
    if (tab === 'apply') load().catch((e) => setMsg(e.message))
  }, [load, tab])

  useEffect(() => {
    if (tab !== 'merchants') return
    api
      .get('/admin/merchants')
      .then((d) => setMerchants(d.merchants || []))
      .catch((e) => setMsg(e.message))
  }, [tab])

  const act = async (appId, path, body, okMsg) => {
    if (busy) return
    setBusy(appId)
    setMsg('')
    try {
      const r = await api.post(`/admin/merchant-applications/${appId}/${path}`, body || {})
      setMsg(okMsg + (r.application?.shop_id ? ` · 已建店 ${r.application.shop_name}` : ''))
      setDetail(null)
      load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="flex items-center gap-6">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">商家入驻</h2>
        <div className="flex gap-1">
          <button
            onClick={() => setTab('apply')}
            className={`press rounded-pill px-4 py-1.5 text-[12px] ${tab === 'apply' ? 'bg-gold/15 font-medium text-gold' : 'text-sub'}`}
          >
            入驻申请
          </button>
          <button
            onClick={() => setTab('merchants')}
            className={`press rounded-pill px-4 py-1.5 text-[12px] ${tab === 'merchants' ? 'bg-gold/15 font-medium text-gold' : 'text-sub'}`}
          >
            已入驻商家
          </button>
        </div>
      </div>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      {tab === 'merchants' ? (
        <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
          <table className="w-full min-w-[640px] text-left text-[12px]">
            <thead>
              <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
                <th className="px-4 py-3">商家</th>
                <th className="px-4 py-3">手机号</th>
                <th className="px-4 py-3">店铺</th>
                <th className="px-4 py-3">入驻时间</th>
              </tr>
            </thead>
            <tbody>
              {merchants.map((m) => (
                <tr key={m.user_id + m.shop_id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3">
                    <p className="text-ink">{m.nickname || m.username}</p>
                    <p className="text-[10px] text-sub">{m.username}</p>
                  </td>
                  <td className="px-4 py-3 text-sub">{m.phone || '—'}</td>
                  <td className="px-4 py-3">
                    <p className="text-ink">{m.shop_name || m.shop_id}</p>
                    <p className="text-[10px] text-sub">{m.shop_id}</p>
                  </td>
                  <td className="px-4 py-3 text-sub">{m.shop_created_at || m.created_at}</td>
                </tr>
              ))}
              {merchants.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-10 text-center text-sub">
                    还没有入驻商家
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <div className="mt-4 flex items-center gap-2">
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setOffset(0)
              }}
              className="rounded-[2px] border border-line bg-white px-3 py-2 text-[12px]"
            >
              <option value="">全部状态</option>
              {Object.entries(APP_STATUS).map(([k, m]) => (
                <option key={k} value={k}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4 overflow-x-auto rounded-card border border-line bg-white shadow-card">
            <table className="w-full min-w-[780px] text-left text-[12px]">
              <thead>
                <tr className="border-b border-line text-[11px] tracking-[0.1em] text-sub">
                  <th className="px-4 py-3">申请单</th>
                  <th className="px-4 py-3">店铺名</th>
                  <th className="px-4 py-3">申请人</th>
                  <th className="px-4 py-3">执照号</th>
                  <th className="px-4 py-3">联系电话</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">提交时间</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => {
                  const m = APP_STATUS[a.status] || { label: a.status, cls: 'bg-line/40 text-sub' }
                  return (
                    <tr key={a.id} className="border-b border-line/60 last:border-0">
                      <td className="px-4 py-3 text-ink">{a.id}</td>
                      <td className="px-4 py-3 text-ink">{a.shop_name}</td>
                      <td className="px-4 py-3">{a.nickname || '—'}</td>
                      <td className="px-4 py-3 text-sub">{a.license_no || '—'}</td>
                      <td className="px-4 py-3 text-sub">{a.contact_phone || '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded-pill px-2 py-0.5 text-[11px] ${m.cls}`}>{m.label}</span>
                      </td>
                      <td className="px-4 py-3 text-sub">{a.created_at}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => {
                            setDetail(a)
                            setRejectNote(a.review_note || '')
                          }}
                          className="press rounded-[2px] border border-gold/40 bg-white px-2.5 py-1 text-[11px] text-gold"
                        >
                          审核
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-sub">
                      没有入驻申请
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Pager offset={offset} total={total} limit={limit} onChange={setOffset} />
        </>
      )}

      {/* 审核抽屉 */}
      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setDetail(null)}>
          <div
            className="h-full w-[420px] overflow-y-auto bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-serif-cn text-[18px] font-normal text-ink">入驻审核</h3>
              <button onClick={() => setDetail(null)} className="press text-[12px] text-sub">
                关闭 ✕
              </button>
            </div>
            <p className="mt-1 text-[11px] text-sub">{detail.id}</p>

            <p className="eyebrow mt-5">申请信息</p>
            <div className="mt-2 space-y-1 rounded-[2px] bg-bg px-3 py-2 text-[12px]">
              <p>
                店铺名：<span className="text-ink">{detail.shop_name}</span>
                <span className="ml-2 rounded-pill bg-pink/10 px-2 py-0.5 text-[11px] text-pink">
                  {(APP_STATUS[detail.status] || {}).label || detail.status}
                </span>
              </p>
              <p>申请人：{detail.nickname || '—'}</p>
              <p>联系人：{detail.contact_name || '—'} {detail.contact_phone || ''}</p>
              <p>执照号：{detail.license_no || '—'}</p>
              <p>地址：{detail.address || '—'}</p>
              {detail.intro && <p className="text-sub">简介：{detail.intro}</p>}
              {detail.review_note && <p className="text-sub">审核备注：{detail.review_note}</p>}
            </div>

            {detail.license_img && (
              <>
                <p className="eyebrow mt-5">执照图片</p>
                <img
                  src={detail.license_img}
                  alt="执照"
                  className="mt-2 h-[160px] w-full rounded-[4px] border border-line object-contain"
                />
              </>
            )}

            {detail.status === 'pending' && (
              <>
                <p className="eyebrow mt-5">拒绝备注</p>
                <textarea
                  value={rejectNote}
                  onChange={(e) => setRejectNote(e.target.value)}
                  maxLength={500}
                  placeholder="填写拒绝原因（可选）"
                  className="maison-field mt-2 w-full resize-none rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]"
                  rows={2}
                />
                <div className="mt-4 flex gap-2">
                  <button
                    onClick={() => act(detail.id, 'approve', {}, '已通过入驻')}
                    disabled={busy}
                    className="press flex-1 rounded-[2px] bg-gold py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                  >
                    通过并开通店铺
                  </button>
                  <button
                    onClick={() => act(detail.id, 'reject', { note: rejectNote }, '已拒绝')}
                    disabled={busy}
                    className="press flex-1 rounded-[2px] border border-line bg-white py-2 text-[12px] text-sub disabled:opacity-40"
                  >
                    拒绝
                  </button>
                </div>
                <p className="mt-2 text-[10px] text-sub/70">通过后申请人成为 merchant 并自动创建店铺。</p>
              </>
            )}

            {detail.status !== 'pending' && (
              <p className="mt-5 text-[12px] text-sub">
                {detail.reviewed_by ? `处理人：${detail.reviewed_by}` : ''}
                {detail.reviewed_at ? ` · ${detail.reviewed_at}` : ''}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
