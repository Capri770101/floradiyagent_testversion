import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import QRCode from 'qrcode'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { IconCheckCircle } from '../components/icons'
import { getOrder, payOrder, publicConfig, getPaymentStatus } from '../api/shop'
import { calcPayable } from '../utils/price'
import { toast } from '../utils/toast'
import Reveal from '../components/Reveal'

const PAY_METHODS = [
  { id: 'wechat_native', name: '微信扫码支付', color: '#B5985A' },
  { id: 'alipay', name: '支付宝', color: '#cfcfcf' },
]

// 07 支付页
export default function Pay() {
  const nav = useNavigate()
  const { state } = useLocation()
  const orderId = state?.orderId
  const [sel, setSel] = useState(0)
  const [remain, setRemain] = useState(0)
  const [order, setOrder] = useState(null)
  const [shippingFee, setShippingFee] = useState(0)
  const [paying, setPaying] = useState(false)
  const [qrCode, setQrCode] = useState(null) // 微信扫码支付二维码 dataURL
  const [payResult, setPayResult] = useState(null) // 支付成功后的结果

  useEffect(() => {
    if (orderId) {
      getOrder(orderId)
        .then((o) => {
          setOrder(o)
          // 真实剩余支付秒数（后端按订单 expires_at 计算；无值则兜底 30 分钟）
          setRemain(Math.max(0, Number(o.remaining_seconds) || 30 * 60))
        })
        .catch((e) => console.error('订单加载失败', e))
    }
  }, [orderId])

  useEffect(() => {
    const t = setInterval(() => setRemain((r) => (r > 0 ? r - 1 : 0)), 1000)
    return () => clearInterval(t)
  }, [])

  // 配送费由后端运营配置下发（与 OrderConfirm 同源，红线2：单一数据源）
  useEffect(() => {
    publicConfig()
      .then((cfg) => { if (cfg.shipping_fee != null) setShippingFee(cfg.shipping_fee) })
      .catch(() => {})
  }, [])

  // 倒计时归零：订单已超时，跳回订单列表让后端懒过期生效
  useEffect(() => {
    if (order && remain === 0 && !paying && order.status !== 'canceled') {
      const t = setTimeout(() => {
        toast('支付超时，订单已自动取消', 'error')
        nav('/profile', { replace: true })
      }, 400)
      return () => clearTimeout(t)
    }
  }, [remain, order, paying, nav])

  // 微信扫码支付：轮询支付状态，支付成功后跳转订单详情
  useEffect(() => {
    if (!qrCode || !payResult) return
    let timer
    const poll = async () => {
      try {
        const st = await getPaymentStatus(orderId)
        if (st && st.paid) {
          clearInterval(timer)
          toast('支付成功！')
          nav('/orders/' + orderId, { replace: true })
        }
      } catch (e) {
        // 忽略轮询错误，继续尝试
      }
    }
    timer = setInterval(poll, 2000)
    return () => clearInterval(timer)
  }, [qrCode, payResult, orderId, nav])

  const mm = String(Math.floor(remain / 60)).padStart(2, '0')
  const ss = String(remain % 60).padStart(2, '0')
  const total = order ? calcPayable(order.total_price, order.discount, shippingFee) : 0
  const earnedPoints = total ? Math.max(1, Math.round(total)) : 0
  const first = order?.items?.[0]
  const recipient = order?.recipient

  const onPay = async () => {
    if (!orderId || paying) return
    setPaying(true)
    try {
      const result = await payOrder(orderId, PAY_METHODS[sel].id)
      // 微信扫码支付（NATIVE）：后端返回 code_url，前端渲染二维码
      if (result?.pay_params?.code_url) {
        const dataUrl = await QRCode.toDataURL(result.pay_params.code_url, { width: 220, margin: 1 })
        setQrCode(dataUrl)
        setPayResult(result)
        toast('请使用微信扫一扫完成支付')
        return
      }
      // H5 支付：后端返回 mweb_url，需要跳转到微信支付页面
      if (result?.pay_params?.mweb_url) {
        window.location.href = result.pay_params.mweb_url
        return
      }
      // 支付宝支付：后端返回 pay_url，需要跳转
      if (result?.pay_params?.pay_url) {
        window.location.href = result.pay_params.pay_url
        return
      }
      // sandbox 或其他模式：直接提示成功
      toast('支付成功！')
      nav('/orders/' + orderId, { replace: true })
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
        <p className="animate-hero text-center text-[30px] font-medium text-dark" style={{ animationDelay: '100ms' }}>
          ¥{total.toFixed(2)}
        </p>
        <p className="animate-hero mt-3 text-center text-[10px] text-sub" style={{ animationDelay: '200ms' }}>
          {remain > 0 ? `订单将在 ${mm}:${ss} 后自动取消` : '订单已超时取消'}
        </p>

        {order && (
          <>
            <div className="animate-hero mx-auto mt-4 w-fit rounded-full bg-pink/10 px-4 py-1.5 text-[11px] text-pink" style={{ animationDelay: '300ms' }}>
              支付成功返 {earnedPoints} 积分
            </div>

            <Reveal delay={80}>
              <h2 className="mt-8 px-1 text-[15px] font-medium text-dark">金额明细</h2>
            </Reveal>
            <Reveal delay={160}>
              <div className="mt-2 rounded-card bg-white p-4 text-[12px] border border-line">
                <div className="flex justify-between py-1 text-sub">
                  <span>商品金额</span>
                  <span className="text-ink">¥{Number(order.total_price || 0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-1 text-sub">
                  <span>配送费</span>
                  <span className="text-ink">¥{Number(shippingFee).toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-1 text-sub">
                  <span>优惠券</span>
                  <span className="text-ink">-¥{Number(order.discount || 0).toFixed(2)}</span>
                </div>
                <div className="mt-1 flex justify-between border-t border-line pt-2 font-medium text-dark">
                  <span>应付合计</span>
                  <span>¥{total.toFixed(2)}</span>
                </div>
              </div>
            </Reveal>
          </>
        )}

        <Reveal delay={120}>
          <h2 className="mt-7 px-1 text-[15px] font-medium text-dark">订单信息</h2>
        </Reveal>
        <Reveal delay={200}>
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
          <p className="mt-1 flex items-center gap-1.5 px-1 text-[12px] text-sub">
            <img
              src="/images/brand/logo.jpg"
              alt="跳舞兰"
              className="h-4 w-4 rounded-full border border-line bg-white object-cover"
            />
            收款方 跳舞兰
          </p>
        </Reveal>

        {/* 微信扫码支付：显示二维码 */}
        {qrCode && (
          <Reveal delay={80}>
            <div className="mt-6 flex flex-col items-center rounded-card bg-white p-5 border border-line">
              <p className="text-[13px] font-medium text-dark">微信扫一扫支付</p>
              <img src={qrCode} alt="微信支付二维码" className="mt-3 h-[220px] w-[220px]" />
              <p className="mt-2 text-[11px] text-sub">打开微信 → 扫一扫 → 完成支付</p>
              <p className="mt-1 text-[10px] text-sub">支付成功后页面将自动跳转</p>
            </div>
          </Reveal>
        )}

        <Reveal delay={160}>
          <h2 className="mt-7 px-1 text-[15px] font-medium text-dark">支付方式</h2>
        </Reveal>
        <Reveal delay={240}>
          <div className="mt-2 overflow-hidden rounded-card bg-white border border-line">
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
        </Reveal>
        <div className="h-4" />
      </div>

      <div className="shrink-0 border-t border-line bg-bg px-4 py-4">
        <Button full disabled={paying || remain === 0} onClick={onPay}>
          {remain === 0 ? '订单已取消' : `立即支付 ¥${total.toFixed(2)}`}
        </Button>
        <p className="mt-2 text-center text-[9px] text-sub">支付即表示同意《用户支付协议》</p>
      </div>
    </div>
  )
}
