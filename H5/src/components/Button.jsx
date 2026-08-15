import React from 'react'

// 按钮（Maison 规范 §5）：
// primary  = 香槟金实底 + 象牙白字（或墨黑实底）
// secondary = 白底 + 0.5px 墨黑描边
// subtle   = 砂色底 + 深古铜字
// 圆角 2px，字间距 1px，无投影
export function Button({
  children,
  variant = 'primary',
  full = false,
  className = '',
  ...rest
}) {
  const base =
    'press inline-flex items-center justify-center h-[42px] rounded-btn text-[14px] font-medium tracking-wide transition disabled:opacity-50 disabled:pointer-events-none'
  const styles =
    variant === 'primary'
      ? 'bg-dark text-[#FAF8F5]'
      : variant === 'subtle'
        ? 'bg-sand text-gold-dark'
        : 'bg-white text-ink border border-ink'
  return (
    <button
      className={`${base} ${styles} ${full ? 'w-full' : ''} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
