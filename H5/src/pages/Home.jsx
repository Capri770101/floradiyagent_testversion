import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconArrow, IconStar, IconPin, IconMenu } from '../components/icons'
import LocationPicker from '../components/LocationPicker'
import ProductCard from '../components/ProductCard'
import MaisonBloom from '../components/MaisonBloom'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import Carousel from '../components/Carousel'
import { listShops, getCart, addCart, favoriteStatus, addFavorite, removeFavorite } from '../api/shop'
import { recommendPlans, recommendSignature } from '../api/recommend'
import { getUserId } from '../api/chat'
import { isLoggedIn, getProfile } from '../api/auth'
import { useRecommend } from '../hooks/useRecommend'
import { toast } from '../utils/toast'
import { getLocation, setLocation } from '../utils/location'
import { imgColor } from '../utils/color'
import { shopImage } from '../assets/imageMap'

export default function Home() {
  const nav = useNavigate()
  const [shops, setShops] = useState([])
  const [cart, setCart] = useState({})
  const [loc, setLoc] = useState(getLocation)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [favs, setFavs] = useState({})

  // 购物车与定位无关 → 只在挂载时加载一次；定位变更只重拉店铺/精选
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const items = await getCart(getUserId())
        if (!alive) return
        const m = {}
        ;(items || []).forEach((it) => {
          m[it.item_id] = { name: it.name, price: it.price, qty: it.qty }
        })
        setCart(m)
      } catch (e) {
        if (alive) console.error('购物车加载失败', e)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const ss = await listShops(loc)
        if (!alive) return
        setShops(ss)
      } catch (e) {
        if (alive) console.error('首页加载失败', e)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [loc])

  // 猜你喜欢（模块三）：定位 + 偏好 + 热度融合推荐，数据全部来自 /recommend/plans
  const {
    items: recPlans,
    state: recState,
    reload: reloadRec,
  } = useRecommend(
    () => recommendPlans({ lat: loc?.lat, lng: loc?.lng, limit: 6 }),
    { deps: [loc] },
  )

  // 当季臻选：策展式推荐（角标气质 + 热度 + 距离），/recommend/signature
  const { items: sigPlans, state: sigState } = useRecommend(
    () => recommendSignature({ lat: loc?.lat, lng: loc?.lng, limit: 3 }),
    { deps: [loc] },
  )

  // 收藏状态（业务闭环：推荐卡上的收藏动线 → 偏好信号自增长）
  useEffect(() => {
    if (!isLoggedIn() || recState !== 'ok') {
      setFavs({})
      return
    }
    let alive = true
    ;(async () => {
      const m = {}
      for (const p of recPlans) {
        try {
          m[p.id] = await favoriteStatus(p.id)
        } catch {
          m[p.id] = false
        }
        if (!alive) return
      }
      setFavs(m)
    })()
    return () => {
      alive = false
    }
  }, [recState, recPlans])

  const onToggleFav = async (p) => {
    if (!isLoggedIn()) {
      toast('登录后才能收藏')
      nav('/profile', { state: { from: '/' } })
      return
    }
    const next = !favs[p.id]
    setFavs((prev) => ({ ...prev, [p.id]: next }))
    try {
      if (next) await addFavorite(p.id)
      else await removeFavorite(p.id)
      toast(next ? '已收藏，推荐会更懂你' : '已取消收藏')
      reloadRec() // 偏好信号变化 → 即时刷新推荐
    } catch (e) {
      setFavs((prev) => ({ ...prev, [p.id]: !next }))
      toast(e.message || '操作失败', 'error')
    }
  }

  const cartCount = useMemo(() => Object.values(cart).reduce((s, it) => s + it.qty, 0), [cart])
  const cartTotal = useMemo(
    () => Math.round(Object.values(cart).reduce((s, it) => s + it.price * it.qty, 0) * 100) / 100,
    [cart],
  )

  const onLocation = (next) => {
    setLocation(next)
    setLoc(next)
    setPickerOpen(false)
  }

  const onAddToCart = async (item) => {
    try {
      const created = await addCart(getUserId(), {
        plan_id: item.id,
        name: item.name,
        price: item.price,
        shop: item.merchant_name || '',
      })
      setCart((prev) => ({
        ...prev,
        [created.item_id]: { name: created.name, price: created.price, qty: created.qty },
      }))
      toast('已加入购物袋')
    } catch (e) {
      toast(e.message || '加入失败', 'error')
    }
  }

  const openMenu = () => {
    setMenuOpen(true)
    if (isLoggedIn()) {
      getProfile().then(setProfile).catch(() => setProfile(null))
    } else {
      setProfile(null)
    }
  }

  const MENU_LINKS = [
    { label: '我的收藏', path: '/favorites' },
    { label: '领券中心', path: '/coupons' },
    { label: '设置', path: '/settings' },
    { label: '关于跳舞兰', path: '/about' },
  ]

  return (
    <div className="min-h-full bg-bg pb-4">
      {/* 顶部定位条（美团外卖风格：左上角具体位置 + 下拉箭头；右侧菜单） */}
      <div
        className="animate-hero flex items-center justify-between px-5 pb-3 pt-3"
        style={{ animationDelay: '0ms' }}
      >
        <button
          onClick={() => setPickerOpen(true)}
          aria-label="选择位置"
          className="press flex min-w-0 items-center gap-1.5 py-1 text-ink"
        >
          <IconPin width={17} height={17} className="shrink-0 text-gold" />
          <span className="max-w-[160px] truncate text-[15px] font-medium">
            {loc?.name ? `深圳 · ${loc.name}` : '选择位置'}
          </span>
          <IconArrow width={11} height={11} className="shrink-0 rotate-90 text-sub" />
        </button>
        <button
          onClick={openMenu}
          aria-label="菜单"
          className="press -mr-1 flex items-center gap-1.5 p-1 text-ink"
        >
          <img
            src="/images/brand/logo.jpg"
            alt="跳舞兰"
            className="h-6 w-6 rounded-full border border-line bg-white object-cover"
          />
          <span className="font-serif-cn text-[15px] tracking-[2px]">
            跳舞兰
          </span>
          <IconMenu width={20} height={20} className="ml-0.5 text-ink" />
        </button>
      </div>

      {/* ≡ 侧拉菜单：个人资料 + 快捷入口 */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 bg-black/30" onClick={() => setMenuOpen(false)}>
          <div
            className="ml-auto flex h-full w-[240px] flex-col border-l border-line bg-white py-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 个人区 */}
            <button
              onClick={() => {
                setMenuOpen(false)
                nav('/profile')
              }}
              className="flex items-center gap-3 px-5 pb-5 text-left"
            >
              <SmartImage
                imgKey="avatar"
                color={imgColor('avatar')}
                className="h-[44px] w-[44px] rounded-full border border-line"
              />
              <div className="min-w-0">
                {profile || isLoggedIn() ? (
                  <>
                    <p className="truncate font-serif-cn text-[15px] font-normal text-ink">
                      {profile?.nickname || profile?.username || ''}
                    </p>
                    <p className="mt-0.5 truncate text-[10px] text-stone">
                      {profile?.id || '个人中心'}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-[14px] font-medium text-ink">登录 / 注册</p>
                    <p className="mt-0.5 text-[10px] text-stone">登录后同步对话与订单</p>
                  </>
                )}
              </div>
              <IconArrow width={14} height={14} className="ml-auto rotate-0 shrink-0 text-sub" />
            </button>
            <div className="mx-5 h-px bg-line" />

            {/* 菜单项 */}
            <div className="mt-2">
              <button
                onClick={() => {
                  setMenuOpen(false)
                  nav('/profile')
                }}
                className="block w-full px-5 py-3.5 text-left text-[13px] text-ink"
              >
                个人中心
              </button>
              {MENU_LINKS.map((l) => (
                <button
                  key={l.path}
                  onClick={() => {
                    setMenuOpen(false)
                    nav(l.path)
                  }}
                  className="block w-full px-5 py-3.5 text-left text-[13px] text-ink"
                >
                  {l.label}
                </button>
              ))}
            </div>
            <p className="mt-auto px-5 py-4 text-center">
              <img
                src="/images/brand/logo.jpg"
                alt="跳舞兰"
                className="mx-auto h-9 w-9 rounded-full border border-line bg-white object-cover"
              />
              <span className="mt-2 block text-[10px] tracking-[0.2em] text-stone">
                跳舞兰
                <br />
                花艺工坊
              </span>
            </p>
          </div>
        </div>
      )}

      {/* Hero（参考稿 .hero：居中 衬线大字 + 金线 + 金线花卉） */}
      <div className="px-6 pb-2 pt-6 text-center">
        <img
          src="/images/brand/logo.jpg"
          alt="跳舞兰"
          className="animate-hero mx-auto h-12 w-12 rounded-full border border-line bg-white object-cover shadow-soft"
          style={{ animationDelay: '100ms' }}
        />
        <p className="animate-hero eyebrow mt-3" style={{ animationDelay: '200ms' }}>
          花艺工坊 · 2026
        </p>
        <h1 className="animate-hero mt-3 font-serif-cn text-[36px] font-normal leading-[1.15] text-ink" style={{ animationDelay: '300ms' }}>
          为懂得欣赏
          <br />
          的人而绽放
        </h1>
        <div className="animate-hero mx-auto mt-5 h-px w-9 bg-gold" style={{ animationDelay: '400ms' }} />
        <p className="animate-hero mx-auto mt-5 max-w-[280px] text-[12px] leading-relaxed text-sub" style={{ animationDelay: '500ms' }}>
          每一束花，皆由花艺师手工甄选、当日采撷。以克制之美，承载最厚重的情意。
        </p>
        <div
          className="animate-hero mx-auto mt-6 flex h-[190px] w-[170px] items-center justify-center rounded-[4px] border border-line bg-[#F0EBE3]"
          style={{ animationDelay: '620ms' }}
        >
          <MaisonBloom size={150} />
        </div>
      </div>

      {/* 猜你喜欢（模块三：个性化推荐位，数据来自 /recommend/plans） */}
      <div className="mt-10 px-5">
        <Reveal>
          <div className="text-center">
            <p className="eyebrow">For You</p>
            <h2 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">猜你喜欢</h2>
            <div className="mx-auto mt-4 h-px w-9 bg-gold" />
          </div>
        </Reveal>
        <div className="mt-7">
          {recState === 'loading' && (
            <div className="flex gap-3 overflow-x-auto">
              {Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-[200px] w-[180px] shrink-0 animate-pulse rounded-[4px] bg-line" />
              ))}
            </div>
          )}
          {recState === 'error' && (
            <div className="flex h-[120px] items-center justify-center rounded-[4px] border border-line bg-white text-[12px] text-sub">
              推荐加载失败，请稍后重试
            </div>
          )}
          {recState === 'empty' && (
            <div className="flex h-[120px] items-center justify-center rounded-[4px] border border-line bg-white text-[12px] text-sub">
              暂无推荐，去看看精选（收藏越多越懂你）
            </div>
          )}
          {recState === 'ok' && (
            <Carousel
              items={recPlans}
              cardWidth={180}
              gap={12}
              renderItem={(p) => (
                <ProductCard
                  compact
                  p={p}
                  onOpen={() => nav(`/product/${p.id}`)}
                  onAdd={onAddToCart}
                  fav={favs[p.id]}
                  onFav={() => onToggleFav(p)}
                />
              )}
            />
          )}
        </div>
      </div>

      {/* 当季臻选（参考稿 .sec：居中 eyebrow + 衬线标题 + 金线；模块三策展推荐 /recommend/signature） */}
      <div className="mt-10 px-5">
        <Reveal>
          <div className="text-center">
            <p className="eyebrow">Signature Collection</p>
            <h2 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">当季臻选</h2>
            <div className="mx-auto mt-4 h-px w-9 bg-gold" />
          </div>
        </Reveal>
        <div className="mt-7 space-y-4">
          {sigState === 'loading' &&
            Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="h-[220px] animate-pulse rounded-[4px] bg-line" />
            ))}
          {sigState === 'error' && (
            <div className="flex h-[120px] items-center justify-center rounded-[4px] border border-line bg-white text-[12px] text-sub">
              精选加载失败，请稍后重试
            </div>
          )}
          {sigState === 'ok' &&
            sigPlans.map((p, i) => (
              <Reveal key={p.id} delay={i * 140}>
                <ProductCard
                  p={p}
                  dist={p.dist_km}
                  onOpen={() => nav(`/product/${p.id}`)}
                  onAdd={onAddToCart}
                />
              </Reveal>
            ))}
        </div>
      </div>

      {/* 热门商家（按当前定位距离优先：后端 /shops?lat=&lng= 排序，最近的在最前） */}
      <div className="mt-12 px-5">
        <Reveal>
          <div className="text-center">
            <p className="eyebrow">Maisons</p>
            <h2 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">合作花店</h2>
            <div className="mx-auto mt-4 h-px w-9 bg-gold" />
          </div>
        </Reveal>
        <div className="mt-7 space-y-3">
          {loading
            ? Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-[64px] animate-pulse rounded-[4px] bg-line" />
              ))
            : shops.slice(0, 4).map((s, i) => (
                <Reveal key={s.id} delay={i * 140}>
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
                    className="press flex cursor-pointer items-center gap-3 rounded-[4px] border border-line bg-white px-3.5 py-3"
                  >
                    <SmartImage
                      src={shopImage(s)}
                      color={imgColor(s.id)}
                      className="h-[44px] w-[52px] rounded-[2px]"
                    />
                    <div className="flex-1">
                      <p className="font-serif-cn text-[15px] font-normal text-ink">
                        {s.name}
                        {loc && i === 0 && (
                          <span className="ml-1.5 rounded-[2px] bg-gold/15 px-1.5 py-px text-[9px] text-gold-dark">
                            距你最近
                          </span>
                        )}
                      </p>
                      <p className="mt-1 flex items-center gap-1 text-[10px] text-sub">
                        <IconStar width={10} height={10} className="text-cream" /> {s.rating} ·{' '}
                        {s.eta} · 起送 ¥{Number(s.min_delivery).toFixed(2)}
                      </p>
                    </div>
                    <span className="text-[10px] text-sub">{s.dist}</span>
                  </div>
                </Reveal>
              ))}
        </div>
      </div>

      {/* 金句区（参考稿 .quote） */}
      <Reveal className="mt-14 border-y border-line px-8 py-12 text-center">
        <p className="font-serif-cn text-[22px] font-normal leading-[1.5] text-ink">
          “真正的奢侈，是
          <br />
          把时间温柔地，
          <br />
          交还给一朵花。”
        </p>
        <p className="quote-credit mt-5">— 跳舞兰 · 花艺工坊</p>
      </Reveal>

      {/* 页脚 */}
      <Reveal delay={60}>
        <p className="py-8 text-center text-[10px] tracking-[1px] text-stone">
          跳舞兰 — 轻奢花艺 · 2026
        </p>
      </Reveal>

      {/* 吸底结算栏（参考稿 .sticky：墨黑底 + 香槟金 CTA） */}
      <div className="sticky bottom-0 z-10 flex items-center justify-between bg-ink px-5 py-3.5">
        <div>
          <p className="text-[10px] tracking-[1px] text-[#FAF8F5]/70">
            购物袋 · {cartCount} 件
          </p>
          <p className="mt-0.5 text-[15px] text-[#FAF8F5]">
            {cartTotal > 0 ? (
              <>
                <span className="mr-0.5 text-[10px]">¥</span>
                {cartTotal}
              </>
            ) : (
              '0'
            )}
          </p>
        </div>
        <button
          onClick={() => nav('/cart')}
          className="rounded-[2px] bg-gold px-6 py-2.5 text-[12px] font-medium tracking-[1px] text-[#FAF8F5]"
        >
          去结算
        </button>
      </div>

      <LocationPicker
        open={pickerOpen}
        onConfirm={onLocation}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  )
}