import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconStore, IconPlus } from './icons'
import MaisonBloom from './MaisonBloom'
import { itemImagePath } from '../assets/imageMap'

// 店家行：点击进店（保留「商品关联店家」需求）
function ShopLine({ p }) {
  const nav = useNavigate()
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        nav(`/shop/${p.shop_id}`)
      }}
      className="mt-1.5 flex items-center gap-1 text-[10px] text-gold"
    >
      <IconStore width={11} height={11} />
      {p.merchant_name || '花店'}
    </button>
  )
}

// 角标（参考稿 §5）：Premium=金色实底 / Limited=酒红描边 / New=砂色底
export function PlanTag({ label }) {
  if (label === 'Premium')
    return <span className="absolute left-3 top-3 rounded-[2px] bg-gold px-2.5 py-1 text-[9px] font-medium tracking-[1px] text-[#FAF8F5]">{label}</span>
  if (label === 'Limited')
    return <span className="absolute left-3 top-3 rounded-[2px] border border-burgundy bg-white/80 px-2.5 py-1 text-[9px] font-medium tracking-[1px] text-burgundy">{label}</span>
  return <span className="absolute left-3 top-3 rounded-[2px] bg-sand px-2.5 py-1 text-[9px] font-medium tracking-[1px] text-gold-dark">{label}</span>
}

// 图区：真实鲜花照片优先；文件未就位时回退金线花卉插画
function CardImage({ p }) {
  const [failed, setFailed] = useState(false)
  const src = itemImagePath('plans', p.id)
  const v = Math.abs((p.id || '').split('').reduce((s, c) => s + c.charCodeAt(0), 0)) % 3
  const variant = ['rose', 'tulip', 'peony'][v]
  return (
    <div className="relative flex aspect-[16/10] items-center justify-center overflow-hidden border-b border-line bg-[#F0EBE3]">
      {!failed && (
        <img
          src={src}
          alt={p.name}
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
      {failed && <MaisonBloom size={110} variant={variant} className="opacity-90" />}
      <PlanTag label={p.label} />
    </div>
  )
}

// 整屏宽产品卡（参考稿 .prod）：16:10 图区 + 贴角标签 + 衬线名 + 描述 + 价格/加入购物车
export default function ProductCard({ p, onOpen, onAdd }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === 'Enter' && onOpen()}
      className="press cursor-pointer overflow-hidden rounded-[4px] border border-line bg-white"
    >
      <CardImage p={p} />
      <div className="px-4 pb-4 pt-3.5">
        <p className="font-serif-cn text-[19px] font-normal leading-snug text-ink">{p.name}</p>
        <p className="mt-1 line-clamp-1 text-[11px] text-sub">{p.desc}</p>
        {p.shop_id && <ShopLine p={p} />}
        <div className="mt-3 flex items-center justify-between">
          <p className="text-[15px] text-ink">
            <span className="mr-0.5 text-[10px] text-stone">¥</span>
            {p.price}
          </p>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onAdd ? onAdd(p) : onOpen()
            }}
            className="flex items-center gap-1.5 rounded-[2px] bg-dark px-4 py-2 text-[11px] font-medium tracking-[1px] text-[#FAF8F5]"
          >
            <IconPlus width={11} height={11} strokeWidth={2} className="text-gold" />
            加入购物车
          </button>
        </div>
      </div>
    </div>
  )
}
