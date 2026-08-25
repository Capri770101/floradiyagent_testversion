import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import { IconPin, IconClock, IconBack } from '../components/icons'
import { getOrder, orderAction, postReview, publicConfig, updateOrder } from '../api/shop'
import { generateEffectImage, pollImageTask } from '../api/image'
import { withApiUrl } from '../api/client'
import { planImage } from '../assets/imageMap'
import { statusMeta } from '../utils/status'
import { fmtMoney, calcPayable } from '../utils/price'
import { toast } from '../utils/toast'

// 订单详情页：展示订单全部信息（商品明细含花材数量/单价/图片、DIY 方案、
// 收货信息、金额明细、物流时间线），并保留支付/收货/评价等操作。
export default function OrderDetail() {
  const nav = useNavigate()
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [shippingFee, setShippingFee] = useState(0)
  // 贺卡编辑
  const [editingCard, setEditingCard] = useState(false)
  const [cardMsg, setCardMsg] = useState('')
  const [cardImg, setCardImg] = useState('')
  const [cardBusy, setCardBusy] = useState(false)

  useEffect(() => {
    if (!orderId) return
    getOrder(orderId)
      .then((o) => setOrder(o || null))
      .catch((e) => toast(e.message || '加载失败', 'error'))
      .finally(() => setLoading(false))
  }, [orderId])

  useEffect(() => {
    publicConfig()
      .then((cfg) => { if (cfg.shipping_fee != null) setShippingFee(cfg.shipping_fee) })
      .catch(() => {})
  }, [])

  const act = async (action) => {
    if (busy || !orderId) return
    setBusy(true)
    try {
      await orderAction(orderId, action)
      toast(action === 'complete' ? '已确认收货' : '订单已取消')
      const o = await getOrder(orderId)
      setOrder(o || null)
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  const goPay = () => nav('/pay', { state: { orderId } })

  const openAddCard = () => {
    setEditingCard(true)
    setCardMsg(order?.card_message || plan?.card_message || '')
    setCardImg(order?.card_image_url || '')
  }

  const onGenerateCard = async () => {
    if (cardBusy || !cardMsg.trim()) return
    setCardBusy(true)
    try {
      const prompt = '水彩花卉贺卡背景，柔和暖色调，粉色玫瑰与香槟色百合，花瓣散落，柔和光影，梦幻模糊背景，温馨优雅，无文字无边框无字母无符号'
      const { task_id } = await generateEffectImage(prompt)
      const data = await pollImageTask(task_id, { timeoutMs: 90000 })
      setCardImg(data.result_url)
      toast('贺卡生成成功')
    } catch (e) {
      toast('贺卡生成失败：' + e.message, 'error')
    } finally {
      setCardBusy(false)
    }
  }

  const saveCard = async () => {
    if (!cardMsg.trim()) { toast('请填写寄语', 'error'); return }
    try {
      const o = await updateOrder(orderId, {
        card_message: cardMsg.trim(),
        card_image_url: cardImg || undefined,
      })
      setOrder(o)
      setEditingCard(false)
      toast('贺卡已保存')
    } catch (e) {
      toast('保存失败：' + e.message, 'error')
    }
  }

  const meta = order ? statusMeta(order.status) : null
  const items = order?.items || []
  const plan = order?.plan
  const recipient = order?.recipient || {}
  const logistics = order?.logistics || []
  const goodsTotal = order?.total_price || 0
  const discount = order?.discount || 0
  const payable = calcPayable(goodsTotal, discount, shippingFee)

  return (
    <div className="min-h-full bg-bg pb-10">
      <div className="flex items-center gap-3 border-b border-line bg-white px-4 py-3">
        <button
          onClick={() => nav(-1)}
          aria-label="返回"
          className="press flex h-7 w-7 items-center justify-center rounded-[2px] text-ink"
        >
          <IconBack width={16} height={16} />
        </button>
        <p className="flex-1 text-center text-[15px] font-medium tracking-[1px] text-ink">订单详情</p>
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
          {/* 订单概览 */}
          <Reveal>
          <div className="mx-5 mt-4 rounded-card bg-white p-4 border border-line">
            <div className="flex items-center justify-between">
              <p className="truncate text-[11px] text-sub">{order.order_id}</p>
              <span className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                {meta.label}
              </span>
            </div>
            <p className="mt-1 text-[10px] text-sub/70">{order.created_at}</p>
            <div className="mt-2 flex items-center justify-between border-t border-line pt-2.5">
              <p className="font-serif-cn text-[16px] font-normal text-ink">
                合计 {fmtMoney(goodsTotal)}
              </p>
              <p className="text-[10px] tracking-[0.15em] text-sub">店铺：{order.shop_id || '—'}</p>
            </div>
          </div>
          </Reveal>

          {/* 商品明细：全部花材（数量/单价/图片） */}
          <Reveal delay={80}>
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">商品明细 · {items.length} 项</p>
            {items.length === 0 && (
              <p className="mt-2 text-[12px] text-sub">无商品明细</p>
            )}
            {items.map((it, i) => {
              const price = Number(it.unit_price || it.price || 0)
              const qty = Number(it.qty || 1)
              // price 语义为 line_total（含数量）时直接用；否则按 单价×数量 计算小计
              const lineTotal = Number(it.price || 0) > 0
                ? Number(it.price)
                : Math.round(price * qty * 100) / 100
              return (
                <div key={`${it.plan_id || it.name}-${i}`} className="mt-2.5 flex items-center gap-3">
                  <SmartImage
                    src={planImage(it)}
                    imgKey="home_rec_1"
                    className="h-[52px] w-[52px] shrink-0 rounded-[4px]"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] text-dark">{it.name}</p>
                    <p className="mt-0.5 text-[11px] text-sub">
                      {it.role ? `${it.role} · ` : ''}{fmtMoney(price)} × {it.qty || 1}
                      {it.shop ? ` · ${it.shop}` : ''}
                    </p>
                  </div>
                  <span className="shrink-0 text-[13px] text-ink">{fmtMoney(lineTotal)}</span>
                </div>
              )
            })}
          </div>
          </Reveal>

          {/* DIY 方案制作信息 */}
          {plan && (
            <Reveal delay={120}>
            <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
              {(plan.effect_image_url || plan.result_url || plan.effectImageUrl) && (
                <SmartImage
                  src={withApiUrl(plan.effect_image_url || plan.result_url || plan.effectImageUrl)}
                  imgKey="diy_main"
                  className="mb-3 w-full rounded-lg object-cover"
                />
              )}
              <p className="eyebrow">DIY 方案</p>
              <p className="mt-1 font-serif-cn text-[15px] font-normal text-ink">{plan.name || 'DIY 定制花束'}</p>
              {plan.requirement && <p className="mt-1 text-[11px] text-sub">需求：{plan.requirement}</p>}
              {plan.difficulty && (
                <p className="mt-1 text-[11px] text-sub">
                  难度：{plan.difficulty} · {plan.est_time || '—'} 分钟 · 保鲜 {plan.shelf_life || '—'}
                </p>
              )}
              {(() => {
                const d = plan.design || {}
                const flowers = [
                  ...(Array.isArray(d.main_flowers) ? d.main_flowers : []),
                  ...(Array.isArray(d.fillers) ? d.fillers : []),
                  ...(Array.isArray(d.foliage) ? d.foliage : []),
                ]
                return flowers.length > 0 ? (
                  <p className="mt-1 text-[11px] text-sub">
                    花材配比：
                    {flowers.map((f) => `${f.name}${f.qty ? ` ×${f.qty}` : ''}${f.ratio ? ` (${f.ratio})` : ''}`).join(' · ')}
                  </p>
                ) : null
              })()}
              {plan.packaging || plan.design?.packaging ? (
                <p className="mt-1 text-[11px] text-sub">包装：{plan.packaging || plan.design.packaging}</p>
              ) : null}
              {Array.isArray(plan.diy_steps) && plan.diy_steps.length > 0 && (
                <>
                  <p className="mt-2 text-[11px] font-medium text-ink">制作步骤</p>
                  <ol className="mt-1 list-decimal pl-4 text-[11px] leading-relaxed text-sub">
                    {plan.diy_steps.map((s, i) => <li key={i}>{s}</li>)}
                  </ol>
                </>
              )}
            </div>
            </Reveal>
          )}

          {/* 贺卡区域：所有订单都显示（不依赖 DIY plan），有贺卡展示、无贺卡显示添加按钮 */}
          <Reveal delay={140}>
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">贺卡寄语</p>
            {(order.card_image_url || order.card_message || plan?.card_message) && !editingCard ? (
              <div className="mt-2">
                <div className="card-preview relative overflow-hidden rounded-[4px]" style={{ maxHeight: 180 }}>
                  {order.card_image_url ? (
                    <img
                      src={withApiUrl(order.card_image_url)}
                      alt="贺卡"
                      className="w-full object-cover"
                      style={{ maxHeight: 180 }}
                    />
                  ) : (
                    <div className="flex h-[120px] w-full items-center justify-center bg-gradient-to-br from-[#F5E6D3] via-[#F0D4C0] to-[#E8C4B0]" />
                  )}
                  {(order.card_message || plan?.card_message) && (
                    <div className="absolute inset-0 flex items-center justify-center px-6">
                      <p
                        className="font-serif-cn text-[15px] leading-[1.8] text-white"
                        style={{ textShadow: '0 1px 8px rgba(0,0,0,0.4)' }}
                      >
                        {order.card_message || plan?.card_message}
                      </p>
                    </div>
                  )}
                </div>
                <button
                  className="mt-2 text-[11px] text-sub/70 underline"
                  onClick={openAddCard}
                >
                  编辑贺卡
                </button>
                {order.card_token && order.paid && (
                  <button
                    className="mt-2 flex items-center gap-1 rounded-[2px] bg-pink/10 px-3 py-1.5 text-[11px] text-pink"
                    onClick={() => {
                      const url = `${window.location.origin}/card-share/${order.card_token}`
                      navigator.clipboard?.writeText(url).then(
                        () => toast('链接已复制，快去分享给 TA 吧'),
                        () => toast('复制失败，请长按链接手动复制', 'error')
                      )
                    }}
                  >
                    <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5">
                      <path d="M4 12V4h8v8H4Z" stroke="currentColor" strokeWidth="1.2" />
                      <path d="M6 12V2h8v10" stroke="currentColor" strokeWidth="1.2" />
                    </svg>
                    分享贺卡
                  </button>
                )}
              </div>
            ) : editingCard ? (
              <div className="mt-2">
                <textarea
                  value={cardMsg}
                  onChange={(e) => setCardMsg(e.target.value)}
                  placeholder="写一句祝福的话…"
                  maxLength={100}
                  rows={2}
                  className="w-full resize-none rounded-[4px] border border-line bg-bg p-3 text-[12px] text-ink outline-none placeholder:text-sub/60 focus:border-pink"
                />
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-[10px] text-sub">{cardMsg.length}/100</span>
                  <Button
                    variant="subtle"
                    className="!h-[28px] !text-[11px]"
                    disabled={cardBusy || !cardMsg.trim()}
                    onClick={onGenerateCard}
                  >
                    {cardBusy ? '生成中…' : cardImg ? '重新生成' : 'AI 生成贺卡'}
                  </Button>
                </div>
                {cardBusy && (
                  <div className="mt-2 flex flex-col items-center justify-center rounded-[4px] bg-pink-2/50 py-6">
                    <div className="mb-2 h-5 w-5 animate-spin rounded-full border-2 border-pink border-t-transparent" />
                    <p className="text-[11px] text-sub">贺卡生成中…</p>
                  </div>
                )}
                {cardImg && !cardBusy && (
                  <div className="card-preview relative mt-2 overflow-hidden rounded-[4px]" style={{ maxHeight: 150 }}>
                    <img
                      src={withApiUrl(cardImg)}
                      alt="贺卡"
                      className="w-full object-cover"
                      style={{ maxHeight: 150 }}
                    />
                    {cardMsg.trim() && (
                      <div className="absolute inset-0 flex items-center justify-center px-4">
                        <p
                          className="font-serif-cn text-[14px] leading-[1.8] text-white"
                          style={{ textShadow: '0 1px 6px rgba(0,0,0,0.4)' }}
                        >
                          {cardMsg.trim()}
                        </p>
                      </div>
                    )}
                  </div>
                )}
                <div className="mt-3 flex gap-2">
                  <Button variant="secondary" className="flex-1 !h-[32px] !text-[12px]" onClick={() => setEditingCard(false)}>
                    取消
                  </Button>
                  <Button variant="primary" className="flex-1 !h-[32px] !text-[12px]" onClick={saveCard}>
                    保存贺卡
                  </Button>
                </div>
              </div>
            ) : (
              <button
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-card border border-dashed border-line bg-white py-4 text-[12px] text-sub hover:border-pink"
                onClick={openAddCard}
              >
                <svg viewBox="0 0 16 16" fill="none" className="h-4 w-4">
                  <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                </svg>
                添加贺卡寄语
              </button>
            )}
          </div>
          </Reveal>

          {/* 收货信息 */}
          <Reveal delay={160}>
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">收货信息</p>
            {recipient.name ? (
              <div className="mt-2">
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
                {order.note && <p className="mt-1 text-[11px] text-sub">备注：{order.note}</p>}
              </div>
            ) : (
              <p className="mt-2 text-[12px] text-sub">未填写收货信息</p>
            )}
          </div>
          </Reveal>

          {/* 金额明细 */}
          <Reveal delay={200}>
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">金额明细</p>
            <div className="mt-2 space-y-1.5 text-[12px]">
              <div className="flex justify-between text-sub">
                <span>商品金额</span>
                <span className="text-ink">{fmtMoney(goodsTotal)}</span>
              </div>
              <div className="flex justify-between text-sub">
                <span>配送费</span>
                <span className="text-ink">{fmtMoney(shippingFee)}</span>
              </div>
              {discount > 0 && (
                <div className="flex justify-between text-sub">
                  <span>优惠券</span>
                  <span className="text-pink">-{fmtMoney(discount)}</span>
                </div>
              )}
              <div className="flex justify-between border-t border-line pt-1.5 font-medium text-dark">
                <span>应付合计</span>
                <span>{fmtMoney(payable)}</span>
              </div>
              {order.paid_at && <p className="text-[10px] text-sub/70">支付时间：{order.paid_at}</p>}
            </div>
          </div>
          </Reveal>

          {/* 物流时间线 */}
          <Reveal delay={240}>
          <div className="mx-5 mt-3 rounded-card bg-white p-4 border border-line">
            <p className="eyebrow">物流跟踪</p>
            {logistics.length === 0 ? (
              <p className="mt-3 rounded-[2px] bg-bg p-4 text-center text-[11px] text-sub">
                暂无物流信息，商家发货后将在此展示
              </p>
            ) : (
              <div className="mt-3">
                {logistics.map((e, i) => (
                  <div key={e.seq ?? i} className="flex gap-3">
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
          </Reveal>

          {/* 订单操作 */}
          {(order.status === 'created' || order.status === 'pending_payment') && (
            <div className="mx-5 mt-4 flex gap-2">
              <Button variant="secondary" className="flex-1" disabled={busy} onClick={() => act('cancel')}>
                取消订单
              </Button>
              <Button variant="secondary" className="flex-1" onClick={goPay}>
                去支付
              </Button>
            </div>
          )}
          {order.status === 'shipped' && (
            <div className="mx-5 mt-4">
              <Button variant="secondary" className="w-full" disabled={busy} onClick={() => act('complete')}>
                确认收货
              </Button>
            </div>
          )}
          {order.status === 'done' && (
            <div className="mx-5 mt-4">
              <Button variant="secondary" className="w-full" onClick={() => nav('/orders')}>
                再来一单
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}