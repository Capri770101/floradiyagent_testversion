import React, { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { getOrder, updateOrder, listAddresses, publicConfig } from '../api/shop'
import { calcPayable } from '../utils/price'
import { toast } from '../utils/toast'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import { planImage } from '../assets/imageMap'

function SectionTitle({ title }) {
  return <h2 className="mb-2 mt-5 px-1 text-[16px] font-medium text-dark">{title}</h2>
}
function Row({ label, value, valueClass = 'text-ink' }) {
  return (
    <div className="flex justify-between">
      <span className="text-sub">{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  )
}

// 06 订单确认
export default function OrderConfirm() {
  const nav = useNavigate()
  const { state } = useLocation()
  const orderId = state?.orderId
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  // 收货人 / 配送时间 / 备注：真实可编辑，去支付时写回订单（review 点名的「假交互」修复）
  const [recipient, setRecipient] = useState({ name: '', phone: '', address: '' })
  const [deliveryOptions, setDeliveryOptions] = useState([])
  const [delivery, setDelivery] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [addresses, setAddresses] = useState([])
  const [selectedAddr, setSelectedAddr] = useState(null)

  // 配送时段由后端运营配置下发（红线2：不写死在页面）
  useEffect(() => {
    publicConfig()
      .then((cfg) => {
        const opts = cfg.delivery_options || []
        setDeliveryOptions(opts)
        if (opts.length > 0) setDelivery((cur) => cur || opts[0])
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    listAddresses()
      .then((list) => {
        setAddresses(list)
        if (list.length > 0) {
          setSelectedAddr(list[0].id)
          const d = list[0]
          setRecipient({ name: d.name, phone: d.phone, address: d.address })
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!orderId) {
      setLoading(false)
      return
    }
    getOrder(orderId)
      .then((o) => {
        setOrder(o)
        const r = o?.recipient || {}
        setRecipient({ name: r.name || '', phone: r.phone || '', address: r.address || '' })
        if (o?.delivery_time) setDelivery(o.delivery_time)
        if (o?.note) setNote(o.note)
      })
      .catch((e) => console.error('订单加载失败', e))
      .finally(() => setLoading(false))
  }, [orderId])

  if (loading) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="确认订单" />
        <div className="flex-1 p-5">
          <div className="h-20 animate-pulse rounded-card bg-line" />
        </div>
      </div>
    )
  }

  if (!order) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="确认订单" />
        <div className="flex-1 p-6 text-center text-[13px] text-sub">
          没有可结算的订单，请先从商品页下单或加入购物车。
          <div className="mt-4">
            <Button onClick={() => nav('/')}>去逛逛</Button>
          </div>
        </div>
      </div>
    )
  }

  const total = calcPayable(order.total_price, order.discount)

  const pickAddr = (a) => {
    setSelectedAddr(a.id)
    setRecipient({ name: a.name, phone: a.phone, address: a.address })
  }

  const onPay = async () => {
    if (saving) return
    setSaving(true)
    try {
      // 把真实收货信息写回订单，再跳转支付
      await updateOrder(orderId, { recipient, delivery, note })
      nav('/pay', { state: { orderId: order.order_id } })
    } catch (e) {
      toast('保存收货信息失败：' + e.message, 'error')
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="确认订单" />
      <div className="flex-1 overflow-y-auto px-4 pt-3">
        {order.items.map((it, i) => (
          <div
            key={i}
            className="flex items-center gap-3 rounded-card bg-white p-3 border border-line"
          >
            <SmartImage
              src={planImage(it)}
              color={imgColor(it.plan_id || it.name)}
              className="h-[62px] w-[62px] rounded-[4px]"
            />
            <div className="flex-1">
              <p className="text-[13px] font-medium text-ink">{it.name}</p>
              <p className="mt-2 text-[12px] font-medium text-ink">¥{it.price}</p>
            </div>
            <span className="text-[11px] text-sub">×{it.qty}</span>
          </div>
        ))}

        <SectionTitle title="收货人" />
        {addresses.length > 0 && (
          <div className="mb-2 space-y-2">
            {addresses.map((a) => (
              <button
                key={a.id}
                onClick={() => pickAddr(a)}
                className={`w-full rounded-card p-3 text-left border border-line transition ${
                  selectedAddr === a.id ? 'border border-pink bg-pink/5' : 'bg-white'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-dark">{a.name}</span>
                  <span className="text-[11px] text-sub">{a.phone}</span>
                  {a.is_default ? (
                    <span className="rounded-full bg-pink/10 px-2 py-0.5 text-[10px] text-pink">
                      默认
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-[11px] text-ink">{a.address}</p>
              </button>
            ))}
            <p className="text-[10px] text-sub">
              选中地址已自动填入下方，也可手动修改；去「我的地址」管理
            </p>
          </div>
        )}
        <div className="space-y-2 rounded-card bg-white p-4 border border-line">
          <input
            value={recipient.name}
            onChange={(e) => setRecipient({ ...recipient, name: e.target.value })}
            placeholder="收货人姓名"
            className="maison-field"
          />
          <input
            value={recipient.phone}
            onChange={(e) => setRecipient({ ...recipient, phone: e.target.value })}
            placeholder="手机号"
            inputMode="tel"
            className="maison-field"
          />
          <input
            value={recipient.address}
            onChange={(e) => setRecipient({ ...recipient, address: e.target.value })}
            placeholder="收货地址"
            className="maison-field"
          />
        </div>

        <SectionTitle title="配送时间" />
        {deliveryOptions.length === 0 ? (
          <p className="px-1 text-[11px] text-sub">配送时段加载中…</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {deliveryOptions.map((opt) => (
              <button
                key={opt}
                onClick={() => setDelivery(opt)}
                className={`rounded-pill px-3 py-1.5 text-[12px] transition ${
                  delivery === opt
                    ? 'bg-pink text-white'
                    : 'bg-white text-sub border border-line'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        )}

        <SectionTitle title="订单备注" />
        <div className="field-shell rounded-card bg-white p-4 border border-line">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="请填写您的备注（选填）"
            className="maison-field-inline w-full"
          />
        </div>

        <div className="mt-4 space-y-2 rounded-card bg-white p-4 text-[12px] border border-line">
          <Row label="商品金额" value={`¥${order.total_price}`} />
          <Row label="配送费" value={`¥20`} />
          <Row
            label="优惠券"
            value={`-¥${Number(order.discount || 0)}`}
            valueClass="text-pink"
          />
        </div>
        <div className="h-4" />
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-line bg-bg px-5 py-4">
        <div>
          <span className="text-[13px] text-ink">合计</span>
          <span className="ml-2 text-[20px] font-medium text-ink">¥{total}</span>
        </div>
        <Button style={{ width: 119 }} onClick={onPay} disabled={saving}>
          {saving ? '保存中…' : '去支付'}
        </Button>
      </div>
    </div>
  )
}
