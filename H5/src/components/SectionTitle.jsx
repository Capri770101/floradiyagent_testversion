import React from 'react'

// 区块标题（Maison 规范 §3/§5）：
// eyebrow（金色小标签 10px/字距 3px）+ 衬线标题（Cormorant，仅 400）
// 右侧可放「更多 ›」等操作；区块间距 ≥48px 由调用方控制。
export default function SectionTitle({ title, eyebrow, action, className = '' }) {
  return (
    <div className={`flex items-end justify-between ${className}`}>
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2 className="mt-1 font-serif-cn text-[22px] font-normal leading-none text-ink">
          {title}
        </h2>
      </div>
      {action}
    </div>
  )
}
