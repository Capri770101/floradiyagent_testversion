import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Pill } from '../components/Pill'
import { Button } from '../components/Button'
import { Placeholder } from '../components/Placeholder'
import { IconHeart, IconStar } from '../components/icons'
import { getPlan, addCart, createOrder, favoriteStatus, addFavorite, removeFavorite, getReviews } from '../api/shop'
import { getUserId } from '../api/chat'
import { isLoggedIn } from '../api/auth'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'

// 04 商品详情
export default function ProductDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [fav, setFav] = useState(false)
  const [reviews, setReviews] = useState([])

  const requireLogin = (action) => {
    if (!isLoggedIn()) {
      nav('/profile', { state: { from: `/product/${id}` } })
      return false
    }
    return true
  }

  useEffect(() => {
    let alive = true
    getPlan(id)
      .then((p) => alive && setProduct(p))
      .catch((e) => alive && console.error('商品加载失败', e))
      .finally(() => alive && setLoading(false))
    favoriteStatus(id)
      .then((f) => alive && setFav(f))
      .catch(() => {})
    getReviews(id)
      .then((r) => alive && setReviews(r))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [id])

  const toggleFav = async () => {
    if (!requireLogin()) return
    try {
      if (fav) {
        await removeFavorite(id)
        setFav(false)
      } else {
        await addFavorite(id)
        setFav(true)
      }
    } catch (e) {
      alert('收藏操作失败：' + e.message)
    }
  }

  const onAddCart = async () => {
    if (!product || busy) return
    if (!requireLogin()) return
    setBusy(true)
    try {
      await addCart(getUserId(), {
        plan_id: product.id,
        name: product.name,
        price: product.price,
        shop: product.merchant_name || '精选花店',
      })
      alert('已加入购物车')
    } catch (e) {
      alert('加入失败：' + e.message)
    } finally {
      setBusy(false)
    }
  }

  const onBuyNow = async () => {
    if (!product || busy) return
    if (!requireLogin()) return
    setBusy(true)
    try {
      const order = await createOrder(getUserId(), [
        {
          plan_id: product.id,
          name: product.name,
          price: product.price,
          qty: 1,
          shop: product.merchant_name || '精选花店',
        },
      ])
      nav('/order', { state: { orderId: order.order_id } })
    } catch (e) {
      alert('下单失败：' + e.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading || !product) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="商品详情" />
        <div className="flex-1 p-5">
          <div className="h-[270px] animate-pulse rounded-[4px] bg-line" />
          <div className="mt-4 h-6 w-1/2 animate-pulse rounded bg-line" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar
        title="商品详情"
        right={
          <button className="text-dark" aria-label="收藏" onClick={toggleFav}>
            <IconHeart
              width={20}
              height={20}
              filled={fav}
              className={fav ? 'text-pink' : 'text-dark'}
            />
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto">
        <SmartImage src={itemImagePath('plans', product.id)} color={imgColor(product.id)} className="h-[270px] w-full" />
        <div className="px-5 pt-4">
          <h1 className="text-[20px] font-medium text-dark">{product.name}</h1>
          <p className="mt-1 text-[22px] font-medium text-ink">¥{product.price}</p>
          <p className="mt-1 flex items-center gap-1 text-[11px] text-sub">
            <IconStar width={11} height={11} className="text-cream" /> {product.rating} · 月售
            {product.sold}
          </p>
        </div>
        <div className="mt-4 px-5">
          <div className="flex flex-wrap gap-2">
            {(product.tags || []).map((t, i) => (
              <Pill key={t} label={t} selected={i === 0} style={{ width: 68 }} />
            ))}
          </div>
        </div>
        <div className="mt-6 px-5">
          <h2 className="text-[16px] font-medium text-dark">商品详情</h2>
          <p className="mt-2 text-[11px] leading-relaxed text-sub" style={{ maxWidth: 330 }}>
            {product.detail}
          </p>
        </div>
        <div className="mt-6 px-5">
          <h2 className="text-[16px] font-medium text-dark">AI 推荐理由</h2>
          <div className="mt-2 rounded-[4px] bg-white p-4 border border-line">
            <p className="text-[11px] leading-relaxed text-ink">{product.aiReason}</p>
          </div>
        </div>
        <div className="mt-6 px-5 pb-6">
          <h2 className="text-[16px] font-medium text-dark">
            用户评价
            {reviews.length > 0 && <span className="ml-1 text-[11px] text-sub">（{reviews.length}）</span>}
          </h2>
          {reviews.length === 0 ? (
            <p className="mt-2 text-[11px] text-sub">暂无评价，快下单成为第一个评价的人吧</p>
          ) : (
            <div className="mt-2 space-y-2">
              {reviews.map((r) => (
                <div key={r.id} className="rounded-[4px] bg-white p-4 border border-line">
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] font-medium text-dark">{r.nickname || '匿名用户'}</span>
                    <span className="flex items-center gap-0.5 text-cream">
                      {[1, 2, 3, 4, 5].map((s) => (
                        <IconStar key={s} width={10} height={10} filled={s <= r.rating} />
                      ))}
                    </span>
                  </div>
                  {r.content && <p className="mt-2 text-[11px] leading-relaxed text-ink">{r.content}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex shrink-0 gap-3 border-t border-line bg-bg px-5 py-4">
        <Button variant="secondary" style={{ width: 88 }} onClick={onAddCart} disabled={busy}>
          加入购物车
        </Button>
        <Button style={{ width: 83 }} onClick={onBuyNow} disabled={busy}>
          立即购买
        </Button>
      </div>
    </div>
  )
}
