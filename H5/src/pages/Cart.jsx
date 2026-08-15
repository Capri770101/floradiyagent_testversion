import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Placeholder } from '../components/Placeholder'
import { IconCheck } from '../components/icons'
import { TopBar } from '../components/TopBar'
import { getCart, updateCart, removeCart, createOrder } from '../api/shop'
import { getUserId } from '../api/chat'
import { imgColor } from '../utils/color'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'

// 10 购物车
export default function Cart() {
  const nav = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

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
    const updated = await updateCart(it.item_id, { selected: !it.selected })
    setItems((list) => list.map((x) => (x.item_id === it.item_id ? updated : x)))
  }

  const changeQty = async (it, delta) => {
    const qty = Math.max(1, it.qty + delta)
    const updated = await updateCart(it.item_id, { qty })
    setItems((list) => list.map((x) => (x.item_id === it.item_id ? updated : x)))
  }

  const onRemove = async (it) => {
    await removeCart(it.item_id)
    setItems((list) => list.filter((x) => x.item_id !== it.item_id))
  }

  const total = items
    .filter((it) => it.selected)
    .reduce((s, it) => s + it.price * it.qty, 0)

  const onCheckout = async () => {
    const checked = items.filter((it) => it.selected)
    if (checked.length === 0) {
      alert('请先选择要结算的商品')
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
      alert('下单失败：' + e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar
        title="购物车"
        right={<span className="text-[11px] text-sub">{loading ? '加载中…' : `${items.length} 件`}</span>}
      />
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-3 p-4">
          {items.map((it) => (
            <div
              key={it.item_id}
              className="flex items-center gap-3 rounded-card bg-white p-3 border border-line"
            >
              <button
                onClick={() => toggle(it)}
                className={`flex h-[18px] w-[18px] items-center justify-center rounded-[2px] ${
                  it.selected ? 'bg-pink text-white' : 'border border-sub text-transparent'
                }`}
                aria-label="选择"
              >
                {it.selected && <IconCheck width={12} height={12} />}
              </button>
              <SmartImage
                src={itemImagePath('plans', it.plan_id)}
                color={imgColor(it.plan_id)}
                className="h-[62px] w-[62px] rounded-[4px]"
              />
              <div className="flex-1">
                <p className="text-[11px] text-sub">{it.shop || '精选花店'}</p>
                <p className="text-[13px] font-medium text-ink">{it.name}</p>
                <p className="mt-1 text-[12px] font-medium text-pink">¥{it.price}</p>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-ink">
                <button onClick={() => changeQty(it, -1)} aria-label="减少">
                  −
                </button>
                <span>{it.qty}</span>
                <button className="text-pink" onClick={() => changeQty(it, 1)} aria-label="增加">
                  ＋
                </button>
              </div>
              <button
                onClick={() => onRemove(it)}
                className="ml-1 text-[11px] text-sub"
                aria-label="删除"
              >
                删除
              </button>
            </div>
          ))}
          {!loading && items.length === 0 && (
            <p className="py-10 text-center text-[12px] text-sub">购物车还是空的，去逛逛吧～</p>
          )}
        </div>
        <div className="h-4" />
      </div>
      <div className="flex shrink-0 items-center justify-between border-t border-line bg-white px-6 py-4">
        <div>
          <span className="text-[12px] text-ink">合计</span>
          <span className="ml-2 text-[18px] font-medium text-pink">¥{total}</span>
        </div>
        <button
          onClick={onCheckout}
          disabled={busy}
          className="press flex h-[42px] items-center justify-center rounded-btn bg-pink px-6 text-[14px] font-medium text-white disabled:opacity-60"
          style={{ width: 111 }}
        >
          去结算
        </button>
      </div>
    </div>
  )
}
