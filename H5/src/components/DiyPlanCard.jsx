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
    difficulty: d.difficulty ?? plan.difficulty ?? null,
    estTime: d.est_time ?? plan.est_time ?? null,
    shelfLife: d.shelf_life ?? plan.shelf_life ?? null,
    suitableFor: toList(d.suitable_for ?? plan.suitable_for),
    caution: d.caution ?? plan.caution ?? null,
    moodTags: toList(d.mood_tags ?? plan.mood_tags),
    effectImageUrl: plan.effect_image_url ?? plan.result_url ?? null,
    flowers,
    fees: d.fees ?? plan.fees ?? null,
    merchant: plan.merchant,
    effectPrompt: plan.effect_prompt ?? d.effect_prompt,
  }
}

function Section({ title, children, className = 'mt-3' }) {
  return (
    <div className={className}>
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
  const steps = Array.isArray(p.diySteps)
    ? p.diySteps.filter(Boolean)
    : String(p.diySteps || '')
        .split(/\n+/)
        .map((s) => s.trim())
        .filter(Boolean)
  const [imgState, setImgState] = useState({ status: 'none', url: null })

  // 头部价格：从「约 200 元（入门 / 日常档）」这类整串中拆出数字主价与档位小字，
  // 避免右侧一整串大字影响卡片头部排版。
  const priceText = String(p.price ?? '')
  const priceNum = (priceText.match(/约?\s*¥?\s*(\d+(?:\.\d+)?)/) || [])[1] || null
  const priceTier = (priceText.match(/[（(]([^（）()]*)[）)]/) || [])[1] || null

  // 效果图状态随 img prop 变化（生图在方案卡之后才完成，prop 是异步挂上的）：
  // result_url → 直接渲染；仅 task_id → 每 2s 轮询 /tasks 直至 done/failed。
  useEffect(() => {
    if (img?.result_url) {
      setImgState({ status: 'done', url: withApiUrl(img.result_url) })
      return
    }
    // 历史方案回落：从资产库取回的方案自带 effect_image_url，直接渲染
    if (p.effectImageUrl) {
      setImgState({ status: 'done', url: withApiUrl(p.effectImageUrl) })
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

  // 防御：无方案不渲染。注意：必须在所有 hooks 之后 return（hooks 不能被条件跳过）。
  if (!p) return null

  return (
    <div className="animate-fade-up mt-2 overflow-hidden rounded-card-lg bg-white border border-line">
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
          <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-sub">
            {p.style && <span>{p.style}</span>}
            {p.occasion && (
              <span className="rounded-full border border-gold/40 bg-pink-2/70 px-1.5 py-px text-[10px] text-gold-dark">
                {p.occasion}
              </span>
            )}
            {p.recipient ? `送给${p.recipient}` : 'DIY 花艺方案'}
          </p>
        </div>
        {p.price != null && (
          <div className="shrink-0 text-right">
            {priceNum ? (
              <>
                <p className="text-[15px] font-medium leading-tight text-ink">
                  ¥{Number(priceNum).toFixed(2)}
                </p>
                {priceTier && (
                  <p className="mt-0.5 text-[10px] leading-tight text-sub">
                    {priceTier}
                  </p>
                )}
              </>
            ) : (
              <p className="text-[12px] leading-tight text-sub">{Number(p.price).toFixed(2)}</p>
            )}
          </div>
        )}
        <Chevron open={open} />
      </button>

      {open && (
        <div className="border-t border-line px-4 pb-4 pt-3">
          {/* 效果图：生成本次效果图完成后 → 全宽大图替换占位；
              生成中 → 占位 + 进度条；失败 → 提示可重试 */}
          {imgState.status === 'done' && imgState.url ? (
            <div className="overflow-hidden rounded-[4px] border border-line">
              <SmartImage
                src={imgState.url}
                imgKey="diy_main"
                className="aspect-[4/3] w-full object-cover"
                alt="方案效果图"
              />
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <SmartImage
                src={null}
                imgKey="diy_main"
                className="h-[92px] w-[92px] shrink-0 rounded-[4px]"
                alt="方案效果图占位"
              />
              {imgState.status === 'pending' && (
                <div className="flex-1">
                  <div className="h-1 w-full overflow-hidden rounded-full bg-pink-2">
                    <div className="h-full w-1/3 animate-pulse rounded-full bg-pink" />
                  </div>
                  <p className="mt-1.5 text-[11px] text-sub">
                    效果图生成中，约需 30 秒…
                  </p>
                </div>
              )}
              {imgState.status === 'failed' && (
                <p className="flex-1 text-[11px] text-pink">
                  效果图生成失败了，可以让我重新生成试试。
                </p>
              )}
            </div>
          )}

          <Section title="花卉组成">
            {p.flowers.length ? (
              <ul className="space-y-1">
                {p.flowers.map((f, i) => (
                  <li key={i}>
                    <span className="text-[11px] text-sub">
                      {f.role || '花材'}：
                    </span>
                    <span className="text-ink">{f.name}</span>
                    {f.qty ? (
                      <span className="ml-1 text-[11px] text-sub">{f.qty} 支</span>
                    ) : null}
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
                {p.moodTags.length > 0 && (
                  <span className="ml-1 text-[11px] text-gold-dark">
                    情绪 · {p.moodTags.join(' / ')}
                  </span>
                )}
              </div>
            )}
          </Section>

          {/* 花语寓意 + 包装形式 并排两列 */}
          <div className="grid grid-cols-2 gap-3">
            <Section title="花语寓意" className="mt-3">
              <span className="whitespace-pre-line">{p.meaning || '—'}</span>
            </Section>
            <Section title="包装形式" className="mt-3">
              <span>{p.packaging || '—'}</span>
            </Section>
          </div>

          {/* 制作难度 + 预计耗时 + 保鲜期 三列并排（模块二） */}
          <div className="mt-3 grid grid-cols-3 gap-3">
            <Section title="制作难度">
              <span>{p.difficulty || '—'}</span>
            </Section>
            <Section title="预计耗时">
              <span>{p.estTime != null ? `约 ${p.estTime} 分钟` : '—'}</span>
            </Section>
            <Section title="保鲜期">
              <span>{p.shelfLife || '—'}</span>
            </Section>
          </div>

          {p.suitableFor.length > 0 && (
            <Section title="适宜人群" className="mt-3">
              <div className="flex flex-wrap gap-1.5">
                {p.suitableFor.map((t, i) => (
                  <span
                    key={i}
                    className="rounded-full border border-line bg-bg px-2 py-0.5 text-[11px] text-ink"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </Section>
          )}

          <Section title="DIY 操作步骤">
            {steps.length ? (
              <ol className="space-y-1.5">
                {steps.map((s, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-[3px] flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-pink text-[10px] font-medium text-white">
                      {i + 1}
                    </span>
                    <span className="min-w-0 flex-1 text-ink">{s}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <span className="text-sub">—</span>
            )}
          </Section>

          <Section title="养护建议">
            <span className="whitespace-pre-line">{p.careTips || '—'}</span>
          </Section>

          {(p.budget?.items?.length || p.fees) && (
            <Section title="费用明细">
              {p.budget?.items?.length ? (
                <ul className="space-y-0.5">
                  {p.budget.items.map((b, i) => (
                    <li key={i} className="flex justify-between text-[11px]">
                      <span className="text-sub">
                        {b.item}：{b.detail}
                      </span>
                      <span className="text-ink">¥{Number(b.amount).toFixed(2)}</span>
                    </li>
                  ))}
                  {p.budget.total_estimate != null && (
                    <li className="flex justify-between border-t border-line pt-1 text-[12px] font-medium">
                      <span className="text-ink">合计</span>
                      <span className="text-ink">¥{Number(p.budget.total_estimate).toFixed(2)}</span>
                    </li>
                  )}
                </ul>
              ) : null}
              {p.fees && (
                <div className="mt-1.5 space-y-0.5 text-[11px] text-sub">
                  <p>· {p.fees.labor_standard || `人工费 ${p.fees.labor_fee ?? ''} 元/束`}</p>
                  <p>· {p.fees.decor_standard || `装饰费 ${p.fees.decor_fee ?? ''} 元/束`}</p>
                </div>
              )}
            </Section>
          )}

          {p.caution && (
            <div className="mt-3 rounded-[2px] border-l-2 border-burgundy/70 bg-sand/40 py-1.5 pl-2.5 pr-2">
              <p className="text-[12px] font-medium text-burgundy">禁忌提醒</p>
              <p className="mt-0.5 text-[12px] leading-[22px] text-sub">
                {p.caution}
              </p>
            </div>
          )}

          {p.cardMessage && (
            <div className="mt-3 rounded-[2px] border-l-2 border-gold bg-sand/40 py-1.5 pl-2.5 pr-2">
              <p className="text-[12px] font-medium text-dark">贺卡寄语</p>
              <p className="mt-0.5 text-[12px] leading-[22px] text-sub">
                {p.cardMessage}
              </p>
            </div>
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
            <div className="mt-3 rounded-[4px] bg-bg p-3">
              <div className="flex items-center gap-2">
                <span className="shrink-0 text-[12px] text-sub">预算</span>
                <input
                  value={budget}
                  onChange={(e) => setBudget(e.target.value.replace(/\D/g, ''))}
                  placeholder={p.price != null ? `当前 ¥${Number(p.price).toFixed(2)}` : '输入预算'}
                  inputMode="numeric"
                  className="maison-field maison-field-sm w-24"
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
                  className="mt-1.5 w-full rounded-[2px] border border-line bg-white px-2 py-1.5 text-[12px] text-ink outline-none placeholder:text-sub"
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
