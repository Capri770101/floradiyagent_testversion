import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getShareCard } from '../api/shop'
import { withApiUrl } from '../api/client'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'
import { Button } from '../components/Button'

export default function CardShare() {
  const { token } = useParams()
  const nav = useNavigate()
  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getShareCard(token)
      .then(setCard)
      .catch((e) => setError(e.message || '贺卡不存在'))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-bg">
        <p className="text-sub text-[13px]">加载中…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-bg px-8">
        <p className="text-sub text-[14px] mb-4">{error}</p>
        <Button variant="subtle" onClick={() => nav('/')}>返回首页</Button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      {/* 顶部店铺信息 */}
      <Reveal>
        <div className="pt-safe px-6 pt-4 pb-2">
          <p className="eyebrow text-center">{card.shop_name || '花艺工作室'}</p>
          <p className="mt-1 text-center text-[10px] text-sub/60">
            送上一束专属花礼
          </p>
        </div>
      </Reveal>

      {/* 主内容区 */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {/* 贺卡图片 */}
        {card.card_image_url && (
          <Reveal delay={100}>
            <div className="mx-auto max-w-[300px]">
              <SmartImage
                src={withApiUrl(card.card_image_url)}
                className="w-full rounded-card shadow-lg"
                alt="贺卡"
              />
            </div>
          </Reveal>
        )}

        {/* 寄语 */}
        {card.card_message && (
          <Reveal delay={200}>
            <div className="mx-auto mt-6 max-w-[300px] text-center">
              <div className="relative inline-block">
                <FloraDecor variant="sprig" className="absolute -left-6 -top-4 h-8 w-8 text-cream/40" />
                <p className="font-serif-cn text-[18px] leading-relaxed text-ink/80">
                  {card.card_message}
                </p>
                <FloraDecor variant="sprig" className="absolute -bottom-3 -right-6 h-8 w-8 rotate-180 text-cream/40" />
              </div>
            </div>
          </Reveal>
        )}

        {/* 收礼人 */}
        {card.recipient_name && (
          <Reveal delay={300}>
            <p className="mt-6 text-center text-[11px] text-sub">
              致 {card.recipient_name}
            </p>
          </Reveal>
        )}

        {/* 时间 */}
        <Reveal delay={400}>
          <p className="mt-2 text-center text-[10px] text-sub/50">
            {card.created_at?.slice(0, 10)}
          </p>
        </Reveal>
      </div>

      {/* 底部按钮 */}
      <Reveal delay={500}>
        <div className="px-6 pb-safe py-4">
          <Button
            variant="primary"
            className="w-full"
            onClick={() => nav('/')}
          >
            送给 TA 这束花
          </Button>
        </div>
      </Reveal>
    </div>
  )
}

/* 小装饰组件（与 DiyDetail 同源） */
function FloraDecor({ variant = 'sprig', className = '' }) {
  if (variant === 'sprig') {
    return (
      <svg viewBox="0 0 32 32" fill="none" className={className}>
        <path
          d="M16 28C16 28 8 22 8 14C8 10 12 6 16 6C20 6 24 10 24 14C24 22 16 28 16 28Z"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
        <path d="M16 14V24" stroke="currentColor" strokeWidth="1" />
      </svg>
    )
  }
  return null
}
