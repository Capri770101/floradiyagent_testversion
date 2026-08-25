import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getShareCard } from '../api/shop'
import { withApiUrl } from '../api/client'
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

  const hasImage = !!card.card_image_url
  const hasMsg = !!card.card_message

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
        {/* 贺卡：背景图 + CSS 文字叠加 */}
        {(hasImage || hasMsg) && (
          <Reveal delay={100}>
            <div className="card-preview relative mx-auto max-w-[320px] overflow-hidden rounded-card shadow-lg" style={{ aspectRatio: '3/4' }}>
              {hasImage && (
                <img
                  src={withApiUrl(card.card_image_url)}
                  alt="贺卡"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              )}
              {/* 纯色兜底（无图时） */}
              {!hasImage && (
                <div className="absolute inset-0 bg-gradient-to-br from-[#F5E6D3] via-[#F0D4C0] to-[#E8C4B0]" />
              )}
              {/* 文字叠加层 */}
              {hasMsg && (
                <div className="absolute inset-0 flex flex-col items-center justify-center px-8">
                  <p
                    className="font-serif-cn text-[20px] leading-[1.8] text-white"
                    style={{ textShadow: '0 2px 12px rgba(0,0,0,0.4), 0 0 40px rgba(0,0,0,0.15)' }}
                  >
                    {card.card_message}
                  </p>
                </div>
              )}
            </div>
          </Reveal>
        )}

        {/* 收礼人 */}
        {card.recipient_name && (
          <Reveal delay={200}>
            <p className="mt-6 text-center text-[12px] text-sub">
              致 {card.recipient_name}
            </p>
          </Reveal>
        )}

        {/* 时间 */}
        <Reveal delay={300}>
          <p className="mt-2 text-center text-[10px] text-sub/50">
            {card.created_at?.slice(0, 10)}
          </p>
        </Reveal>
      </div>

      {/* 底部按钮 */}
      <Reveal delay={400}>
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
