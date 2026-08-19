import React, { useEffect, useRef, useState } from 'react'

// 滚动渐入上浮（Scroll Reveal）：元素进入视口时执行 fade-up 动画。
// 用 IntersectionObserver 实现，只在真正滚动到该处时才触发，而非页面加载即播。
// - once：触发一次后保持显示（默认 false：离开视口后复位，上下滚动可反复播放）
// - delay：入场延迟（ms），用于多个相邻块做轻微交错
// - className：透传给容器的额外类名
export default function Reveal({ children, once = false, delay = 0, className = '', as: Tag = 'div' }) {
  const ref = useRef(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true)
            if (once) io.unobserve(entry.target)
          } else if (!once) {
            setVisible(false)
          }
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [once])

  return (
    <Tag
      ref={ref}
      className={`${className} ${visible ? 'reveal-in' : 'reveal-init'}`}
      style={delay ? { animationDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Tag>
  )
}