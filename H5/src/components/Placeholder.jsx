import React from 'react'
import { lighten, hashStr } from '../utils/color'
import { FLORAL_MOTIFS } from './FloralDecor'

// 图片占位：无真实素材时，渲染「柔化渐变 + 手绘花卉水印」而非平涂色块。
// 这样没图时也有「精心设计过」的观感，而非「加载失败」的空块（温柔文艺手作风）。
// 真实图片就位后（imageMap 路径）由 SmartImage 透传 <img>，本组件不介入。
export function Placeholder({
  color = '#E8BFC8',
  className = '',
  style = {},
  seed,
}) {
  const light = lighten(color, 0.24)
  const key = String(seed || color)
  const Motif = FLORAL_MOTIFS[hashStr(key) % FLORAL_MOTIFS.length]
  return (
    <div
      className={`relative overflow-hidden ${className}`}
      style={{
        background: `linear-gradient(135deg, ${light} 0%, ${color} 100%)`,
        ...style,
      }}
      aria-hidden="true"
    >
      <Motif
        className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{ width: '46%', height: '46%', opacity: 0.5, color: '#ffffff' }}
      />
    </div>
  )
}
