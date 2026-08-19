import React, { useEffect, useRef, useState } from 'react'

// 横向无缝匀速滚动（Marquee 式）：所有卡片首尾相接，永不停止地慢慢平移。
// 用 requestAnimationFrame 累积位移，pos 对「一份宽度」取模实现无缝无限循环。
// 支持：触摸左右滑动、指针拖拽（桌面）、横向滚轮。
// - items：数据数组
// - renderItem：渲染单项（(item) => ReactNode）
// - cardWidth：单卡固定宽度（px），默认 180
// - gap：卡片间距（px），默认 12
// - speed：滚动速度（px/s），越小越慢，默认 40
export default function Carousel({
  items,
  renderItem,
  cardWidth = 180,
  gap = 12,
  speed = 40,
  className = '',
}) {
  const n = items.length
  const list = [...items, ...items] // 2 份，pos 对一份宽度取模即可无缝循环
  const one = n * (cardWidth + gap) // 一份完整数据的像素宽度
  const [pos, setPos] = useState(0) // 当前位移（px，正值向左滚）
  const posRef = useRef(0)
  const startX = useRef(0)
  const startPos = useRef(0)
  const [dragging, setDragging] = useState(false)
  const raf = useRef(null)
  // 指针事件已统一覆盖鼠标/触摸/触控笔；旧浏览器无 PointerEvent 时退回 touch 事件
  const supportsPointer = typeof window !== 'undefined' && 'PointerEvent' in window
  const touchHandled = useRef(false)
  const activePointer = useRef(null)

  // 匀速滚动主循环
  useEffect(() => {
    if (dragging || speed <= 0 || n <= 1) return
    let last = performance.now()
    const tick = (now) => {
      const dt = (now - last) / 1000
      last = now
      posRef.current = (posRef.current + speed * dt) % one
      setPos(posRef.current)
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [dragging, speed, n, one])

  if (n === 0) return null

  // 判定「点击 vs 拖拽」：只有水平位移超过阈值才算拖拽，
  // 否则放行点击事件（卡片内收藏/进详情/加购按钮仍可点）。
  const DRAG_THRESHOLD = 8

  const beginDrag = (clientX) => {
    startX.current = clientX
    startPos.current = posRef.current
  }
  const moveDrag = (clientX) => {
    const dx = clientX - startX.current
    if (!dragging && Math.abs(dx) < DRAG_THRESHOLD) return
    if (!dragging) {
      setDragging(true) // 超过阈值，正式进入拖拽模式
    }
    // 向左滑 → 内容左移 → pos 增加
    let next = startPos.current + (startX.current - clientX)
    next = ((next % one) + one) % one
    posRef.current = next
    setPos(next)
  }
  const endDrag = () => {
    setDragging(false)
    activePointer.current = null
  }

  return (
    <div
      className={`relative overflow-hidden ${className}`}
      onTouchStart={(e) => {
        if (supportsPointer) return
        touchHandled.current = true
        beginDrag(e.touches[0].clientX)
      }}
      onTouchMove={(e) => {
        if (!touchHandled.current) return
        moveDrag(e.touches[0].clientX)
      }}
      onTouchEnd={() => {
        touchHandled.current = false
        endDrag()
      }}
      onPointerDown={(e) => {
        if (e.pointerType === 'mouse' && e.button !== 0) return
        activePointer.current = e.pointerId
        beginDrag(e.clientX)
      }}
      onPointerMove={(e) => {
        if (activePointer.current !== e.pointerId) return
        moveDrag(e.clientX)
      }}
      onPointerUp={(e) => {
        if (activePointer.current === e.pointerId) endDrag()
      }}
      onPointerLeave={(e) => {
        if (activePointer.current === e.pointerId) endDrag()
      }}
      onPointerCancel={(e) => {
        if (activePointer.current === e.pointerId) endDrag()
      }}
      onWheel={(e) => {
        const next = ((posRef.current + e.deltaY + one) % one + one) % one
        posRef.current = next
        setPos(next)
      }}
    >
      <div className="flex will-change-transform" style={{ width: 'max-content' }}>
        <div
          className="flex"
          style={{
            gap: `${gap}px`,
            transform: `translateX(${-pos}px)`,
          }}
        >
          {list.map((it, i) => (
            <div key={i} className="flex shrink-0" style={{ width: cardWidth }}>
              {renderItem(it)}
            </div>
          ))}
        </div>
      </div>

      {/* 左右两端渐隐遮罩（渐入渐出） */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-bg to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-bg to-transparent" />
    </div>
  )
}