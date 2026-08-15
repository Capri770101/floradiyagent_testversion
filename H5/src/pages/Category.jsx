import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Placeholder } from '../components/Placeholder'
import { Pill } from '../components/Pill'
import { IconSearch, IconArrow } from '../components/icons'
import { listPlans } from '../api/shop'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'

// 09 分类
function Glyph({ name, color = '#E88AA1' }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: color,
    strokeWidth: 1.6,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
  }
  switch (name) {
    case 'tulip':
      return (
        <svg {...common}>
          <path d="M12 21V11" />
          <path d="M12 11c0-3 2-5 0-8-2 3 0 5 0 8Z" />
          <path d="M9 14c-2-1-3-3-3-5 2 0 3 1 3 3M15 14c2-1 3-3 3-5-2 0-3 1-3 3" />
        </svg>
      )
    case 'sun':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" />
        </svg>
      )
    case 'carnation':
      return (
        <svg {...common}>
          <path d="M12 21V9" />
          <path d="M12 9c-3 0-4-2-4-4 2 0 3 1 4 3 1-2 2-3 4-3 0 2-1 4-4 4Z" />
        </svg>
      )
    case 'bouquet':
      return (
        <svg {...common}>
          <path d="M8 20 12 8l4 12" />
          <path d="M12 8 7 4M12 8l5-4M12 8v4" />
        </svg>
      )
    case 'green':
      return (
        <svg {...common}>
          <path d="M5 19c0-8 6-13 14-14-1 8-6 14-14 14Z" />
        </svg>
      )
    default: // rose
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="2" />
          <path d="M12 10c0-2 1.5-4 0-5s-1 2-1 4M14 12c2 0 4-1.5 5 0s-2 1-4 1M12 14c0 2-1.5 4 0 5s1-2 1-4M10 12c-2 0-4 1.5-5 0s2-1 4-1" />
        </svg>
      )
  }
}

const CATEGORIES = [
  { id: 'all', name: '全部', glyph: 'bouquet' },
  { id: 'cat_rose', name: '玫瑰', glyph: 'rose' },
  { id: 'cat_tulip', name: '郁金香', glyph: 'tulip' },
  { id: 'cat_sun', name: '向日葵', glyph: 'sun' },
  { id: 'cat_carnation', name: '康乃馨', glyph: 'carnation' },
  { id: 'cat_bouquet', name: '花束', glyph: 'bouquet' },
  { id: 'cat_green', name: '绿植', glyph: 'green' },
]
const SCENES = ['全部', '生日', '纪念日', '告白', '送妈妈', '毕业', '日常']

export default function Category() {
  const nav = useNavigate()
  const [cat, setCat] = useState(0)
  const [scene, setScene] = useState(0)
  const [query, setQuery] = useState('')
  const [plans, setPlans] = useState([])

  useEffect(() => {
    listPlans().then(setPlans).catch((e) => console.error('分类加载失败', e))
  }, [])

  // 分类 / 场景 / 搜索 三重过滤：选中「全部」(index 0) 时不收窄
  const featured = useMemo(() => {
    const q = query.trim().toLowerCase()
    const catName = CATEGORIES[cat]?.name
    const sceneName = SCENES[scene]
    return plans.filter((p) => {
      const hay = (p.name + ' ' + (p.desc || '') + ' ' + (p.tags || []).join(' ')).toLowerCase()
      if (q && !hay.includes(q)) return false
      if (cat !== 0 && catName && !hay.includes(catName.toLowerCase())) return false
      if (scene !== 0 && sceneName && !hay.includes(sceneName.toLowerCase())) return false
      return true
    })
  }, [plans, query, cat, scene])

  return (
    <div className="min-h-full bg-bg pb-8">
      <div className="px-5 pt-7">
        <h1 className="text-[20px] font-medium text-dark">发现好花</h1>
        <p className="mt-1 text-[11px] text-sub">挑选心意，从一束花开始</p>
      </div>

      {/* 搜索条（实时过滤精选） */}
      <div className="mx-5 mt-4 flex h-[44px] items-center gap-2 rounded-[22px] bg-white px-4">
        <IconSearch width={16} height={16} className="text-sub" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索花束、花材或店铺"
          className="flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-sub"
        />
      </div>

      {/* 热门分类 */}
      <div className="mt-7 px-5">
        <h2 className="text-[16px] font-medium text-dark">热门分类</h2>
        <div className="mt-3 grid grid-cols-3 gap-y-4">
          {CATEGORIES.map((c, i) => (
            <button
              key={c.id}
              onClick={() => setCat(i)}
              className="flex flex-col items-center gap-1.5"
            >
              <div
                className={`flex h-[44px] w-[44px] items-center justify-center rounded-[12px] bg-white transition ${
                  cat === i ? 'ring-2 ring-pink' : ''
                }`}
              >
                <Glyph name={c.glyph} />
              </div>
              <span className="text-[11px] font-medium text-ink">{c.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 按场景 */}
      <div className="mt-7 px-5">
        <h2 className="text-[16px] font-medium text-dark">按场景</h2>
        <div className="mt-3 grid grid-cols-3 gap-2.5">
          {SCENES.map((s, i) => (
            <Pill
              key={s}
              label={s}
              selected={scene === i}
              onClick={() => setScene(i)}
              style={{ width: 96 }}
            />
          ))}
        </div>
      </div>

      {/* 精选花束（真实接口） */}
      <div className="mt-9 px-5">
        <h2 className="text-[16px] font-medium text-dark">精选花束</h2>
        <div className="mt-3 space-y-3">
          {featured.map((f) => (
            <div
              key={f.id}
              role="button"
              tabIndex={0}
              onClick={() => nav(`/product/${f.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  nav(`/product/${f.id}`)
                }
              }}
              className="press flex cursor-pointer items-center gap-3 rounded-card bg-white p-3 shadow-card"
            >
              <SmartImage
                src={itemImagePath('category', f.id)}
                color={imgColor(f.id)}
                className="h-[60px] w-[78px] rounded-[12px]"
              />
              <div className="flex-1">
                <p className="text-[13px] font-medium text-ink">{f.name}</p>
                <p className="mt-1 text-[10px] text-sub">{(f.tags || []).join(' · ')}</p>
                {/* 商品对应的店家：点击进店 */}
                {f.shop_id && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      nav(`/shop/${f.shop_id}`)
                    }}
                    className="mt-1 flex items-center gap-0.5 text-[10px] text-pink"
                  >
                    🏪 {f.merchant_name || '花店'}
                    <IconArrow width={9} height={9} />
                  </button>
                )}
                <p className="mt-1 text-[12px] font-medium text-pink">¥{f.price}</p>
              </div>
              <IconArrow width={16} height={16} className="text-sub" />
            </div>
          ))}
          {featured.length === 0 && (
            <p className="py-6 text-center text-[12px] text-sub">没有找到匹配的花束</p>
          )}
        </div>
      </div>
    </div>
  )
}
