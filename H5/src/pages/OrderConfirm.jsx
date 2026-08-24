import React, { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { getOrder, getShop, updateOrder, listAddresses, publicConfig } from '../api/shop'
import { calcPayable } from '../utils/price'
import { toast } from '../utils/toast'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import { planImage } from '../assets/imageMap'
import DeliveryLocationPicker from '../components/DeliveryLocationPicker'
import AddressSearchInput from '../components/AddressSearchInput'

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

// 最快配送默认项（拼接店铺配送时长，如「尽快送达（约22分钟）」）
const FAST_DELIVERY = '尽快送达'

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
  const [delivery, setDelivery] = useState(FAST_DELIVERY) // 默认最快配送
  const [shopDelivery, setShopDelivery] = useState('')    // 店铺配送时长（如「约22分钟」）
  const [customDelivery, setCustomDelivery] = useState('') // 自定义时间输入
  const [shippingFee, setShippingFee] = useState(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [addresses, setAddresses] = useState([])
  const [selectedAddr, setSelectedAddr] = useState(null)
  // 配送位置（地图选点，与收货地址分开）
  const [deliveryLoc, setDeliveryLoc] = useState(null) // {lat, lng, address}
  const [locPickerOpen, setLocPickerOpen] = useState(false)

  // 配送时段 / 配送费由后端运营配置下发（红线2：不写死在页面）
  useEffect(() => {
    publicConfig()
      .then((cfg) => {
        const opts = cfg.delivery_options || []
        setDeliveryOptions(opts)
        if (opts.length > 0) setDelivery((cur) => cur || opts[0])
        if (cfg.shipping_fee != null) setShippingFee(cfg.shipping_fee)
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
        // 配送时间：订单已有值则回显；否则默认「尽快送达」
        if (o?.delivery_time) setDelivery(o.delivery_time)
        else setDelivery(FAST_DELIVERY)
        if (o?.note) setNote(o.note)
        // 回显已有配送位置
        if (o?.delivery_location?.lat != null) {
          setDeliveryLoc(o.delivery_location)
        }
        // 拉取店铺配送时长，用于「尽快送达」文案
        if (o?.shop_id) {
          getShop(o.shop_id)
            .then((s) => {
              if (s?.delivery_time) setShopDelivery(s.delivery_time)
            })
            .catch(() => {})
        }
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

  const total = calcPayable(order.total_price, order.discount, shippingFee)

  const pickAddr = (a) => {
    setSelectedAddr(a.id)
    setRecipient({ name: a.name, phone: a.phone, address: a.address })
  }

  const onPay = async () => {
    if (saving) return
    setSaving(true)
    try {
      // 自定义时间选中时，用输入框内容作为配送时间
      const finalDelivery = delivery === 'custom' && customDelivery.trim()
        ? customDelivery.trim()
        : delivery
      if (delivery === 'custom' && !customDelivery.trim()) {
        toast('请填写自定义配送时间', 'error')
        setSaving(false)
        return
      }
      // 把真实收货信息写回订单，再跳转支付
      await updateOrder(orderId, { recipient, delivery: finalDelivery, note, delivery_location: deliveryLoc })
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
          <Reveal key={i} delay={i * 140}>
          <div
            className="flex items-center gap-3 rounded-card bg-white p-3 border border-line"
          >
            <SmartImage
              src={planImage(it)}
              color={imgColor(it.plan_id || it.name)}
              className="h-[62px] w-[62px] rounded-[4px]"
            />
            <div className="flex-1">
              <p className="text-[13px] font-medium text-ink">{it.name}</p>
              <p className="mt-2 text-[12px] font-medium text-ink">¥{Number(it.price).toFixed(2)}</p>
            </div>
            <span className="text-[11px] text-sub">×{it.qty}</span>
          </div>
          </Reveal>
        ))}

        <Reveal>
        <SectionTitle title="收货人" />
        </Reveal>
        {addresses.length > 0 && (
          <div className="mb-2 space-y-2">
            {addresses.map((a, i) => (
              <Reveal key={a.id} delay={i * 140}>
              <button
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
              </Reveal>
            ))}
            <p className="text-[10px] text-sub">
              选中地址已自动填入下方，也可手动修改；去「我的地址」管理
            </p>
          </div>
        )}
        <Reveal>
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
          <AddressSearchInput
            value={recipient.address}
            onChange={(v) => setRecipient({ ...recipient, address: v })}
            onPick={(it) => setRecipient((r) => ({ ...r, address: it.title, lat: it.lat, lng: it.lng }))}
            placeholder="收货地址（输入可搜索匹配）"
            className="maison-field"
          />
        </div>
        </Reveal>

        {/* 配送位置（地图选点，与收货地址分开） */}
        <Reveal>
        <SectionTitle title="配送位置" />
        </Reveal>
        <Reveal>
        <div className="space-y-2 rounded-card bg-white p-4 border border-line">
          <p className="text-[11px] text-sub">地图选点确定配送位置，花店按此计算配送距离（与收货地址可不同）</p>
          <button
            onClick={() => setLocPickerOpen(true)}
            className="press flex w-full items-center justify-between rounded-[2px] border border-dashed border-gold/50 bg-gold/5 px-4 py-3"
          >
            <span className={`text-[13px] ${deliveryLoc ? 'text-ink' : 'text-gold'}`}>
              {deliveryLoc
                ? `已选：${deliveryLoc.address || `${deliveryLoc.lat}, ${deliveryLoc.lng}`}`
                : '＋ 地图选点配送位置'}
            </span>
          </button>
          {deliveryLoc?.lat != null && (
            <p className="text-[10px] text-sub/70">坐标：{deliveryLoc.lat}, {deliveryLoc.lng}</p>
          )}
        </div>
        </Reveal>
        <DeliveryLocationPicker
          open={locPickerOpen}
          onConfirm={(loc) => {
            setDeliveryLoc(loc)
            setLocPickerOpen(false)
          }}
          onClose={() => setLocPickerOpen(false)}
        />

        <Reveal>
        <SectionTitle title="配送时间" />
        </Reveal>
        <Reveal>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {/* 最快配送（默认） */}
            <button
              onClick={() => setDelivery(FAST_DELIVERY)}
              className={`rounded-pill px-3 py-1.5 text-[12px] transition ${
                delivery === FAST_DELIVERY
                  ? 'bg-pink text-white'
                  : 'bg-white text-sub border border-line'
              }`}
            >
              {FAST_DELIVERY}{shopDelivery ? `（${shopDelivery}）` : ''}
            </button>
            {/* 运营配置的固定时段 */}
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
            {/* 自定义时间 */}
            <button
              onClick={() => setDelivery('custom')}
              className={`rounded-pill px-3 py-1.5 text-[12px] transition ${
                delivery === 'custom'
                  ? 'bg-pink text-white'
                  : 'bg-white text-sub border border-line'
              }`}
            >
              自定义
            </button>
          </div>
          {delivery === 'custom' && (
            <input
              value={customDelivery}
              onChange={(e) => setCustomDelivery(e.target.value)}
              placeholder="请输入配送时间，如 今晚 20:00 / 明天下午"
              className="maison-field !rounded-pill"
            />
          )}
          {deliveryOptions.length === 0 && delivery !== 'custom' && (
            <p className="px-1 text-[11px] text-sub">配送时段加载中…</p>
          )}
        </div>
        </Reveal>

        <Reveal>
        <SectionTitle title="订单备注" />
        </Reveal>
        <Reveal>
        <div className="field-shell rounded-card bg-white p-4 border border-line">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="请填写您的备注（选填）"
            className="maison-field-inline w-full"
          />
        </div>
        </Reveal>

        <Reveal>
        <div className="mt-4 space-y-2 rounded-card bg-white p-4 text-[12px] border border-line">
          <Row label="商品金额" value={`¥${Number(order.total_price).toFixed(2)}`} />
          <Row label="配送费" value={`¥${Number(shippingFee ?? 0).toFixed(2)}`} />
          <Row
            label="优惠券"
            value={`-¥${Number(order.discount || 0).toFixed(2)}`}
            valueClass="text-pink"
          />
        </div>
        </Reveal>
        <div className="h-4" />
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-line bg-bg px-5 py-4">
        <div>
          <span className="text-[13px] text-ink">合计</span>
          <span className="ml-2 text-[20px] font-medium text-ink">¥{Number(total).toFixed(2)}</span>
        </div>
        <Button style={{ width: 119 }} onClick={onPay} disabled={saving}>
          {saving ? '保存中…' : '去支付'}
        </Button>
      </div>
    </div>
  )
}
