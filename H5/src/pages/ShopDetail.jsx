import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { IconStar, IconCart, IconArrow, IconClock, IconPin } from '../components/icons'
import { getShop, getCart, addCart, updateCart, removeCart } from '../api/shop'
import { recommendShops } from '../api/recommend'
import { useRecommend } from '../hooks/useRecommend'
import { getUserId } from '../api/chat'
import { getLocation } from '../utils/location'
import { toast } from '../utils/toast'
import { PLACEHOLDER } from '../tokens'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import ReportDialog from '../components/ReportDialog'
import { planImage, shopImage } from '../assets/imageMap'

// 美团外卖式店铺详情页：
// 顶部店铺信息（评分/月售/起送/配送费/配送时长/距离/公告/营业时间/地址）
// + 左栏分类导航（滚动联动高亮）+ 右栏商品列表（加购步进器）
// + 底部悬浮购物车条（合计/去结算）。

function ShopHeader({ shop, noticeOpen, onToggleNotice, onChat }) {
  return (
    <div className="shrink-0">
      {/* 封面（真实店铺图，文件未就位时回退砂色块） */}
      <SmartImage
        src={shopImage(shop)}
        color={PLACEHOLDER.shopCover}
        className="h-[150px] w-full"
      />
      {/* 店铺信息卡 */}
      <div className="bg-white px-4 pb-3 pt-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {shop.logo && (
                <img
                  src={shop.logo}
                  alt="店铺 Logo"
                  className="h-[26px] w-[26px] shrink-0 rounded-full border border-line object-cover"
                />
              )}
              <h1 className="truncate font-serif-cn text-[20px] font-normal text-ink">{shop.name}</h1>
            </div>
            <p className="mt-1 flex items-center gap-1 text-[11px] text-ink">
              <IconStar width={11} height={11} className="text-cream" filled />
              <span className="font-medium text-dark">{shop.rating}</span>
              <span className="text-sub">月售 {shop.sales}</span>
              <span className="text-sub">·</span>
              <span className="text-sub">{shop.distance_km != null && shop.distance_km !== '' ? `${shop.distance_km}km` : ''}</span>
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${
              shop.status === '营业中' ? 'bg-green/20 text-[#5b8a6a]' : 'bg-line text-sub'
            }`}
          >
            {shop.status}
          </span>
        </div>
        {/* 起送 / 配送费 / 配送时长 */}
        <div className="mt-2.5 flex items-center gap-2 text-[11px] text-sub">
          <span className="rounded bg-bg px-1.5 py-0.5">起送 ¥{shop.min_delivery}</span>
          <span className="rounded bg-bg px-1.5 py-0.5">配送 ¥{shop.delivery_fee}</span>
          <span className="rounded bg-bg px-1.5 py-0.5">{shop.delivery_time}</span>
        </div>
        {/* 公告（可展开） */}
        <button
          onClick={onToggleNotice}
          className="mt-2 flex w-full items-center gap-1 text-left text-[11px] text-sub"
        >
          <span className="shrink-0 rounded bg-pink-2 px-1 text-[10px] text-pink">公告</span>
          <span className="truncate">{shop.notice}</span>
          <IconArrow
            width={10}
            height={10}
            className={`shrink-0 transition-transform ${noticeOpen ? 'rotate-180' : 'rotate-90'}`}
          />
        </button>
        {noticeOpen && (
          <p className="mt-1.5 rounded bg-bg px-2 py-2 text-[11px] leading-relaxed text-sub">
            {shop.notice ? (
              <p>{shop.notice}</p>
            ) : (
              <p className="text-sub/70">商家暂未发布店铺公告</p>
            )}
            <p className="mt-1.5 text-sub/80">本店花材每日现采，支持同城速递，如需指定送达时间请在下单时备注。</p>
          </p>
        )}
        {/* 营业时间 / 地址 */}
        <div className="mt-2 flex items-center gap-3 border-t border-line pt-2 text-[11px] text-sub">
          <span className="flex items-center gap-1">
            <IconClock width={12} height={12} className="text-gold" />
            {shop.hours}
          </span>
          <span className="flex min-w-0 items-center gap-1 truncate">
            <IconPin width={12} height={12} className="shrink-0 text-gold" />
            <span className="truncate">{shop.address}</span>
          </span>
        </div>
        {/* 联系商家：进入顾客-商家会话（契约 4.1） */}
        {onChat && (
          <button
            onClick={onChat}
            className="press mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-[2px] border border-gold/50 bg-gold/5 py-2 text-[12px] tracking-[1px] text-gold"
          >
            联系商家
            <IconArrow width={11} height={11} className="rotate-90" />
          </button>
        )}
      </div>
    </div>
  )
}

function ProductRow({ item, qty, onAdd, onDec, onInc }) {
  return (
    <div className="flex gap-3 py-4">
      <SmartImage
        src={planImage(item)}
        color={imgColor(item.id)}
        className="h-[76px] w-[76px] shrink-0 rounded-[2px]"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-serif-cn text-[17px] font-normal text-ink">{item.name}</p>
        <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-sub">{item.desc}</p>
        {(item.tags?.length > 0 || item.style) && (
          <p className="mt-1 flex flex-wrap gap-1">
            {item.style && (
              <span className="rounded-[2px] bg-sand px-1.5 py-px text-[9px] text-gold-dark">{item.style}</span>
            )}
            {(item.tags || []).slice(0, 2).map((t) => (
              <span key={t} className="rounded-[2px] bg-bg px-1.5 py-px text-[9px] text-stone">
                {t}
              </span>
            ))}
          </p>
        )}
        <div className="mt-2 flex items-end justify-between">
          <div>
            <p className="text-[10px] text-stone">月售 {item.sales}</p>
            <p className="text-[15px] text-ink">
              <span className="mr-0.5 text-[10px] text-stone">¥</span>
              {item.price}
            </p>
          </div>
          {qty > 0 ? (
            <div className="flex items-center gap-2.5">
              <button
                onClick={onDec}
                aria-label="减少"
                className="flex h-[24px] w-[24px] items-center justify-center rounded-[2px] border border-line text-[14px] text-ink"
              >
                −
              </button>
              <span className="min-w-[14px] text-center text-[13px] text-ink">{qty}</span>
              <button
                onClick={onInc}
                aria-label="增加"
                className="flex h-[24px] w-[24px] items-center justify-center rounded-[2px] bg-gold text-[14px] text-[#FAF8F5]"
              >
                ＋
              </button>
            </div>
          ) : (
            <button
              onClick={onAdd}
              className="rounded-[2px] bg-sand px-4 py-2 text-[11px] font-medium tracking-[1px] text-gold-dark"
            >
              加入
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ShopDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [shop, setShop] = useState(null)
  const [cart, setCart] = useState({}) // plan_id -> { item_id, qty }
  const [loading, setLoading] = useState(true)
  const [activeCat, setActiveCat] = useState(0)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const listRef = useRef(null)
  const sectionRefs = useRef({})

  // 附近同类店铺（模块三）：排除本店 + 同价位带加权 + 定位距离
  const { items: recShops, state: recState } = useRecommend(
    () => {
      const loc = getLocation()
      return recommendShops({ lat: loc?.lat, lng: loc?.lng, limit: 4, shopId: id })
    },
    { deps: [id] },
  )

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const [s, items] = await Promise.all([getShop(id), getCart(getUserId())])
        if (!alive) return
        setShop(s)
        const m = {}
        ;(items || []).forEach((it) => {
          m[it.plan_id] = { item_id: it.item_id, qty: it.qty }
        })
        setCart(m)
      } catch (e) {
        console.error('店铺加载失败', e)
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    return () => {
      alive = false
    }
  }, [id])

  const planIds = useMemo(() => {
    const s = new Set()
    ;(shop?.menu || []).forEach((c) => (c.items || []).forEach((it) => s.add(it.id)))
    return s
  }, [shop])

  // 本店购物车：件数 / 合计
  const { count, total } = useMemo(() => {
    let c = 0
    let t = 0
    Object.entries(cart).forEach(([pid, v]) => {
      if (planIds.has(pid)) {
        c += v.qty
        const item = (shop?.menu || [])
          .flatMap((cat) => cat.items || [])
          .find((it) => it.id === pid)
        if (item) t += item.price * v.qty
      }
    })
    return { count: c, total: t }
  }, [cart, planIds, shop])

  const setQty = (pid, entry) => {
    setCart((prev) => {
      const next = { ...prev }
      if (entry.qty <= 0) delete next[pid]
      else next[pid] = entry
      return next
    })
  }

  const onAdd = async (item) => {
    try {
      const created = await addCart(getUserId(), {
        plan_id: item.id,
        name: item.name,
        price: item.price,
        shop: shop?.name || '',
      })
      setQty(item.id, { item_id: created.item_id, qty: created.qty })
    } catch (e) {
      toast('加入购物车失败：' + e.message, 'error')
    }
  }

  const onInc = async (item) => {
    const cur = cart[item.id]
    if (!cur) return onAdd(item)
    try {
      const updated = await updateCart(cur.item_id, { qty: cur.qty + 1 })
      setQty(item.id, { item_id: updated.item_id, qty: updated.qty })
    } catch (e) {
      toast('操作失败：' + e.message, 'error')
    }
  }

  const onDec = async (item) => {
    const cur = cart[item.id]
    if (!cur) return
    try {
      if (cur.qty <= 1) {
        await removeCart(cur.item_id)
        setQty(item.id, { item_id: cur.item_id, qty: 0 })
      } else {
        const updated = await updateCart(cur.item_id, { qty: cur.qty - 1 })
        setQty(item.id, { item_id: updated.item_id, qty: updated.qty })
      }
    } catch (e) {
      toast('操作失败：' + e.message, 'error')
    }
  }

  // 右栏滚动 → 左栏分类高亮
  const onScroll = () => {
    const box = listRef.current
    if (!box) return
    const top = box.getBoundingClientRect().top + 8
    let active = 0
    ;(shop?.menu || []).forEach((c, i) => {
      const el = sectionRefs.current[i]
      if (el && el.getBoundingClientRect().top <= top) active = i
    })
    setActiveCat(active)
  }

  const jumpTo = (i) => {
    sectionRefs.current[i]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setActiveCat(i)
  }

  if (loading || !shop) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="店铺" />
        <div className="flex-1 p-5">
          <div className="h-[132px] animate-pulse rounded-[4px] bg-line" />
          <div className="mt-3 h-[120px] animate-pulse rounded-[4px] bg-line" />
        </div>
      </div>
    )
  }

  const menu = shop.menu || []

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar
        title={shop.name}
        right={
          <button
            className="text-[11px] tracking-[1px] text-sub"
            aria-label="举报"
            onClick={() => setReportOpen(true)}
          >
            举报
          </button>
        }
      />
      <ReportDialog
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        targetType="shop"
        targetId={id}
        targetTitle={`店铺「${shop.name}」`}
      />
      {/* 店铺信息 */}
      <Reveal>
        <ShopHeader
          shop={shop}
          noticeOpen={noticeOpen}
          onToggleNotice={() => setNoticeOpen(!noticeOpen)}
          onChat={() => nav(`/chat/${encodeURIComponent(id)}`)}
        />
      </Reveal>

      {/* 左栏分类 + 右栏商品 */}
      <div className="flex min-h-0 flex-1">
        <aside className="w-[86px] shrink-0 overflow-y-auto bg-[#F3EFE9]">
          {menu.map((c, i) => (
            <button
              key={c.id}
              onClick={() => jumpTo(i)}
              className={`flex w-full flex-col items-center py-3.5 text-[12px] leading-tight ${
                activeCat === i
                  ? 'bg-bg font-medium text-pink'
                  : 'text-sub'
              }`}
              style={
                activeCat === i
                  ? { boxShadow: 'inset 2px 0 0 #B5985A' }
                  : undefined
              }
            >
              {c.name}
              {activeCat === i && <span className="mt-1 h-[3px] w-3 rounded bg-pink" />}
            </button>
          ))}
        </aside>

        <div ref={listRef} onScroll={onScroll} className="min-w-0 flex-1 overflow-y-auto px-4">
          {menu.length === 0 && (
            <p className="py-16 text-center text-[12px] text-sub">本店暂无上架商品</p>
          )}
          {menu.map((c, i) => (
            <section key={c.id} ref={(el) => (sectionRefs.current[i] = el)}>
              <h3 className="sticky top-0 z-10 -mx-4 bg-bg/95 px-4 pb-1 pt-3 font-serif-cn text-[17px] font-normal text-ink backdrop-blur">
                {c.name}
              </h3>
              <div className="divide-y divide-line">
                {(c.items || []).map((it) => (
                  <ProductRow
                    key={it.id}
                    item={it}
                    qty={cart[it.id]?.qty || 0}
                    onAdd={() => onAdd(it)}
                    onInc={() => onInc(it)}
                    onDec={() => onDec(it)}
                  />
                ))}
              </div>
            </section>
          ))}
          <div className="h-4" />

          {/* 附近同类店铺（模块三：数据来自 /recommend/shops，排除本店） */}
          <div className="-mx-4 border-t border-line bg-bg px-4 pb-4 pt-4">
            <Reveal>
              <h3 className="font-serif-cn text-[17px] font-normal text-ink">附近同类店铺</h3>
            </Reveal>
            <Reveal delay={80}>
              <p className="mt-0.5 text-[10px] text-sub">按偏好、热度与距离综合推荐</p>
            </Reveal>
            <div className="mt-3 space-y-2">
              {recState === 'loading' &&
                Array.from({ length: 2 }).map((_, i) => (
                  <div key={i} className="h-[58px] animate-pulse rounded-[4px] bg-line" />
                ))}
              {recState === 'error' && (
                <p className="py-4 text-center text-[11px] text-sub">推荐加载失败，请稍后重试</p>
              )}
              {recState === 'empty' && (
                <p className="py-4 text-center text-[11px] text-sub">暂无同类店铺推荐</p>
              )}
              {recState === 'ok' &&
                recShops.map((s, i) => (
                  <Reveal key={s.id} delay={160 + i * 140}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => nav(`/shop/${s.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          nav(`/shop/${s.id}`)
                        }
                      }}
                      className="press flex cursor-pointer items-center gap-3 rounded-[4px] border border-line bg-white p-3"
                    >
                      <SmartImage
                        src={shopImage(s)}
                        color={imgColor(s.id)}
                        className="h-[52px] w-[52px] shrink-0 rounded-[2px]"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-serif-cn text-[15px] font-normal text-ink">{s.name}</p>
                        <p className="mt-0.5 flex items-center gap-1 text-[10px] text-sub">
                          <IconStar width={10} height={10} className="text-cream" /> {s.rating} ·{' '}
                          {s.eta} · 起送 ¥{s.min_delivery}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-sub">{s.dist}</span>
                    </div>
                  </Reveal>
                ))}
            </div>
          </div>
        </div>
      </div>

      {/* 底部吸底结算栏（Maison：墨黑底 + 香槟金 CTA） */}
      <div className="shrink-0 bg-white px-4 pb-3 pt-2">
        <div className="flex items-center justify-between rounded-[2px] bg-dark py-2 pl-3 pr-1.5">
          <div className="flex items-center gap-2">
            <div className="relative">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gold text-white">
                <IconCart width={19} height={19} />
              </span>
              {count > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-cream px-1 text-[10px] font-medium text-white">
                  {count}
                </span>
              )}
            </div>
            <div>
              <p className="text-[13px] font-medium text-white">
                {total > 0 ? (
                  <>
                    <span className="text-[11px]">¥</span>
                    {total}
                  </>
                ) : (
                  <span className="text-white/70">未选购商品</span>
                )}
              </p>
              {total > 0 && (
                <p className="text-[10px] text-white/60">另需配送费 ¥{shop.delivery_fee}</p>
              )}
            </div>
          </div>
          <button
            onClick={() => nav('/cart')}
            disabled={count === 0}
            className={`flex h-9 items-center rounded-[2px] px-5 text-[13px] font-medium tracking-wide ${
              count > 0 ? 'bg-gold text-[#FAF8F5]' : 'bg-line text-sub'
            }`}
          >
            去结算
          </button>
        </div>
      </div>
    </div>
  )
}
