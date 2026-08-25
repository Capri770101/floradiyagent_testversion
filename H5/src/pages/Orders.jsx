import React, { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import SmartImage from '../components/SmartImage'
import { Button } from '../components/Button'
import Reveal from '../components/Reveal'
import { IconStar } from '../components/icons'
import { planImage } from '../assets/imageMap'
import { listOrders, orderAction, orderAftersale, postReview } from '../api/shop'
import { toast } from '../utils/toast'
import { statusMeta } from '../utils/status'
import { fmtMoney } from '../utils/price'

// 状态筛选 tab（键与后端 order.status 对齐）
const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'created', label: '待付款' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '配送中' },
  { key: 'done', label: '已完成' },
  { key: 'canceled', label: '已取消' },
]

// 我的订单：状态筛选 + 订单卡片列表；点击进入物流追踪（含订单概要 + 时间线）
export default function Orders() {
  const nav = useNavigate()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('all')
  const [kw, setKw] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [asTarget, setAsTarget] = useState(null) // 申请售后的订单
  const [asType, setAsType] = useState('refund')
  const [asReason, setAsReason] = useState('')
  const [asBusy, setAsBusy] = useState(false)
  const [reviewTarget, setReviewTarget] = useState(null) // 待评价订单
  const [reviewRating, setReviewRating] = useState(5)
  const [reviewContent, setReviewContent] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)

  const loadOrders = () => {
    listOrders()
      .then(setOrders)
      .catch((e) => toast(e.message || '订单加载失败', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(loadOrders, [])

  // 订单操作：取消 / 模拟发货 / 确认收货
  const act = async (oid, action) => {
    if (busyId) return
    setBusyId(oid)
    try {
      await orderAction(oid, action)
      toast(action === 'ship' ? '已模拟发货' : action === 'complete' ? '已确认收货' : '订单已取消')
      loadOrders()
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const goPay = (oid) => nav('/pay', { state: { orderId: oid } })

  const openReview = (o) => {
    setReviewTarget(o)
    setReviewRating(5)
    setReviewContent('')
  }

  const submitReview = async () => {
    if (reviewBusy || !reviewTarget) return
    setReviewBusy(true)
    try {
      await postReview({
        order_id: reviewTarget.order_id,
        rating: reviewRating,
        content: reviewContent.trim(),
      })
      toast('评价成功，感谢你的反馈')
      setReviewTarget(null)
      loadOrders()
    } catch (e) {
      toast(e.message || '评价失败', 'error')
    } finally {
      setReviewBusy(false)
    }
  }

  const filtered = useMemo(() => {
    const q = kw.trim().toLowerCase()
    let list = tab === 'all' ? orders : orders.filter((o) => o.status === tab)
    if (q) {
      list = list.filter((o) => {
        const items = (o.items || []).map((it) => `${it.name} ${it.plan_id} ${it.shop || ''}`).join(' ')
        return `${o.order_id} ${o.status} ${items}`.toLowerCase().includes(q)
      })
    }
    return list
  }, [orders, tab, kw])

  // 售后：已支付且未取消的订单可发起
  const canAftersale = (o) => o.paid && o.status !== 'canceled'

  const submitAftersale = async (e) => {
    e.preventDefault()
    if (asBusy || !asTarget) return
    if (!asReason.trim()) {
      toast('请填写售后原因', 'error')
      return
    }
    setAsBusy(true)
    try {
      await orderAftersale(asTarget.order_id, { type: asType, reason: asReason.trim() })
      toast('售后申请已提交，等待平台审核')
      setAsTarget(null)
      setAsReason('')
      setAsType('refund')
    } catch (err) {
      toast(err.message || '提交失败', 'error')
    } finally {
      setAsBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="我的订单" />
      {/* 状态筛选 tab：横向滚动，避免窄屏换行 */}
      <div className="flex shrink-0 gap-2 overflow-x-auto px-4 py-3">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
            className={`press shrink-0 rounded-pill px-3.5 py-1.5 text-[12px] tracking-[1px] ${
              tab === t.key ? 'bg-ink text-[#FAF8F5]' : 'bg-white text-sub border border-line'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="shrink-0 px-4 pb-3">
        <input
          value={kw}
          onChange={(e) => setKw(e.target.value)}
          placeholder="搜索订单号 / 商品名称"
          className="maison-field w-full !rounded-pill !px-4"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-6">
        {loading ? (
          <p className="mt-6 rounded-card bg-white p-8 text-center text-[12px] text-sub border border-line">
            加载中…
          </p>
        ) : filtered.length === 0 ? (
          <Reveal>
          <div className="py-16 text-center">
            <p className="font-serif-cn text-[18px] font-normal text-ink">
              {kw.trim()
                ? '没有匹配的订单'
                : tab === 'all'
                  ? '还没有订单'
                  : '该状态下暂无订单'}
            </p>
            <p className="mt-2 text-[11px] text-sub">去首页挑一束心仪的花吧</p>
            <Button
              variant="subtle"
              className="mt-5"
              onClick={() => nav('/')}
            >
              去逛逛
            </Button>
          </div>
          </Reveal>
        ) : (
          <div className="space-y-3">
            {filtered.map((o, i) => {
              const meta = statusMeta(o.status)
              const items = o.items || []
              const total = o.total_price != null
                ? o.total_price
                : Math.round(items.reduce((s, it) => s + (it.price || 0) * (it.qty || 1), 0) * 100) / 100
              const count = items.reduce((s, it) => s + (it.qty || 1), 0)
              return (
                <Reveal key={o.order_id} delay={i * 140}>
                <div
                  className="block w-full overflow-hidden rounded-card bg-white border border-line text-left"
                >
                  <button
                    type="button"
                    onClick={() => nav(`/orders/${o.order_id}`)}
                    className="block w-full text-left"
                  >
                    <div className="flex items-center justify-between border-b border-line px-4 py-3">
                      <span className="text-[11px] text-sub">{o.order_id}</span>
                      <span className={`rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                        {meta.label}
                      </span>
                    </div>
                    {items.map((it, idx) => (
                      <div key={`${it.plan_id || it.name}-${idx}`} className="flex items-center gap-3 px-4 py-2.5">
                        <SmartImage
                          src={planImage(it)}
                          imgKey="home_rec_1"
                          className="h-[44px] w-[44px] shrink-0 rounded-[4px]"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] text-dark">{it.name}</p>
                          <p className="text-[11px] text-sub">
                            ¥{Number(it.unit_price || it.price || 0).toFixed(2)} × {it.qty}
                            {it.shop ? ` · ${it.shop}` : ''}
                          </p>
                        </div>
                      </div>
                    ))}
                    <div className="flex items-center justify-between border-t border-line px-4 py-3">
                      <span className="text-[11px] text-sub">共 {count} 件</span>
                      <span className="font-serif-cn text-[15px] font-normal text-ink">
                        合计 {fmtMoney(total)}
                      </span>
                    </div>
                  </button>
                  <div className="flex gap-2 border-t border-line px-4 py-3">
                      {canAftersale(o) && (
                        <Button
                          variant="secondary"
                          className="flex-1 !h-[34px] !text-[12px]"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAsTarget(o)
                            setAsReason('')
                            setAsType('refund')
                          }}
                        >
                          申请售后
                        </Button>
                      )}
                      {(o.status === 'created' || o.status === 'pending_payment') && (
                        <>
                          <Button
                            variant="secondary"
                            className="flex-1 !h-[34px] !text-[12px]"
                            disabled={busyId === o.order_id}
                            onClick={() => act(o.order_id, 'cancel')}
                          >
                            取消订单
                          </Button>
                          <Button
                            variant="secondary"
                            className="flex-1 !h-[34px] !text-[12px]"
                            disabled={busyId === o.order_id}
                            onClick={() => goPay(o.order_id)}
                          >
                            去支付
                          </Button>
                        </>
                      )}
                      {o.status === 'paid' && (
                        <Button
                          variant="secondary"
                          className="flex-1 !h-[34px] !text-[12px]"
                          disabled={busyId === o.order_id}
                          onClick={() => act(o.order_id, 'ship')}
                        >
                          模拟发货
                        </Button>
                      )}
                      {o.status === 'shipped' && (
                        <Button
                          variant="secondary"
                          className="flex-1 !h-[34px] !text-[12px]"
                          disabled={busyId === o.order_id}
                          onClick={() => act(o.order_id, 'complete')}
                        >
                          确认收货
                        </Button>
                      )}
                      {o.status === 'done' && (
                        <Button
                          variant="secondary"
                          className="flex-1 !h-[34px] !text-[12px]"
                          onClick={() => openReview(o)}
                        >
                          评价
                        </Button>
                      )}
                  </div>
                  <div className="flex border-t border-line">
                    {o.shop_id && (
                      <button
                        type="button"
                        onClick={() => nav(`/chat/${encodeURIComponent(o.shop_id)}`)}
                        className="press flex-1 border-r border-line bg-bg/50 py-2.5 text-center text-[11px] tracking-[1px] text-sub"
                      >
                        联系商家
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => nav(`/logistics/${o.order_id}`)}
                      className="press flex-1 bg-bg/50 py-2.5 text-center text-[11px] tracking-[1px] text-sub"
                    >
                      查看物流跟踪
                    </button>
                  </div>
                </div>
                </Reveal>
              )
            })}
          </div>
        )}
      </div>

      {/* 评价弹窗 */}
      {reviewTarget && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setReviewTarget(null)}
        >
          <div
            className="w-full max-w-[430px] rounded-t-[20px] bg-white p-5 pb-7"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-center text-[16px] font-medium text-dark">评价订单</h3>
            <p className="mt-1 text-center text-[11px] text-sub">
              订单 {reviewTarget.order_id} · 已完成，欢迎分享你的体验
            </p>
            <div className="mt-4 flex justify-center gap-2">
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  aria-label={`${s} 星`}
                  onClick={() => setReviewRating(s)}
                  className="p-1"
                >
                  <IconStar
                    width={26}
                    height={26}
                    filled={s <= reviewRating}
                    className={s <= reviewRating ? 'text-pink' : 'text-line'}
                  />
                </button>
              ))}
            </div>
            <textarea
              value={reviewContent}
              onChange={(e) => setReviewContent(e.target.value)}
              placeholder="说说这束花的体验吧（选填）"
              maxLength={500}
              rows={3}
              className="mt-4 w-full resize-none rounded-[4px] border border-line bg-bg p-3 text-[12px] text-ink outline-none placeholder:text-sub/60 focus:border-pink"
            />
            <Button className="mt-4 w-full" onClick={submitReview} disabled={reviewBusy}>
              {reviewBusy ? '提交中…' : '提交评价'}
            </Button>
          </div>
        </div>
      )}

      {/* 申请售后弹层 */}
      {asTarget && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setAsTarget(null)}
        >
          <form
            onSubmit={submitAftersale}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-h5 rounded-t-[20px] bg-white px-5 pb-8 pt-5"
          >
            <div className="mx-auto mb-4 h-[2px] w-9 bg-gold" />
            <h3 className="font-serif-cn text-[19px] font-normal text-ink">申请售后</h3>
            <p className="mt-1 text-[11px] text-sub">
              订单 {asTarget.order_id} · 合计 {fmtMoney(asTarget.total_price)}
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-[11px] text-sub">售后类型</label>
                <div className="flex gap-2">
                  {[
                    { v: 'refund', l: '退款' },
                    { v: 'return', l: '退货' },
                    { v: 'exchange', l: '换货' },
                  ].map((t) => (
                    <button
                      key={t.v}
                      type="button"
                      onClick={() => setAsType(t.v)}
                      className={`press flex-1 rounded-pill border py-2.5 text-[12px] tracking-[1px] ${
                        asType === t.v ? 'border-gold bg-gold/10 text-gold' : 'border-line bg-white text-sub'
                      }`}
                    >
                      {t.l}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-sub">原因 *</label>
                <textarea
                  value={asReason}
                  onChange={(e) => setAsReason(e.target.value)}
                  maxLength={200}
                  rows={3}
                  placeholder="请描述售后原因"
                  className="maison-field w-full resize-none"
                />
              </div>
              <Button
                className="mt-2 w-full"
                disabled={asBusy}
                onClick={submitAftersale}
              >
                {asBusy ? '提交中…' : '提交申请'}
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
