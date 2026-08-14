import React from 'react'
import { FloraBloom } from './FloralDecor'

// 通用区块标题（温柔文艺风）：左侧小花点缀 + 衬线标题 + 右侧可放「更多 ›」等操作。
// 用法：<SectionTitle title="今日推荐" action={<span>更多 <IconArrow/></span>} />
export default function SectionTitle({ title, action, className = '' }) {
  return (
    <div className={`flex items-center justify-between ${className}`}>
      <div className="flex items-center gap-1.5">
        <FloraBloom width={13} height={13} className="text-pink/70" />
        <h2 className="font-serif-cn text-[17px] font-medium text-dark">{title}</h2>
      </div>
      {action}
    </div>
  )
}
