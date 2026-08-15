import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconArrow, IconStar, IconPin, IconStore } from '../components/icons'
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
      {/* 品牌头：MAISON·FLORA 衬线 logo + 法文副标 */}
      <div className="px-5 pt-8">
        <p className="eyebrow">Atelier de Fleurs</p>
        <h1 className="mt-1 font-serif-cn text-[30px] font-normal leading-none tracking-wide text-ink">
          MAISON·FLORA
        </h1>
        <p className="mt-2 text-[12px] text-sub">轻奢花艺 · AI 专属设计</p>
      </div>

      {/* 定位栏：显示当前位置，点击重新选择 */}
      <button
        onClick={() => setPickerOpen(true)}
        className="press mx-5 mt-4 flex h-[36px] w-fit items-center gap-1.5 rounded-[2px] border border-line bg-white px-3 text-[11px] text-ink"
      >
        <IconPin width={13} height={13} className="text-gold" />
        <span className="max-w-[130px] truncate font-medium">{locationName() || '选择位置'}</span>
        <IconArrow width={10} height={10} className="rotate-90 text-sub" />
      </button>

      {/* Hero —— Maison 主视觉：象牙白 + 衬线大字 + 金色短线 */}
      <div className="hero-flora relative mx-5 mt-4 overflow-hidden rounded-[4px] p-6">
        <p className="eyebrow">Signature Bouquets</p>
        <p className="mt-3 font-serif-cn text-[26px] font-normal leading-snug text-ink">
          把时间，温柔地
          <br />
          交还给一朵花
        </p>
        <div className="mt-4 h-[2px] w-10 bg-gold" />
        <p className="mt-3 text-[12px] text-sub">智能推荐 · 专属设计 · 送花无忧</p>
        <button
          onClick={() => nav('/agent')}
          className="press mt-5 inline-flex h-[44px] w-[132px] items-center justify-center rounded-[2px] bg-dark text-[14px] font-medium tracking-wide text-[#FAF8F5]"
        >
          开始对话
        </button>
      </div>

      {/* 今日推荐 */}
      <div className="mt-12 px-5">
        <SectionTitle
          eyebrow="Curation"
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
        <div className="mt-5 grid grid-cols-3 gap-2">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-[120px] animate-pulse rounded-[2px] bg-line" />
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
                  className="press cursor-pointer rounded-[2px] bg-white p-2 border border-line"
                >
                  <SmartImage
                    src={itemImagePath('plans', p.id)}
                    color={imgColor(p.id)}
                    className="h-[68px] w-full rounded-[4px]"
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
                      <IconStore width={9} height={9} className="shrink-0 text-gold" />
                      <span className="truncate">{p.merchant_name || '花店'}</span>
                      <IconArrow width={8} height={8} className="shrink-0" />
                    </button>
                  )}
                </div>
              ))}
        </div>
      </div>

      {/* 热门商家 */}
      <div className="mt-12 px-5">
        <SectionTitle eyebrow="Maisons" title="热门商家" />
        <div className="mt-5 space-y-3">
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
                  className="press flex cursor-pointer items-center gap-3 rounded-card bg-white p-3 border border-line"
                >
                  <SmartImage
                    src={itemImagePath('shops', s.id)}
                    color={imgColor(s.id)}
                    className="h-[44px] w-[54px] rounded-[4px]"
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
