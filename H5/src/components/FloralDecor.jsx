// 手绘风花卉线描装饰（温柔文艺手作风）。
// 统一用 stroke=currentColor，描边细、圆头，靠父级 color / opacity 控制色彩与浓淡。
// 灵感：翻开一本花艺手帐——细线、留白、植物随笔。
import React from 'react'

const svgBase = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

// 五瓣花（中心小圆 + 旋转花瓣），适合做点缀 / 头像水印 / 分割符
export function FloraBloom(props) {
  return (
    <svg viewBox="0 0 100 100" {...svgBase} {...props}>
      {[0, 72, 144, 216, 288].map((a) => (
        <path
          key={a}
          d="M50 50 C41 40 43 22 50 13 C57 22 59 40 50 50Z"
          transform={`rotate(${a} 50 50)`}
        />
      ))}
      <circle cx="50" cy="50" r="5" />
    </svg>
  )
}

// 枝叶小枝（弯茎 + 三片叶），适合角落 / 卡片侧边点缀
export function FloraSprig(props) {
  return (
    <svg viewBox="0 0 100 100" {...svgBase} {...props}>
      <path d="M50 94 C50 74 42 64 46 46 C48 36 52 30 50 16" />
      <path d="M47 66 C34 64 28 56 30 47 C41 49 47 56 47 66Z" />
      <path d="M49 50 C62 48 68 40 66 31 C55 33 49 40 49 50Z" />
      <path d="M48 34 C37 33 32 26 34 19 C43 21 48 27 48 34Z" />
    </svg>
  )
}

// 单枝叶片（直茎 + 对生叶），更极简，适合细节点缀
export function FloraLeaf(props) {
  return (
    <svg viewBox="0 0 100 100" {...svgBase} {...props}>
      <path d="M50 90 C50 64 50 40 50 14" />
      <path d="M50 64 C36 60 28 50 30 38 C44 40 50 50 50 64Z" />
      <path d="M50 46 C64 42 72 32 70 20 C56 22 50 32 50 46Z" />
    </svg>
  )
}

// 角落花枝（沿左上角弯弧 + 叶片），absolute 定位贴角用
export function FloraCorner(props) {
  return (
    <svg viewBox="0 0 100 100" {...svgBase} {...props}>
      <path d="M8 8 C34 12 52 30 58 60" />
      <path d="M14 30 C4 30 0 22 4 14 C14 16 18 22 14 30Z" />
      <path d="M30 16 C30 5 38 1 47 4 C44 13 38 18 30 16Z" />
      <path d="M40 44 C32 46 28 53 31 61 C39 58 43 51 40 44Z" />
    </svg>
  )
}

// 横向花卉分割符（左右细线 + 中心小花），用于区块之间的文艺分隔
export function FloraDivider(props) {
  return (
    <svg viewBox="0 0 160 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" {...props}>
      <line x1="8" y1="8" x2="66" y2="8" />
      <path d="M80 9 C76 5 77 2 80 2 C83 2 84 5 80 9 C84 13 83 16 80 16 C77 16 76 13 80 9Z" fill="currentColor" stroke="none" />
      <line x1="94" y1="8" x2="152" y2="8" />
    </svg>
  )
}

export const FLORAL_MOTIFS = [FloraBloom, FloraSprig, FloraLeaf]
