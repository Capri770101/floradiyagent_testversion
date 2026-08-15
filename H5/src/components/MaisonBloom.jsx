import React from 'react'

// Maison 极简金线花卉插画（参考稿 hero-art / 产品卡占位）：
// 香槟金细线 + 酒红花蕊 + 深古铜花茎，仅描边不填色（规范 §8.1）
export default function MaisonBloom({ size = 150, className = '', variant = 'rose' }) {
  const common = { width: size, height: size, viewBox: '0 0 150 170', fill: 'none' }
  if (variant === 'tulip') {
    return (
      <svg {...common} className={className}>
        <path d="M75 60 C 58 48 50 30 60 18 C 78 28 82 46 75 60Z" fill="#E8E4DD" stroke="#B5985A" strokeWidth="0.6" />
        <path d="M75 54 C 92 42 100 24 90 12 C 72 22 68 40 75 54Z" fill="#F0EBE3" stroke="#B5985A" strokeWidth="0.6" />
        <circle cx="75" cy="18" r="10" fill="none" stroke="#722F37" strokeWidth="0.8" />
        <circle cx="75" cy="18" r="4" fill="#B5985A" />
        <line x1="75" y1="60" x2="75" y2="140" stroke="#6B5630" strokeWidth="0.7" />
        <path d="M75 100 C 60 108 50 118 46 132 M75 100 C 90 108 100 118 104 132" stroke="#6B5630" strokeWidth="0.5" />
      </svg>
    )
  }
  if (variant === 'peony') {
    return (
      <svg {...common} className={className}>
        <circle cx="75" cy="42" r="26" fill="none" stroke="#B5985A" strokeWidth="0.8" />
        <circle cx="75" cy="42" r="14" fill="#FAF8F5" stroke="#722F37" strokeWidth="0.6" />
        <circle cx="75" cy="42" r="4" fill="#B5985A" />
        <path d="M75 42 L58 32 M75 42 L92 32 M75 42 L75 16 M75 42 L58 52 M75 42 L92 52" stroke="#B5985A" strokeWidth="0.5" />
        <line x1="75" y1="68" x2="62" y2="140" stroke="#6B5630" strokeWidth="0.6" />
        <line x1="75" y1="68" x2="88" y2="140" stroke="#6B5630" strokeWidth="0.6" />
      </svg>
    )
  }
  // 默认 rose（参考稿 hero 主视觉）
  return (
    <svg {...common} className={className}>
      <line x1="75" y1="90" x2="75" y2="150" stroke="#B5985A" strokeWidth="0.8" />
      <path d="M75 90 C 55 75 48 52 62 38 C 82 50 86 72 75 90Z" fill="#E8E4DD" stroke="#B5985A" strokeWidth="0.6" />
      <path d="M75 82 C 95 67 102 44 88 30 C 68 42 64 64 75 82Z" fill="#F0EBE3" stroke="#B5985A" strokeWidth="0.6" />
      <circle cx="75" cy="30" r="20" fill="none" stroke="#722F37" strokeWidth="0.8" />
      <circle cx="75" cy="30" r="10" fill="#FAF8F5" stroke="#B5985A" strokeWidth="0.6" />
      <circle cx="75" cy="30" r="3" fill="#B5985A" />
      <path d="M75 30 L62 22 M75 30 L88 22 M75 30 L62 38 M75 30 L88 38 M75 30 L75 12" stroke="#B5985A" strokeWidth="0.5" />
    </svg>
  )
}
