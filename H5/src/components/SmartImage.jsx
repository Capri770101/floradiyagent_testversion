import React, { useState } from 'react'
import { Placeholder } from './Placeholder'
import { imageMap } from '../assets/imageMap'

// 智能图片：有真实图片就显示图片，没有（文件还没放进去）就回退到色块占位。
// 这样「替换图片」= 把图片按 imageMap 里的 path 放进 H5/public/images/...，前端零改动。
export default function SmartImage({
  imgKey,
  src,
  color,
  className = '',
  style = {},
  alt = '',
}) {
  const meta = imgKey ? imageMap[imgKey] : null
  const resolved = src || meta?.path || null
  const fallback = color || meta?.color || '#E8BFC8'
  const [failed, setFailed] = useState(!resolved)

  if (failed || !resolved) {
    return (
      <Placeholder
        color={fallback}
        seed={src || meta?.path || imgKey || fallback}
        className={className}
        style={style}
      />
    )
  }
  return (
    <img
      src={resolved}
      alt={alt || meta?.alt || ''}
      className={className}
      style={style}
      onError={() => setFailed(true)}
    />
  )
}
