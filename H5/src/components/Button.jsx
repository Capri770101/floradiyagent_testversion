import React from 'react'

// 按钮：primary（粉底白字）/ secondary（白底粉字描边），来自规范 §2.1
// 规格：高 42，圆角 21
export function Button({
  children,
  variant = 'primary',
  full = false,
  className = '',
  ...rest
}) {
  const base =
    'press inline-flex items-center justify-center h-[42px] rounded-btn text-[14px] font-medium transition disabled:opacity-50 disabled:pointer-events-none'
  const styles =
    variant === 'primary'
      ? 'bg-pink text-white'
      : 'bg-white text-pink border border-pink'
  return (
    <button
      className={`${base} ${styles} ${full ? 'w-full' : ''} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
