import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { IconCheckCircle } from '../components/icons'
import { getOrder, payOrder } from '../api/shop'
import { calcPayable } from '../utils/price'
import { toast } from '../utils/toast'

const PAY_METHODS = [
  { id: 'wechat', name: '微信支付', color: '#A7C5AE' },
  { id: 'alipay', name: '支付宝', color: '#cfcfcf' },
  { id: 'union', name: '银联云闪付', color: '#cfcfcf' },
  { id: 'huabei', name: '花呗', color: '#cfcfcf' },
]

// 07 支付页
export default function Pay() {
  const nav = useNavigate()
  const { state } = useLocation()
  const orderId = state?.orderId
  const [sel, setSel] = useState(0)
  const [remain, setRemain] = useState(29 * 60 + 52)
  const [order, setOrder] = useState(null)
  const [paying, setPaying] = useState(false)

  useEffect(() => {
    if (orderId) {
      getOrder(orderId).then(setOrder).catch((e) => console.error('订单加载失败', e))
    }
  }, [orderId])

  useEffect(() => {
    const t = setInterval(() => setRemain((r) => (r > 0 ? r - 1 : 0)), 1000)
    return () => clearInterval(t)
  }, [])

  const mm = String(Math.floor(remain / 60)).padStart(2, '0')
  const ss = String(remain % 60).padStart(2, '0')
  const total = order ? calcPayable(order.total_price) : 0
  const first = order?.items?.[0]
  const recipient = order?.recipient

  const onPay = async () => {
    if (!orderId || paying) return
    setPaying(true)
    try {
      await payOrder(orderId, PAY_METHODS[sel].id)
      toast('支付成功！')
      nav('/profile')
    } catch (e) {
      toast('支付失败：' + e.message, 'error')
    } finally {
      setPaying(false)
    }
  }

  if (!orderId) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="支付订单" />
        <div className="flex-1 p-6 text-center text-[13px] text-sub">
          没有待支付的订单。
          <div className="mt-4">
            <Button onClick={() => nav('/')}>去逛逛</Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="支付订单" />
      <div className="flex-1 overflow-y-auto px-4 pt-6">
        <p className="text-center text-[30px] font-medium text-dark">¥{total.toFixed(2)}</p>
        <p className="mt-3 text-center text-[10px] text-sub">
          订单将在 {mm}:{ss} 后自动取消
        </p>

        <h2 className="mt-8 px-1 text-[15px] font-medium text-dark">订单信息</h2>
        <p className="mt-2 px-1 text-[12px] text-sub">
          {first?.name || '花束'}
          {first?.shop ? ` · ${first.shop}` : ''}
        </p>
        {recipient?.name && (
          <p className="mt-1 px-1 text-[12px] text-sub">
            {recipient.name}
            {recipient.phone ? ` · ${recipient.phone}` : ''}
            {recipient.address ? ` · ${recipient.address}` : ''}
          </p>
        )}
        <p className="mt-1 px-1 text-[12px] text-sub">收款方 FloraDIY</p>

        <h2 className="mt-7 px-1 text-[15px] font-medium text-dark">支付方式</h2>
        <div className="mt-2 overflow-hidden rounded-card bg-white shadow-card">
          {PAY_METHODS.map((m, i) => (
            <button
              key={m.id}
              onClick={() => setSel(i)}
              className={`flex w-full items-center justify-between px-4 py-3.5 ${
                i < PAY_METHODS.length - 1 ? 'border-b border-line' : ''
              }`}
            >
              <span className="flex items-center gap-2 text-[13px] text-ink">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: i === 0 ? m.color : '#cfcfcf' }}
                />
                {m.name}
              </span>
              <span className={sel === i ? 'text-pink' : 'text-sub'}>
                {sel === i ? (
                  <IconCheckCircle width={18} height={18} />
                ) : (
                  <span className="block h-4 w-4 rounded-full border border-sub" />
                )}
              </span>
            </button>
          ))}
        </div>
        <div className="h-4" />
      </div>

      <div className="shrink-0 border-t border-line bg-bg px-4 py-4">
        <Button full disabled={paying} onClick={onPay}>
          立即支付 ¥{total.toFixed(2)}
        </Button>
        <p className="mt-2 text-center text-[9px] text-sub">支付即表示同意《用户支付协议》</p>
      </div>
    </div>
  )
}
