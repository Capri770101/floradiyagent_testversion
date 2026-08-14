import React, { useState } from 'react'
import { Placeholder } from './Placeholder'
import { Button } from './Button'
import { IconFlower } from './icons'
import { PLACEHOLDER } from '../tokens'
import SmartImage from './SmartImage'

// 把后端返回的 DIY 方案（design 嵌套 / 顶层混合）归一化为前端稳定字段，
// 避免 LLM 输出结构漂移导致卡片渲染错位。
export function normalizePlan(plan) {
  if (!plan) return null
  const d = plan.design || {}
  const flowers = [
    ...(d.main_flowers || plan.main_flowers || []),
    ...(d.fillers || plan.fillers || []),
    ...(d.foliage || plan.foliage || []),
  ]
  return {
    plan_id: plan.plan_id,
    name: plan.name || '我的花艺方案',
    style: plan.style,
    recipient: plan.recipient,
    occasion: plan.occasion,
    price: plan.estimated_price ?? plan.price,
    meaning: d.meaning ?? plan.meaning,
    packaging: d.packaging ?? plan.packaging,
    colorScheme: d.color_scheme ?? plan.color_scheme,
    diySteps: plan.diy_steps ?? d.diy_steps,
    careTips: plan.care_tips ?? d.care_tips,
    cardMessage: plan.card_message ?? d.card_message,
    budget: plan.budget_breakdown ?? d.budget_breakdown,
    flowers,
    merchant: plan.merchant,
    effectPrompt: plan.effect_prompt ?? d.effect_prompt,
  }
}

function Section({ title, children }) {
  return (
    <div className="mt-3">
      <p className="text-[12px] font-medium text-dark">{title}</p>
      <div className="mt-1 text-[12px] leading-[22px] text-ink">{children}</div>
    </div>
  )
}

function Chevron({ open }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}
    >
      <path d="M6 9l6 6 6-6" stroke="#999999" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function DiyPlanCard({ plan, onConfirm, onAdjust }) {
  const [open, setOpen] = useState(true)
  const p = normalizePlan(plan)
  if (!p) return null

  return (
    <div className="animate-fade-up mt-2 overflow-hidden rounded-card-lg bg-white shadow-card">
      {/* 头部：点击展开/收起 */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-pink text-white">
          <IconFlower width={16} height={16} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-medium text-dark">{p.name}</p>
          <p className="text-[11px] text-sub">
            {p.style ? `${p.style} · ` : ''}
            {p.recipient ? `送给${p.recipient}` : 'DIY 花艺方案'}
          </p>
        </div>
        {p.price != null && (
          <span className="text-[16px] font-medium text-pink">¥{p.price}</span>
        )}
        <Chevron open={open} />
      </button>

      {open && (
        <div className="border-t border-line px-4 pb-4 pt-1">
          <div className="flex gap-3">
            <SmartImage
              imgKey="diy_main"
              className="h-[104px] w-[92px] shrink-0 rounded-[14px]"
            />
            <div className="flex-1">
              <Section title="花卉组成">
                {p.flowers.length ? (
                  <ul className="space-y-1">
                    {p.flowers.map((f, i) => (
                      <li key={i}>
                        <span className="text-[11px] text-sub">
                          {f.role || '花材'}：
                        </span>
                        <span className="text-ink">{f.name}</span>
                        {f.flower_language && f.flower_language.length > 0 && (
                          <span className="ml-1 text-[11px] text-sub">
                            （{f.flower_language.join('、')}）
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-sub">—</span>
                )}
                {p.colorScheme && p.colorScheme.length > 0 && (
                  <div className="mt-2 flex items-center gap-1.5">
                    {p.colorScheme.map((c, i) => (
                      <span
                        key={i}
                        className="h-3.5 w-3.5 rounded-full border border-line"
                        style={{ backgroundColor: c }}
                      />
                    ))}
                  </div>
                )}
              </Section>
            </div>
          </div>

          <Section title="花语寓意">
            <span className="whitespace-pre-line">{p.meaning || '—'}</span>
          </Section>

          <Section title="包装形式">
            <span>{p.packaging || '—'}</span>
          </Section>

          <Section title="DIY 操作步骤">
            <span className="whitespace-pre-line">{p.diySteps || '—'}</span>
          </Section>

          <Section title="养护建议">
            <span className="whitespace-pre-line">{p.careTips || '—'}</span>
          </Section>

          {p.budget && p.budget.length > 0 && (
            <Section title="预算明细">
              <ul className="space-y-0.5">
                {p.budget.map((b, i) => (
                  <li key={i} className="flex justify-between text-[11px]">
                    <span className="text-sub">
                      {b.item}：{b.detail}
                    </span>
                    <span className="text-ink">¥{b.amount}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {p.cardMessage && (
            <Section title="贺卡寄语">
              <span className="text-sub">{p.cardMessage}</span>
            </Section>
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
      )}
    </div>
  )
}
