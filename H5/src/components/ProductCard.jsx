import React from 'react'
import { useNavigate } from 'react-router-dom'
import { IconStore } from './icons'
import MaisonBloom from './MaisonBloom'

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

// 整屏宽产品卡（参考稿 .prod）：16:10 金线花卉图区 + 贴角标签 + 衬线名 + 描述 + 价格/加入
export default function ProductCard({ p, onOpen, onAdd }) {
  const v = Math.abs((p.id || '').split('').reduce((s, c) => s + c.charCodeAt(0), 0)) % 3
  const variant = ['rose', 'tulip', 'peony'][v]
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === 'Enter' && onOpen()}
      className="press cursor-pointer overflow-hidden rounded-[4px] border border-line bg-white"
    >
      <div className="relative flex aspect-[16/10] items-center justify-center border-b border-line bg-[#F0EBE3]">
        <MaisonBloom size={110} variant={variant} className="opacity-90" />
        <PlanTag label={p.label} />
      </div>
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
            className="rounded-[2px] bg-sand px-4 py-2 text-[11px] font-medium tracking-[1px] text-gold-dark"
          >
            加入
          </button>
        </div>
      </div>
    </div>
  )
}
