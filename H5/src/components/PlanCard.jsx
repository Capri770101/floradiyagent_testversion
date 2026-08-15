import React from 'react'
import { PLACEHOLDER } from '../tokens'
import { Placeholder } from './Placeholder'
import SmartImage from './SmartImage'
import { Button } from './Button'

// 方案卡片（规范 §2.3 方案卡 326x275 圆角 18）
// plan: { title, lead, flowers:[string], price, desc }
export function PlanCard({
  title,
  lead,
  flowers = [],
  price,
  onAdjust,
  onConfirm,
}) {
  return (
    <div className="animate-fade-up rounded-card-lg bg-white p-4 border border-line">
      {lead && <p className="text-[12px] text-sub">{lead}</p>}
      <h3 className="mt-1 text-[18px] font-medium text-dark">{title}</h3>

      <div className="mt-3 flex gap-3">
        <SmartImage
          imgKey="agent_plan"
          className="h-[128px] w-[112px] shrink-0 rounded-[4px]"
        />
        <div className="flex-1">
          <p className="text-[12px] leading-[26px] text-ink">
            {flowers.map((f, i) => (
              <span key={i} className="block">
                {f}
              </span>
            ))}
            {flowers.length === 0 && <span className="text-sub">{descFallback}</span>}
          </p>
        </div>
      </div>

      {price != null && (
        <p className="mt-3 text-[18px] font-medium text-pink">{price}</p>
      )}

      <div className="mt-3 flex gap-3">
        {onAdjust && (
          <Button variant="secondary" className="flex-1" onClick={onAdjust}>
            调整方案
          </Button>
        )}
        {onConfirm && (
          <Button variant="primary" className="flex-1" onClick={onConfirm}>
            确认方案
          </Button>
        )}
      </div>
    </div>
  )
}

const descFallback = '（方案详情见下方说明）'
