import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconArrow, IconStar } from '../components/icons'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'
import SectionTitle from '../components/SectionTitle'
import LocationPicker from '../components/LocationPicker'
import { listPlans, listShops } from '../api/shop'
import { getLocation, locationName, setLocation } from '../utils/location'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'

// 01 首页
export default function Home() {
  const nav = useNavigate()
  const [plans, setPlans] = useState([])
  const [shops, setShops] = useState([])
  const [loc, setLoc] = useState(getLocation)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [ps, ss] = await Promise.all([listPlans(), listShops(loc)])
        if (!alive) return
        setPlans(ps)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc])

  const onLocation = (next) => {
    setLocation(next) // 持久化，首页/分类/对话/店铺列表共用
    setLoc(next)
    setPickerOpen(false)
  }

  return (
    <div className="min-h-full bg-bg pb-8">
      <div className="px-5 pt-7">
        <h1 className="font-serif-cn text-[25px] font-medium text-dark">FloraDIY</h1>
        <p className="mt-1 text-[12px] text-sub">AI帮你设计专属花束</p>
      </div>

      {/* 定位栏：显示当前位置，点击重新选择 */}
      <button
        onClick={() => setPickerOpen(true)}
        className="press mx-5 mt-3 flex h-[34px] w-fit items-center gap-1 rounded-full bg-white px-3 text-[11px] text-ink shadow-card"
      >
        <span className="text-[12px]">📍</span>
        <span className="max-w-[130px] truncate font-medium">{locationName() || '选择位置'}</span>
        <IconArrow width={10} height={10} className="rotate-90 text-sub" />
      </button>

      {/* Hero Banner —— 文艺封面：暖渐变 + 角落花枝 + 衬线标题 */}
      <div className="hero-flora relative mx-5 mt-3 overflow-hidden rounded-[24px] p-4 shadow-soft">
        <FloraCorner
          className="pointer-events-none absolute -right-3 -top-2 text-white/55"
          style={{ width: 110, height: 110 }}
        />
        <FloraSprig
          className="pointer-events-none absolute bottom-2 right-3 text-pink/30"
          style={{ width: 64, height: 64 }}
        />
        <p className="font-serif-cn text-[22px] font-medium leading-tight text-dark">为生活</p>
        <p className="font-serif-cn text-[22px] font-medium leading-tight text-dark">增添一束浪漫</p>
        <p className="mt-2 text-[12px] text-sub">智能推荐 · 专属设计 · 送花无忧</p>
        <button
          onClick={() => nav('/agent')}
          className="press mt-4 inline-flex h-[42px] w-[118px] items-center justify-center rounded-btn bg-pink text-[14px] font-medium text-white"
        >
          开始对话
        </button>
      </div>

      {/* 今日推荐 */}
      <div className="mt-7 px-5">
        <SectionTitle
          title="今日推荐"
          action={
            <button
              onClick={() => nav('/category')}
              className="flex items-center text-[11px] text-sub"
            >
              更多 <IconArrow width={12} height={12} />
            </button>
          }
        />
        <div className="mt-3 grid grid-cols-3 gap-2">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-[120px] animate-pulse rounded-[10px] bg-line" />
              ))
            : plans.slice(0, 3).map((p) => (
                <div
                  key={p.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => nav(`/product/${p.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      nav(`/product/${p.id}`)
                    }
                  }}
                  className="press cursor-pointer rounded-[12px] bg-white p-2 shadow-card"
                >
                  <SmartImage
                    src={itemImagePath('plans', p.id)}
                    color={imgColor(p.id)}
                    className="h-[68px] w-full rounded-[10px]"
                  />
                  <p className="mt-2 truncate text-[11px] text-ink">{p.name}</p>
                  <p className="text-[12px] font-medium text-pink">¥{p.price}</p>
                  {/* 商品对应的店家：点击进店 */}
                  {p.shop_id && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        nav(`/shop/${p.shop_id}`)
                      }}
                      className="mt-1 flex w-full items-center gap-0.5 truncate text-[9px] text-sub"
                    >
                      <span className="shrink-0">🏪</span>
                      <span className="truncate">{p.merchant_name || '花店'}</span>
                      <IconArrow width={8} height={8} className="shrink-0" />
                    </button>
                  )}
                </div>
              ))}
        </div>
      </div>

      {/* 热门商家 */}
      <div className="mt-8 px-5">
        <SectionTitle title="热门商家" />
        <div className="mt-3 space-y-3">
          {loading
            ? Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-[60px] animate-pulse rounded-card bg-line" />
              ))
            : shops.map((s) => (
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
                  className="press flex cursor-pointer items-center gap-3 rounded-card bg-white p-3 shadow-card"
                >
                  <SmartImage
                    src={itemImagePath('shops', s.id)}
                    color={imgColor(s.id)}
                    className="h-[44px] w-[54px] rounded-[10px]"
                  />
                  <div className="flex-1">
                    <p className="text-[13px] font-medium text-ink">{s.name}</p>
                    <p className="mt-1 flex items-center gap-1 text-[11px] text-sub">
                      <IconStar width={11} height={11} className="text-cream" /> {s.rating} ·{' '}
                      {s.eta} · 起送 ¥{s.min_delivery}
                    </p>
                  </div>
                  <span className="text-[10px] text-sub">{s.dist}</span>
                </div>
              ))}
        </div>
      </div>

      <LocationPicker
        open={pickerOpen}
        onConfirm={onLocation}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  )
}
