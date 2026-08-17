import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { IconBack, IconPin, IconClock } from '../components/icons'
import { getOrder } from '../api/shop'
import { planImage } from '../assets/imageMap'
import SmartImage from '../components/SmartImage'
import { toast } from '../utils/toast'

const STATUS_META = {
  created: { label: '待付款', cls: 'bg-pink/10 text-pink' },
  pending_payment: { label: '待付款', cls: 'bg-pink/10 text-pink' },
  paid: { label: '待发货', cls: 'bg-pink/10 text-pink' },
  shipped: { label: '配送中', cls: 'bg-pink/10 text-pink' },
  done: { label: '已完成', cls: 'bg-pink/10 text-pink' },
  canceled: { label: '已取消', cls: 'bg-line/40 text-sub' },
}

const fmtMoney = (v) => `¥${Number(v || 0).toFixed(2)}`

// 物流跟踪页：订单概要 + 时间线，商家/用户共用数据源
export default function Logistics() {
  const nav = useNavigate()
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getOrder(orderId)
      .then((r) => setOrder(r.order || null))
      .catch((e) => toast(e.message || '加载失败', 'error'))
      .finally(() => setLoading(false))
  }, [orderId])

  const meta = order ? STATUS_META[order.status] || { label: order.status, cls: 'bg-line/40 text-sub' } : null
  const items = order?.items || []
  const recipient = order?.recipient || {}
  const logistics = order?.logistics || []

  return (
    <div className="min-h-full bg-bg pb-8">
      <div className="flex items-center gap-3 border-b border-line bg-white px-4 py-3">
        <button
          onClick={() => nav(-1)}
          aria-label="返回"
          className="press flex h-7 w-7 items-center justify-center rounded-[2px] text-ink"
        >
          <IconBack width={16} height={16} />
        </button>
        <p className="flex-1 text-center text-[15px] font-medium tracking-[1px] text-ink">物流跟踪</p>
        <span className="w-7" />
      </div>

      {loading ? (
        <p className="mx-5 mt-6 rounded-card bg-white p-8 text-center text-[12px] text-sub border border-line">
          加载中…
        </p>
      ) : !order ? (
        <p className="mx-5 mt-6 rounded-card bg-white p-8 text-center text-[12px] text-sub border border-line">
          订单不存在
        </p>
      ) : (
        <>
          {/* 订单概要 */}
          <div className="mx-5 mt-4 rounded-card bg-white p-4 border border-line">
            <div className="flex items-center justify-between">
              <p className="truncate text-[11px] text-sub">{order.order_id}</p>
              <span className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                {meta.label}
              </span>
            </div>
            <p className="mt-1 text-[10px] text-sub/70">{order.created_at}</p>
            <div className="mt-2 flex items-center justify-between border-t border-line pt-2.5">
              <p className="font-serif-cn text-[15px] font-normal text-ink">共 {fmtMoney(order.total_price)}</p>
              <p className="text-[10px] tracking-[0.15em] text-sub">店铺：{order.shop_id || '—'}</p>
            </div>
          </div>

          {/* 商品明细 */}
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">商品明细</p>
            {items.map((it) => (
              <div key={it.plan_id} className="mt-2.5 flex items-center gap-3">
                <SmartImage
                  src={planImage(it)}
                  imgKey="home_rec_1"
                  className="h-[44px] w-[44px] shrink-0 rounded-[4px]"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-dark">{it.name}</p>
                  <p className="text-[11px] text-sub">
                    {fmtMoney(it.price)} × {it.qty}
                    {it.shop ? ` · ${it.shop}` : ''}
                  </p>
                </div>
              </div>
            ))}
            {recipient.name && (
              <div className="mt-3 border-t border-line pt-3">
                <p className="text-[12px] text-ink">
                  {recipient.name}
                  {recipient.phone ? <span className="ml-2 text-[11px] text-sub">{recipient.phone}</span> : null}
                </p>
                {recipient.address && (
                  <p className="mt-1 flex items-start gap-1 text-[11px] leading-relaxed text-sub">
                    <IconPin width={12} height={12} className="mt-0.5 shrink-0" />
                    {recipient.address}
                  </p>
                )}
                {order.delivery_time && (
                  <p className="mt-1 flex items-center gap-1 text-[10px] text-sub/80">
                    <IconClock width={11} height={11} />
                    预约 {order.delivery_time}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* 物流时间线 */}
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">物流跟踪</p>
            {logistics.length === 0 ? (
              <p className="mt-3 rounded-[2px] bg-bg p-4 text-center text-[11px] text-sub">
                暂无物流信息，商家发货后将在此展示
              </p>
            ) : (
              <div className="mt-3">
                {logistics.map((e, i) => (
                  <div key={e.seq} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className={`mt-1 h-2 w-2 rounded-full ${i === 0 ? 'bg-pink' : 'bg-line'}`} />
                      {i < logistics.length - 1 && <span className="w-px flex-1 bg-line" />}
                    </div>
                    <div className="pb-3">
                      <p className={`text-[12px] ${i === 0 ? 'font-medium text-dark' : 'text-sub'}`}>{e.text}</p>
                      <p className="text-[10px] text-sub/70">{e.created_at}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}