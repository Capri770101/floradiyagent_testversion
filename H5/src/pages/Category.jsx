import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconSearch } from '../components/icons'
import { FloraBloom } from '../components/FloralDecor'
import ProductCard from '../components/ProductCard'
import Reveal from '../components/Reveal'
import { listPlans, listCategories, addCart } from '../api/shop'
import { getUserId } from '../api/chat'
import { matchPinyinFields } from '../utils/pinyin'
import { toast } from '../utils/toast'

// 分类页：分类导航 + 搜索 + 按分类筛选（整屏宽产品卡）
export default function Category() {
  const nav = useNavigate()
  const [query, setQuery] = useState('')
  const [plans, setPlans] = useState([])
  const [cats, setCats] = useState([])
  const [active, setActive] = useState('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    Promise.all([listPlans(), listCategories()])
      .then(([pl, ca]) => {
        if (!alive) return
        setPlans(pl)
        setCats(ca || [])
      })
      .catch((e) => console.error('分类加载失败', e))
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const catName = useMemo(() => {
    const m = {}
    cats.forEach((c) => {
      m[c.id] = c.name
    })
    return m
  }, [cats])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return plans.filter((p) => {
      if (active !== 'all' && p.category_id !== active) return false
      if (!q) return true
      return matchPinyinFields([p.name, p.desc || '', (p.tags || []).join(' ')], q)
    })
  }, [plans, active, query])

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

  const sectionTitle = active === 'all' ? '全部花束' : catName[active] || '花束'

  return (
    <div className="min-h-full bg-bg pb-10">
      {/* 品牌头 */}
      <Reveal>
        <div className="px-5 pt-8">
          <p className="eyebrow">Collection</p>
          <h1 className="mt-1 font-serif-cn text-[28px] font-normal text-ink">发现好花</h1>
          <p className="mt-1.5 text-[11px] text-sub">挑选心意，从一束花开始</p>
        </div>
      </Reveal>

      {/* 搜索条 */}
      <Reveal delay={80}>
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
      </Reveal>

      {/* 分类导航 */}
      <div className="app-scroll mt-5 flex gap-2 overflow-x-auto px-5">
        <CatChip label="全部" active={active === 'all'} onClick={() => setActive('all')} />
        {cats.map((c) => (
          <CatChip
            key={c.id}
            label={c.name}
            count={c.plan_count}
            active={active === c.id}
            onClick={() => setActive(c.id)}
          />
        ))}
      </div>

      {/* 花束列表 */}
      <div className="mt-8 px-5">
        <Reveal delay={140}>
          <div className="text-center">
            <p className="eyebrow">Signature Collection</p>
            <h2 className="mt-2 font-serif-cn text-[26px] font-normal text-ink">{sectionTitle}</h2>
            <div className="mx-auto mt-4 h-px w-9 bg-gold" />
          </div>
        </Reveal>
        <div className="mt-7 space-y-4">
          {loading ? (
            <p className="py-10 text-center text-[12px] text-stone">加载中…</p>
          ) : (
            visible.map((f, i) => (
              <Reveal key={f.id} delay={i * 140}>
                <ProductCard p={f} onOpen={() => nav(`/product/${f.id}`)} onAdd={onAdd} />
              </Reveal>
            ))
          )}
          {!loading && visible.length === 0 && (
            <p className="py-10 text-center text-[12px] text-stone">没有找到匹配的花束</p>
          )}
        </div>
      </div>
    </div>
  )
}

function CatChip({ label, count, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`press flex shrink-0 items-baseline gap-1 rounded-pill border px-4 py-2 text-[12px] tracking-[1px] transition-colors ${
        active
          ? 'border-gold bg-gold text-[#FAF8F5]'
          : 'border-line bg-white text-ink'
      }`}
    >
      <span>{label}</span>
      {typeof count === 'number' && (
        <span className={`text-[9px] ${active ? 'text-[#FAF8F5]/70' : 'text-sub/70'}`}>{count}</span>
      )}
    </button>
  )
}
