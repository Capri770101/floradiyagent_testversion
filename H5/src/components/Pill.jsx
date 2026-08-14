import React from 'react'

// 标签 pill：高 30，圆角 15，字号 11（规范 §2.2）
// 选中：底 pink2 + 字 pink；未选：底白 + 字 sub
export function Pill({ label, selected = false, onClick, style = {} }) {
  return (
    <button
      onClick={onClick}
      style={style}
      className={`press h-[30px] rounded-pill px-3 text-[11px] whitespace-nowrap transition ${
        selected ? 'bg-pink-2 text-pink' : 'bg-white text-sub'
      }`}
    >
      {label}
    </button>
  )
}
