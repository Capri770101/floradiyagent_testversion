import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconArrow, IconStar, IconPin, IconMenu } from '../components/icons'
import LocationPicker from '../components/LocationPicker'
import ProductCard from '../components/ProductCard'
import MaisonBloom from '../components/MaisonBloom'
import SmartImage from '../components/SmartImage'
import { listPlans, listShops, getCart, addCart } from '../api/shop'
import { getUserId } from '../api/chat'
import { isLoggedIn, getProfile } from '../api/auth'
import { toast } from '../utils/toast'
import { getLocation, setLocation } from '../utils/location'
import { imgColor } from '../utils/color'
import { itemImagePath } from '../assets/imageMap'

export default function Home() {
  const nav = useNavigate()
  const [plans, setPlans] = useState([])
  const [shops, setShops] = useState([])
  const [cart, setCart] = useState({})
  const [loc, setLoc] = useState(getLocation)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [ps, ss, items] = await Promise.all([listPlans(), listShops(loc), getCart(getUserId())])
        if (!alive) return
        setPlans(ps)
        setShops(ss)
        const m = {}
        ;(items || []).forEach((it) => {
          m[it.item_id] = { name: it.name, price: it.price, qty: it.qty }
        })
        setCart(m)
      } catch (e) {
        if (alive) console.error('首页加载失败', e)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc])

  const cartCount = useMemo(() => Object.values(cart).reduce((s, it) => s + it.qty, 0), [cart])
  const cartTotal = useMemo(
    () => Object.values(cart).reduce((s, it) => s + it.price * it.qty, 0),
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
    { label: '关于 MAISON·FLORA', path: '/about' },
  ]

  return (
    <div className="min-h-full bg-bg pb-4">
      {/* 顶部定位条（美团外卖风格：左上角具体位置 + 下拉箭头；右侧菜单） */}
      <div className="flex items-center justify-between px-5 pb-3 pt-3">
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
            MAISON<span className="text-gold">·</span>FLORA
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
                      {profile?.nickname || profile?.username || 'Capri'}
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
                MAISON·FLORA
                <br />
                Atelier de Fleurs
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
          className="mx-auto h-12 w-12 rounded-full border border-line bg-white object-cover shadow-soft"
        />
        <p className="eyebrow mt-3">Atelier de Fleurs · 2026</p>
        <h1 className="mt-3 font-serif-cn text-[36px] font-normal leading-[1.15] text-ink">
          为懂得欣赏
          <br />
          的人而绽放
        </h1>
        <div className="mx-auto mt-5 h-px w-9 bg-gold" />
        <p className="mx-auto mt-5 max-w-[280px] text-[12px] leading-relaxed text-sub">
          每一束花，皆由花艺师手工甄选、当日采撷。以克制之美，承载最厚重的情意。
        </p>
        <div className="mx-auto mt-6 flex h-[190px] w-[170px] items-center justify-center rounded-[4px] border border-line bg-[#F0EBE3]">
          <MaisonBloom size={150} />
        </div>
      </div>

      {/* 当季臻选（参考稿 .sec：居中 eyebrow + 衬线标题 + 金线） */}
      <div className="mt-10 px-5">
        <div className="text-center">
          <p className="eyebrow">Signature Collection</p>
          <h2 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">当季臻选</h2>
          <div className="mx-auto mt-4 h-px w-9 bg-gold" />
        </div>
        <div className="mt-7 space-y-4">
          {loading
            ? Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-[220px] animate-pulse rounded-[4px] bg-line" />
              ))
            : plans.slice(0, 3).map((p) => (
                <ProductCard key={p.id} p={p} onOpen={() => nav(`/product/${p.id}`)} onAdd={onAddToCart} />
              ))}
        </div>
      </div>

      {/* 热门商家 */}
      <div className="mt-12 px-5">
        <div className="text-center">
          <p className="eyebrow">Maisons</p>
          <h2 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">合作花店</h2>
          <div className="mx-auto mt-4 h-px w-9 bg-gold" />
        </div>
        <div className="mt-7 space-y-3">
          {loading
            ? Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-[64px] animate-pulse rounded-[4px] bg-line" />
              ))
            : shops.slice(0, 4).map((s) => (
                <div
                  key={s.id}
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
                    src={itemImagePath('shops', s.id)}
                    color={imgColor(s.id)}
                    className="h-[44px] w-[52px] rounded-[2px]"
                  />
                  <div className="flex-1">
                    <p className="font-serif-cn text-[15px] font-normal text-ink">{s.name}</p>
                    <p className="mt-1 flex items-center gap-1 text-[10px] text-sub">
                      <IconStar width={10} height={10} className="text-cream" /> {s.rating} ·{' '}
                      {s.eta} · 起送 ¥{s.min_delivery}
                    </p>
                  </div>
                  <span className="text-[10px] text-sub">{s.dist}</span>
                </div>
              ))}
        </div>
      </div>

      {/* 金句区（参考稿 .quote） */}
      <div className="mt-14 border-y border-line px-8 py-12 text-center">
        <p className="font-serif-cn text-[22px] font-normal leading-[1.5] text-ink">
          “真正的奢侈，是
          <br />
          把时间温柔地，
          <br />
          交还给一朵花。”
        </p>
        <p className="quote-credit mt-5">— MAISON FLORA ATELIER</p>
      </div>

      {/* 页脚 */}
      <p className="py-8 text-center text-[10px] tracking-[1px] text-stone">
        MAISON · FLORA — 轻奢花艺 · 2026
      </p>

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
