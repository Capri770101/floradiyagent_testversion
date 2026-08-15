import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Pill } from '../components/Pill'
import { Button } from '../components/Button'
import { Placeholder } from '../components/Placeholder'
import { IconHeart, IconStar } from '../components/icons'
import { getPlan, addCart, createOrder, favoriteStatus, addFavorite, removeFavorite } from '../api/shop'
import { getUserId } from '../api/chat'
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

  useEffect(() => {
    let alive = true
    getPlan(id)
      .then((p) => alive && setProduct(p))
      .catch((e) => alive && console.error('商品加载失败', e))
      .finally(() => alive && setLoading(false))
    favoriteStatus(id)
      .then((f) => alive && setFav(f))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [id])

  const toggleFav = async () => {
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
          <div className="h-[270px] animate-pulse rounded-[20px] bg-line" />
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
          <p className="mt-1 text-[22px] font-medium text-pink">¥{product.price}</p>
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
          <div className="mt-2 rounded-[16px] bg-white p-4 shadow-card">
            <p className="text-[11px] leading-relaxed text-ink">{product.aiReason}</p>
          </div>
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
