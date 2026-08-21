import React, { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { IconHeart } from '../components/icons'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import { planImage } from '../assets/imageMap'
import { listFavorites, removeFavorite } from '../api/shop'
import { toast } from '../utils/toast'

// 10 我的收藏：收藏方案列表（新→旧），支持关键词筛选，可取消收藏 / 跳转详情
export default function Favorites() {
  const nav = useNavigate()
  const [favorites, setFavorites] = useState([])
  const [kw, setKw] = useState('')
  const [busy, setBusy] = useState(false)

  const filtered = useMemo(() => {
    const q = kw.trim().toLowerCase()
    if (!q) return favorites
    return favorites.filter((f) =>
      [f.name, f.desc, (f.tags || []).join(' '), f.merchant_name]
        .filter(Boolean)
        .some((t) => t.toLowerCase().includes(q)),
    )
  }, [favorites, kw])

  const load = async () => {
    try {
      const data = await listFavorites()
      setFavorites(data.favorites || [])
    } catch (e) {
      toast(e.message || '收藏加载失败', 'error')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const remove = async (planId) => {
    if (busy) return
    setBusy(true)
    try {
      await removeFavorite(planId)
      toast('已取消收藏')
      await load()
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="我的收藏" />
      <div className="shrink-0 px-4 py-3">
        <input
          value={kw}
          onChange={(e) => setKw(e.target.value)}
          placeholder="搜索收藏的花束名称 / 花材 / 店铺"
          className="maison-field w-full !rounded-pill !px-4"
        />
      </div>
      <div className="flex-1 overflow-y-auto px-4 pt-1 pb-6">
        {favorites.length === 0 ? (
          <Reveal>
            <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
              还没有收藏，去首页挑一束喜欢的吧
            </p>
          </Reveal>
        ) : filtered.length === 0 ? (
          <Reveal>
            <p className="mt-6 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
              没有匹配「{kw.trim()}」的收藏
            </p>
          </Reveal>
        ) : (
          filtered.map((f, i) => (
            <Reveal key={f.plan_id} delay={i * 140}>
              <div
                className="mb-3 flex items-center gap-3 rounded-card bg-white p-3 border border-line"
              >
                <SmartImage
                  src={planImage(f)}
                  imgKey="home_rec_1"
                  className="h-[62px] w-[62px] shrink-0 rounded-[4px]"
                />
                <div className="min-w-0 flex-1" onClick={() => nav(`/product/${f.plan_id}`)}>
                  <p className="truncate text-[13px] font-medium text-dark">{f.name}</p>
                  <p className="mt-1 text-[12px] text-pink">
                    ¥{Number(f.price).toFixed(2)}
                    {f.merchant_name ? ` · ${f.merchant_name}` : ''}
                  </p>
                  <p className="mt-1 line-clamp-1 text-[11px] text-sub">{f.desc}</p>
                </div>
                <button
                  className="press shrink-0 p-1"
                  aria-label="取消收藏"
                  onClick={() => remove(f.plan_id)}
                >
                  <IconHeart width={20} height={20} className="text-pink" filled />
                </button>
              </div>
            </Reveal>
          ))
        )}
      </div>
    </div>
  )
}