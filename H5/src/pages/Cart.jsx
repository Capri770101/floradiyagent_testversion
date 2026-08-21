import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconCheck } from '../components/icons'
import { TopBar } from '../components/TopBar'
import { getCart, updateCart, removeCart, createOrder } from '../api/shop'
import { getUserId } from '../api/chat'
import { toast } from '../utils/toast'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import { planImage } from '../assets/imageMap'

// 购物车（Maison 风格：细描边卡片 + 衬线品名 + 墨黑吸底结算栏）
export default function Cart() {
  const nav = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  // 逐商品请求防抖/串行：同一商品并发改数量会导致互相覆盖（服务端旧值回写）
  const inFlight = useRef(new Set())

  const load = () => {
    return getCart(getUserId())
      .then(setItems)
      .catch((e) => console.error('购物车加载失败', e))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const toggle = async (it) => {
    if (inFlight.current.has(it.item_id)) return
    inFlight.current.add(it.item_id)
    try {
      const updated = await updateCart(it.item_id, { selected: !it.selected })
      setItems((list) => list.map((x) => (x.item_id === it.item_id ? updated : x)))
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      inFlight.current.delete(it.item_id)
    }
  }

  const changeQty = async (it, delta) => {
    if (inFlight.current.has(it.item_id)) return
    inFlight.current.add(it.item_id)
    try {
      const qty = Math.max(1, it.qty + delta)
      const updated = await updateCart(it.item_id, { qty })
      setItems((list) => list.map((x) => (x.item_id === it.item_id ? updated : x)))
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      inFlight.current.delete(it.item_id)
    }
  }

  const onRemove = async (it) => {
    if (inFlight.current.has(it.item_id)) return
    inFlight.current.add(it.item_id)
    try {
      await removeCart(it.item_id)
      setItems((list) => list.filter((x) => x.item_id !== it.item_id))
    } catch (e) {
      toast(e.message || '移除失败', 'error')
    } finally {
      inFlight.current.delete(it.item_id)
    }
  }

  const total = Math.round(
    items.filter((it) => it.selected).reduce((s, it) => s + it.price * it.qty, 0) * 100
  ) / 100
  const count = items.filter((it) => it.selected).reduce((s, it) => s + it.qty, 0)

  const onCheckout = async () => {
    const checked = items.filter((it) => it.selected)
    if (checked.length === 0) {
      toast('请先选择要结算的商品')
      return
    }
    setBusy(true)
    try {
      const order = await createOrder(
        getUserId(),
        checked.map((it) => ({
          plan_id: it.plan_id,
          name: it.name,
          price: it.price,
          qty: it.qty,
          shop: it.shop,
          item_id: it.item_id,
        })),
      )
      nav('/order', { state: { orderId: order.order_id } })
    } catch (e) {
      toast('下单失败：' + e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar
        title="购物袋"
        right={<span className="text-[11px] text-stone">{loading ? '加载中…' : `${count} 件`}</span>}
      />
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-3 p-4">
          {items.map((it, i) => (
            <Reveal key={it.item_id} delay={i * 140}>
              <div
                className="flex items-center gap-3 rounded-[4px] border border-line bg-white p-3"
              >
              <button
                onClick={() => toggle(it)}
                className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[2px] ${
                  it.selected ? 'bg-gold text-[#FAF8F5]' : 'border border-stone text-transparent'
                }`}
                aria-label="选择"
              >
                {it.selected && <IconCheck width={12} height={12} />}
              </button>
              <SmartImage
                src={planImage(it)}
                color={imgColor(it.plan_id)}
                className="h-[64px] w-[64px] shrink-0 rounded-[2px]"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[10px] tracking-[1px] text-stone">{it.shop || '精选花店'}</p>
                <p className="mt-0.5 truncate font-serif-cn text-[17px] font-normal text-ink">{it.name}</p>
                <p className="mt-1 text-[13px] text-ink">
                  <span className="mr-0.5 text-[10px] text-stone">¥</span>
                  {Number(it.price).toFixed(2)}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => changeQty(it, -1)}
                    aria-label="减少"
                    className="flex h-[22px] w-[22px] items-center justify-center rounded-[2px] border border-line text-[13px] text-ink"
                  >
                    −
                  </button>
                  <span className="min-w-[16px] text-center text-[12px] text-ink">{it.qty}</span>
                  <button
                    onClick={() => changeQty(it, 1)}
                    aria-label="增加"
                    className="flex h-[22px] w-[22px] items-center justify-center rounded-[2px] bg-gold text-[13px] text-[#FAF8F5]"
                  >
                    ＋
                  </button>
                </div>
                <button onClick={() => onRemove(it)} className="text-[10px] tracking-[1px] text-stone" aria-label="删除">
                  移除
                </button>
              </div>
            </div>
            </Reveal>
          ))}
          {!loading && items.length === 0 && (
            <Reveal>
              <div className="py-14 text-center">
                <p className="font-serif-cn text-[20px] font-normal text-ink">购物袋还是空的</p>
                <p className="mt-2 text-[11px] text-stone">去首页挑选一束心仪的花吧</p>
                <button
                  onClick={() => nav('/')}
                  className="press mt-5 rounded-[2px] bg-dark px-8 py-2.5 text-[12px] font-medium tracking-[1px] text-[#FAF8F5]"
                >
                  去逛逛
                </button>
              </div>
            </Reveal>
          )}
        </div>
        <div className="h-4" />
      </div>
      {/* 墨黑吸底结算栏（与首页一致） */}
      <div className="flex shrink-0 items-center justify-between bg-ink px-5 py-3.5">
        <div>
          <p className="text-[10px] tracking-[1px] text-[#FAF8F5]/70">已选 {count} 件</p>
          <p className="mt-0.5 text-[15px] text-[#FAF8F5]">
            <span className="mr-0.5 text-[10px]">¥</span>
            {Number(total).toFixed(2)}
          </p>
        </div>
        <button
          onClick={onCheckout}
          disabled={busy || count === 0}
          className="rounded-[2px] bg-gold px-7 py-2.5 text-[12px] font-medium tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
        >
          去结算
        </button>
      </div>
    </div>
  )
}
