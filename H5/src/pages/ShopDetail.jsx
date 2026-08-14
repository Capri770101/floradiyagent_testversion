import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { Placeholder } from '../components/Placeholder'
import { IconStar } from '../components/icons'
import { PLACEHOLDER } from '../tokens'
import { getShop } from '../api/shop'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'

const TABS = ['店铺首页', '全部商品', '评价']

// 05 商家详情
export default function ShopDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [shop, setShop] = useState(null)
  const [tab, setTab] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    getShop(id)
      .then((s) => alive && setShop(s))
      .catch((e) => alive && console.error('店铺加载失败', e))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [id])

  if (loading || !shop) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="店铺" />
        <div className="flex-1 p-5">
          <div className="h-[170px] animate-pulse rounded-[20px] bg-line" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title={shop.name} />
      <div className="flex-1 overflow-y-auto">
        <SmartImage imgKey="shop_cover" className="h-[170px] w-full" />
        <div className="px-5 pt-4">
          <h1 className="text-[20px] font-medium text-dark">{shop.name}</h1>
          <p className="mt-1 flex items-center gap-1 text-[11px] text-sub">
            <IconStar width={11} height={11} className="text-cream" /> {shop.rating} ·{' '}
            {shop.status} · {shop.dist}
          </p>
        </div>
        <div className="mt-3 flex gap-6 border-b border-line px-5">
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              className={`border-b-2 pb-2 text-[13px] ${
                tab === i ? 'border-pink font-medium text-pink' : 'border-transparent text-sub'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="px-5 pt-4">
          <h2 className="text-[16px] font-medium text-dark">店铺推荐</h2>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {(shop.recommend || []).map((r) => (
              <div
                key={r.id}
                onClick={() => nav(`/product/${r.id}`)}
                className="press"
              >
                <SmartImage
                  src={itemImagePath('plans', r.id)}
                  color={imgColor(r.id)}
                  className="h-[72px] w-full rounded-[10px]"
                />
                <p className="mt-1.5 truncate text-[10px] text-ink">{r.name}</p>
                <p className="text-[11px] font-medium text-pink">¥{r.price}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="px-5 pt-7">
          <h2 className="text-[16px] font-medium text-dark">店铺介绍</h2>
          <p className="mt-2 text-[11px] leading-relaxed text-sub">{shop.intro}</p>
        </div>
      </div>
      <div className="flex shrink-0 justify-end border-t border-line bg-bg px-5 py-4">
        <Button
          style={{ width: 119 }}
          onClick={() => shop.recommend?.[0] && nav(`/product/${shop.recommend[0].id}`)}
        >
          进入店铺
        </Button>
      </div>
    </div>
  )
}
