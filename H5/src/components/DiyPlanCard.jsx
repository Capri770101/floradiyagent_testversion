import React, { useState, useEffect } from 'react'
import { Placeholder } from './Placeholder'
import { Button } from './Button'
import { IconFlower } from './icons'
import { PLACEHOLDER } from '../tokens'
import SmartImage from './SmartImage'
import { getImageTask, withApiUrl } from '../api/chat'

const STYLE_CHOICES = ['北欧', '浪漫', '自然', '复古', '治愈', '简约', '奢华']

// 花材列表归一化：LLM 可能给数组（{name, role, ...}）或字符串（"洋桔梗、郁金香"）
function toFlowerList(v) {
  if (!v) return []
  if (Array.isArray(v)) return v
  return String(v)
    .split(/[、，,;；/\s]+/)
    .filter(Boolean)
    .map((name) => ({ name }))
}

// 把后端返回的 DIY 方案（design 嵌套 / 顶层混合）归一化为前端稳定字段，
// 避免 LLM 输出结构漂移导致卡片渲染错位。
export function normalizePlan(plan) {
  if (!plan) return null
  const d = plan.design || {}
  const flowers = [
    ...toFlowerList(d.main_flowers ?? plan.main_flowers),
    ...toFlowerList(d.fillers ?? plan.fillers),
    ...toFlowerList(d.foliage ?? plan.foliage),
  ]
  const toList = (v) => {
    if (!v) return []
    if (Array.isArray(v)) return v
    return String(v).split(/[、，,;；/\s]+/).filter(Boolean)
  }
  return {
    plan_id: plan.plan_id,
    name: plan.name || '我的花艺方案',
    style: plan.style,
    recipient: plan.recipient,
    occasion: plan.occasion,
    price: plan.estimated_price ?? plan.price,
    meaning: d.meaning ?? plan.meaning,
    packaging: d.packaging ?? plan.packaging,
    colorScheme: toList(d.color_scheme ?? plan.color_scheme),
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

export default function DiyPlanCard({ plan, onConfirm, onAdjust, onEdit, img }) {
  const [open, setOpen] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [budget, setBudget] = useState('')
  const [style, setStyle] = useState('')
  const [addFlower, setAddFlower] = useState('')
  const [removed, setRemoved] = useState([])
  const p = normalizePlan(plan)
  const [imgState, setImgState] = useState({ status: 'none', url: null })
  if (!p) return null

  // 效果图状态随 img prop 变化（生图在方案卡之后才完成，prop 是异步挂上的）：
  // result_url → 直接渲染；仅 task_id → 每 2s 轮询 /tasks 直至 done/failed。
  useEffect(() => {
    if (img?.result_url) {
      setImgState({ status: 'done', url: withApiUrl(img.result_url) })
      return
    }
    if (!img?.task_id) {
      setImgState({ status: 'none', url: null })
      return
    }
    setImgState({ status: 'pending', url: null })
    let alive = true
    const poll = async () => {
      try {
        const r = await getImageTask(img.task_id)
        if (!alive) return
        if (r.status === 'done') {
          setImgState({ status: 'done', url: withApiUrl(r.result_url) })
        } else if (r.status === 'failed') {
          setImgState({ status: 'failed', url: null })
        } else {
          setTimeout(poll, 2000)
        }
      } catch (e) {
        if (alive) setImgState({ status: 'failed', url: null })
      }
    }
    poll()
    return () => {
      alive = false
    }
  }, [img?.task_id, img?.result_url])

  return (
    <div className="animate-fade-up mt-2 overflow-hidden rounded-card-lg bg-white shadow-card">
      {/* 头部：方案名 + 价格，点击展开/收起 */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        aria-expanded={open}
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
        <div className="border-t border-line px-4 pb-4 pt-3">
          {/* 效果图状态提示：生图完成后的图片渲染在下方「方案效果图」占位符位置，
              这里只保留进行中 / 失败的状态文案，避免出现两处图片 */}
          {imgState.status === 'pending' && (
            <div className="mb-2">
              <div className="h-1 w-full overflow-hidden rounded-full bg-pink2">
                <div className="h-full w-1/3 animate-pulse rounded-full bg-pink" />
              </div>
              <p className="mt-1.5 text-[11px] text-sub">
                效果图生成中，约需 30 秒…
              </p>
            </div>
          )}
          {imgState.status === 'failed' && (
            <p className="mb-2 text-[11px] text-pink">
              效果图生成失败了，可以让我重新生成试试。
            </p>
          )}

          <div className="flex gap-3">
            <SmartImage
              src={imgState.status === 'done' ? imgState.url : null}
              imgKey="diy_main"
              className="h-[104px] w-[92px] shrink-0 rounded-[14px]"
              alt="方案效果图"
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
            <span className="whitespace-pre-line">
              {Array.isArray(p.diySteps) ? p.diySteps.join('\n') : p.diySteps || '—'}
            </span>
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
            {!editMode && onAdjust && (
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => setEditMode(true)}
              >
                调整方案
              </Button>
            )}
            {!editMode && onConfirm && (
              <Button variant="primary" className="flex-1" onClick={onConfirm}>
                确认方案
              </Button>
            )}
            {editMode && (
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => {
                  setEditMode(false)
                  setRemoved([])
                  setAddFlower('')
                  setBudget('')
                  setStyle('')
                }}
              >
                取消
              </Button>
            )}
            {editMode && (
              <Button
                variant="primary"
                className="flex-1"
                disabled={!budget && !style && !addFlower && !removed.length}
                onClick={() => {
                  const parts = []
                  if (budget) parts.push(`预算改为 ${budget} 元`)
                  if (style) parts.push(`风格换成 ${style}`)
                  if (removed.length) parts.push(`去掉 ${removed.join('、')}`)
                  if (addFlower.trim())
                    parts.push(`加上 ${addFlower.trim().replace(/[、，,;；/\s]+/g, '、')}`)
                  setEditMode(false)
                  onAdjust?.(`调整方案：${parts.join('，')}`)
                }}
              >
                提交调整
              </Button>
            )}
          </div>

          {/* 内联调整面板：预算 / 风格 / 花材增删，直接改方案不走打字 */}
          {editMode && (
            <div className="mt-3 rounded-[12px] bg-bg p-3">
              <div className="flex items-center gap-2">
                <span className="shrink-0 text-[12px] text-sub">预算</span>
                <input
                  value={budget}
                  onChange={(e) => setBudget(e.target.value.replace(/\D/g, ''))}
                  placeholder={p.price != null ? `当前 ¥${p.price}` : '输入预算'}
                  inputMode="numeric"
                  className="w-24 rounded-[8px] border border-line bg-white px-2 py-1.5 text-[12px] text-ink outline-none placeholder:text-sub"
                />
                <span className="text-[12px] text-sub">元</span>
              </div>

              <div className="mt-2.5">
                <p className="text-[12px] text-sub">风格</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {STYLE_CHOICES.map((s) => (
                    <button
                      key={s}
                      onClick={() => setStyle(style === s ? '' : s)}
                      className={`rounded-full border px-2.5 py-1 text-[11px] ${
                        style === s
                          ? 'border-pink bg-pink text-white'
                          : 'border-line bg-white text-ink'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-2.5">
                <p className="text-[12px] text-sub">花材</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {p.flowers.map((f, i) => (
                    <span
                      key={i}
                      className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] ${
                        removed.includes(f.name)
                          ? 'border-line text-sub line-through'
                          : 'border-line bg-white text-ink'
                      }`}
                    >
                      {f.name}
                      <button
                        onClick={() =>
                          setRemoved((r) =>
                            r.includes(f.name)
                              ? r.filter((x) => x !== f.name)
                              : [...r, f.name]
                          )
                        }
                        className="text-sub"
                        aria-label={`移除 ${f.name}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <input
                  value={addFlower}
                  onChange={(e) => setAddFlower(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && setAddFlower('')}
                  placeholder="添加花材，如：洋桔梗、郁金香"
                  className="mt-1.5 w-full rounded-[8px] border border-line bg-white px-2 py-1.5 text-[12px] text-ink outline-none placeholder:text-sub"
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
