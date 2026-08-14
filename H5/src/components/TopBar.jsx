import React from 'react'
import { useNavigate } from 'react-router-dom'
import { IconBack } from './icons'

// 顶栏：标题居中 16 Medium，左返回 ‹，右侧可选图标/文字（规范 §1.4）
export function TopBar({ title, right, onBack }) {
  const nav = useNavigate()
  return (
    <div className="relative flex h-[56px] shrink-0 items-center justify-center border-b border-line bg-bg px-4">
      {onBack !== null && (
        <button
          onClick={onBack || (() => nav(-1))}
          className="press absolute left-3 top-1/2 -translate-y-1/2 text-ink"
          aria-label="返回"
        >
          <IconBack width={26} height={26} />
        </button>
      )}
      <span className="text-[16px] font-medium text-dark">{title}</span>
      {right && <div className="absolute right-4 top-1/2 -translate-y-1/2">{right}</div>}
    </div>
  )
}
