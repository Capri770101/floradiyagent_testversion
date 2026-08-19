import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconSearch } from '../components/icons'
import { FloraBloom } from '../components/FloralDecor'
import ProductCard from '../components/ProductCard'
import { listPlans, addCart } from '../api/shop'
import { getUserId } from '../api/chat'
import { matchPinyinFields } from '../utils/pinyin'
import { toast } from '../utils/toast'

// 分类页：搜索 + 精选花束（整屏宽产品卡）
export default function Category() {
  const nav = useNavigate()
  const [query, setQuery] = useState('')
  const [plans, setPlans] = useState([])

  useEffect(() => {
    listPlans().then(setPlans).catch((e) => console.error('分类加载失败', e))
  }, [])

  const featured = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return plans
    return plans.filter((p) =>
      matchPinyinFields(
        [p.name, p.desc || '', (p.tags || []).join(' ')],
        q,
      ),
    )
  }, [plans, query])

  const onAdd = async (item) => {
    try {
      await addCart(getUserId(), {
        plan_id: item.id,
        name: item.name,
        price: item.price,
        shop: item.merchant_name || '',
      })
      toast('已加入购物袋')
    } catch (e) {
      toast(e.message || '加入失败', 'error')
    }
  }

  return (
    <div className="min-h-full bg-bg pb-10">
      {/* 品牌头 */}
      <div className="px-5 pt-8">
        <p className="eyebrow">Collection</p>
        <h1 className="mt-1 font-serif-cn text-[28px] font-normal text-ink">发现好花</h1>
        <p className="mt-1.5 text-[11px] text-sub">挑选心意，从一束花开始</p>
      </div>

      {/* 搜索条（聚焦出金色竖线 + 花饰点缀） */}
      <div className="field-shell mx-5 mt-5 flex h-[42px] items-center gap-2 rounded-[2px] border border-line bg-white px-4">
        <IconSearch width={15} height={15} className="text-gold" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索花束、花材或店铺"
          className="maison-field-inline flex-1"
        />
        <FloraBloom width={13} height={13} className="shrink-0 text-gold/40" />
      </div>

      {/* 精选花束 */}
      <div className="mt-9 px-5">
        <div className="text-center">
          <p className="eyebrow">Signature Collection</p>
          <h2 className="mt-2 font-serif-cn text-[26px] font-normal text-ink">精选花束</h2>
          <div className="mx-auto mt-4 h-px w-9 bg-gold" />
        </div>
        <div className="mt-7 space-y-4">
          {featured.map((f) => (
            <ProductCard key={f.id} p={f} onOpen={() => nav(`/product/${f.id}`)} onAdd={onAdd} />
          ))}
          {featured.length === 0 && (
            <p className="py-10 text-center text-[12px] text-stone">没有找到匹配的花束</p>
          )}
        </div>
      </div>
    </div>
  )
}
