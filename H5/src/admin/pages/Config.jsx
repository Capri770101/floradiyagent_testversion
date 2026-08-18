// 运营配置（M7）：配送时段（动态增删）/ 配送费 / 优惠券规则，后端 operations_config 落库。
import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

export function Config() {
  const [opts, setOpts] = useState([])
  const [shippingFee, setShippingFee] = useState('')
  const [couponRules, setCouponRules] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const d = await api.get('/admin/config')
    setOpts(d.delivery_options || [])
    setShippingFee(String(d.shipping_fee ?? ''))
    setCouponRules(JSON.stringify(d.coupon_rules || {}, null, 2))
  }, [])

  useEffect(() => {
    load().catch((e) => setMsg(e.message))
  }, [load])

  const save = async () => {
    if (busy) return
    setBusy(true)
    setMsg('')
    let rules = {}
    try {
      rules = couponRules.trim() ? JSON.parse(couponRules) : {}
    } catch (e) {
      setMsg('优惠券规则不是合法 JSON')
      setBusy(false)
      return
    }
    try {
      const body = {
        delivery_options: opts.filter((o) => o.trim()),
        shipping_fee: shippingFee === '' ? undefined : Number(shippingFee),
        coupon_rules: rules,
      }
      if (body.shipping_fee !== undefined && (Number.isNaN(body.shipping_fee) || body.shipping_fee < 0)) {
        throw new Error('配送费必须是非负数字')
      }
      await api.put('/admin/config', body)
      setMsg('运营配置已保存')
      load()
    } catch (e) {
      setMsg(e.message || '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const setOpt = (i, v) => setOpts((arr) => arr.map((x, idx) => (idx === i ? v : x)))
  const addOpt = () => setOpts((arr) => [...arr, ''])
  const removeOpt = (i) => setOpts((arr) => arr.filter((_, idx) => idx !== i))

  const fieldCls = 'maison-field rounded-[2px] border border-line bg-bg/40 px-3 py-2 text-[12px]'

  return (
    <div>
      <h2 className="font-serif-cn text-[22px] font-normal text-ink">运营配置</h2>
      <p className="mt-1 text-[12px] text-sub">配送时段 / 运费 / 优惠券规则，保存后 C 端即时生效</p>

      {msg && <p className="mt-2 text-[12px] text-gold-dark">{msg}</p>}

      <div className="mt-4 max-w-[560px] rounded-card border border-line bg-white p-5 shadow-card">
        <p className="eyebrow">配送时段</p>
        <div className="mt-3 space-y-2">
          {opts.map((o, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={o}
                onChange={(e) => setOpt(i, e.target.value)}
                maxLength={40}
                placeholder="如 今天 18:00–20:00"
                className={`${fieldCls} flex-1`}
              />
              <button
                onClick={() => removeOpt(i)}
                className="press shrink-0 rounded-[2px] border border-line px-2.5 py-2 text-[11px] text-sub"
              >
                删除
              </button>
            </div>
          ))}
          <button onClick={addOpt} className="press rounded-[2px] border border-gold/40 px-3 py-1.5 text-[12px] text-gold">
            + 添加时段
          </button>
        </div>

        <p className="eyebrow mt-6">配送费（元）</p>
        <input
          value={shippingFee}
          onChange={(e) => setShippingFee(e.target.value.replace(/[^\d.]/g, ''))}
          inputMode="decimal"
          placeholder="5"
          className={`${fieldCls} mt-2 w-[160px]`}
        />

        <p className="eyebrow mt-6">优惠券规则（JSON）</p>
        <textarea
          value={couponRules}
          onChange={(e) => setCouponRules(e.target.value)}
          rows={6}
          placeholder='{"满减示例": "满 199 减 20"}'
          className={`${fieldCls} mt-2 w-full resize-none font-mono`}
        />
        <p className="mt-1 text-[10px] text-sub/70">key=规则名，value=规则描述（sandbox 演示，正式对接券引擎时扩展）</p>

        <button
          onClick={save}
          disabled={busy}
          className="press mt-5 rounded-[2px] bg-gold px-6 py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
        >
          {busy ? '保存中…' : '保存配置'}
        </button>
      </div>
    </div>
  )
}
