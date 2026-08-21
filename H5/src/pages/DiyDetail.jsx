import React, { useState, useEffect } from 'react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Pill } from '../components/Pill'
import { Button } from '../components/Button'
import { IconRefresh, IconFlower } from '../components/icons'
import { normalizePlan } from '../components/DiyPlanCard'
import { createOrder, getPlan } from '../api/shop'
import { recommendPlans } from '../api/recommend'
import { useRecommend } from '../hooks/useRecommend'
import { generateEffectImage, pollImageTask, API_BASE } from '../api/image'
import { getUserId } from '../api/chat'
import { isLoggedIn } from '../api/auth'
import { toast } from '../utils/toast'
import SmartImage from '../components/SmartImage'
import Reveal from '../components/Reveal'

// 03 DIY 方案详情（真实数据）
// 主路径：对话「确认方案」经路由 state 传入完整 plan（含 design 花材/包装），直接渲染；
// 兜底：刷新/直链进入时按 id 调 GET /plans/{id}（仅顶层字段，无 design 时降级显示）。
export default function DiyDetail() {
  const { id } = useParams()
  const { state } = useLocation()
  const nav = useNavigate()
  const [plan, setPlan] = useState(state?.plan || null)
  const [loading, setLoading] = useState(!state?.plan)
  const [busy, setBusy] = useState(false)
  // 生图状态：idle（未生成）| loading（生成中）| done（已出图）| error
  const [img, setImg] = useState({ status: 'idle', url: '' })

  useEffect(() => {
    if (plan || !id) {
      setLoading(false)
      return
    }
    let alive = true
    getPlan(id)
      .then((p) => alive && setPlan(p))
      .catch(() => {})
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [id, plan])

  const p = normalizePlan(plan)

  // 同风格方案（模块三）：style 就绪后按词表分组命中 /recommend/plans
  const { items: recPlans, state: recState } = useRecommend(
    () =>
      recommendPlans({ limit: 6, style: p?.style }).then((list) =>
        list.filter((it) => it.id !== plan.plan_id),
      ),
    { enabled: !!p?.style, deps: [plan?.plan_id, p?.style] },
  )
  const parseNum = (v) => {
    const n = Number(v)
    if (!Number.isNaN(n)) return n
    const m = String(v || '').match(/\d+(?:\.\d+)?/)
    return m ? Number(m[0]) : 0
  }
  const estPrice = parseNum(p?.price ?? plan?.budget_num ?? plan?.estimated_price)

  const onConfirm = async () => {
    if (busy || !plan) return
    if (!isLoggedIn()) {
      nav('/profile', { state: { from: `/diy/${id}` } })
      return
    }
    setBusy(true)
    try {
      const order = await createOrder(getUserId(), [
        {
          plan_id: plan.plan_id,
          name: p?.name || plan.name,
          price: estPrice,
          qty: 1,
          shop: plan.merchant_name || '',
        },
      ])
      nav('/order', { state: { orderId: order.order_id } })
    } catch (e) {
      toast('下单失败：' + e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const onGenerate = async () => {
    if (busy || img.status === 'loading' || !p?.effectPrompt) return
    setImg({ status: 'loading', url: '' })
    try {
      const { task_id } = await generateEffectImage(p.effectPrompt)
      const data = await pollImageTask(task_id)
      setImg({ status: 'done', url: data.result_url })
    } catch (e) {
      setImg({ status: 'idle', url: '' })
      toast('生成效果图失败：' + e.message, 'error')
    }
  }

  if (loading) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="DIY 方案详情" />
        <div className="flex-1 p-6">
          <div className="h-40 animate-pulse rounded-card bg-line" />
        </div>
      </div>
    )
  }

  if (!p) {
    return (
      <div className="flex h-full flex-col bg-bg">
        <TopBar title="DIY 方案详情" />
        <div className="flex-1 p-6 text-center text-[13px] text-sub">
          未找到该方案，请从对话中重新确认方案。
          <div className="mt-4">
            <Button onClick={() => nav('/agent')}>去对话</Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar
        title="DIY 方案详情"
        right={
          <button
            className="text-dark"
            aria-label="刷新"
            onClick={() => nav(0)}
          >
            <IconRefresh width={20} height={20} />
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto">
        {/* 顶部效果图：已生成则展示真实图，否则用占位色块；有 effect_prompt 时可一键生图 */}
        <Reveal>
        <div className="relative mx-4 mt-3 h-[210px] overflow-hidden rounded-[4px] bg-line">
          {img.status === 'done' && img.url ? (
            <img
              src={`${API_BASE}${img.url}`}
              alt={p.name}
              className="h-full w-full object-cover"
            />
          ) : (
            <SmartImage imgKey="diy_main" className="h-[210px] w-full" />
          )}

          {p.effectPrompt && img.status !== 'done' && (
            <div className="absolute inset-x-0 bottom-0 flex justify-center bg-gradient-to-t from-black/45 to-transparent p-3">
              <Button
                variant="secondary"
                onClick={onGenerate}
                disabled={img.status === 'loading'}
              >
                {img.status === 'loading' ? '生成中…' : '生成效果图'}
              </Button>
            </div>
          )}

          {img.status === 'loading' && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/20">
              <span className="h-7 w-7 animate-spin rounded-full border-2 border-white border-t-transparent" />
            </div>
          )}
        </div>
        </Reveal>
        <Reveal delay={80}>
        <div className="px-6 pt-4">
          <h1 className="text-[19px] font-medium text-dark">{p.name}</h1>
          <div className="mt-2 flex flex-wrap gap-2">
            {(plan.tags || []).map((t, i) => (
              <Pill key={t} label={t} selected={i === 0} />
            ))}
          </div>
        </div>
        </Reveal>

        <div className="px-6 pt-6">
          <Reveal>
          <h2 className="text-[16px] font-medium text-dark">花材清单</h2>
          </Reveal>
          <div className="mt-3 space-y-3">
            {p.flowers.length ? (
              p.flowers.map((f, i) => (
                <Reveal key={i} delay={i * 140}>
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-4 w-4 items-center justify-center text-pink">
                    <IconFlower width={16} height={16} />
                  </span>
                  <span className="text-[12px] text-ink">
                    {f.role ? `${f.role}：` : ''}
                    {f.name}
                    {f.qty ? (
                      <span className="ml-1 rounded-[2px] bg-sand px-1.5 py-px text-[10px] text-gold-dark">
                        {f.qty} 支
                      </span>
                    ) : null}
                    {f.unit_price ? (
                      <span className="ml-1 text-[11px] text-sub">
                        ¥{Number(f.unit_price).toFixed(2)}/支
                      </span>
                    ) : null}
                    {f.flower_language && f.flower_language.length > 0 && (
                      <span className="text-sub">
                        （{f.flower_language.join('、')}）
                      </span>
                    )}
                  </span>
                </div>
                </Reveal>
              ))
            ) : (
              <p className="text-[12px] text-sub">—</p>
            )}
          </div>
        </div>

        <Reveal>
        <div className="px-6 pt-7">
          <h2 className="text-[16px] font-medium text-dark">包装设计</h2>
          <p className="mt-2 text-[12px] text-sub">{p.packaging || '—'}</p>
        </div>
        </Reveal>

        {(p.fees || (p.budget?.items?.length && p.budget?.fees)) && (
          <Reveal>
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">费用明细</h2>
            {p.budget?.items?.length ? (
              <div className="mt-2 space-y-1.5">
                {p.budget.items.map((it, i) => (
                  <div key={i} className="flex items-start justify-between gap-2 text-[12px]">
                    <span className="min-w-0 flex-1 text-ink">
                      {it.item}
                      {it.detail ? <span className="ml-1 text-sub">{it.detail}</span> : null}
                    </span>
                    <span className="shrink-0 text-ink">¥{Number(it.amount).toFixed(2)}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between border-t border-line pt-1.5 text-[13px] font-medium">
                  <span className="text-ink">合计</span>
                  <span className="text-ink">¥{Number(p.budget.total_estimate).toFixed(2)}</span>
                </div>
              </div>
            ) : null}
            {p.fees && (
              <div className="mt-2 rounded-[4px] bg-sand/50 p-2.5 text-[11px] leading-[18px] text-sub">
                <p>· {p.fees.labor_standard || `人工费 ${p.fees.labor_fee ?? ''} 元/束`}</p>
                <p>· {p.fees.decor_standard || `装饰费 ${p.fees.decor_fee ?? ''} 元/束`}</p>
                {p.fees.note && <p className="mt-1 text-[10px]">（{p.fees.note}）</p>}
              </div>
            )}
          </div>
          </Reveal>
        )}

        {p.diySteps && (
          <Reveal>
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">DIY 操作步骤</h2>
            <p className="mt-2 whitespace-pre-line text-[12px] text-sub">
              {p.diySteps}
            </p>
          </div>
          </Reveal>
        )}
        {p.careTips && (
          <Reveal>
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">养护建议</h2>
            <p className="mt-2 whitespace-pre-line text-[12px] text-sub">
              {p.careTips}
            </p>
          </div>
          </Reveal>
        )}
        {p.meaning && (
          <Reveal>
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">花语寓意</h2>
            <p className="mt-2 whitespace-pre-line text-[12px] text-sub">
              {p.meaning}
            </p>
          </div>
          </Reveal>
        )}

        {/* 同风格方案（模块三：数据来自 /recommend/plans?style=） */}
        <div className="px-6 pt-7">
          <Reveal>
          <h2 className="text-[16px] font-medium text-dark">同风格方案</h2>
          <p className="mt-0.5 text-[10px] text-sub">与「{p.style || '本方案'}」风格相近的更多选择</p>
          </Reveal>
          <div className="mt-3 space-y-3">
            {recState === 'loading' &&
              Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="h-[180px] animate-pulse rounded-[4px] bg-line" />
              ))}
            {recState === 'error' && (
              <p className="py-4 text-center text-[11px] text-sub">推荐加载失败，请稍后重试</p>
            )}
            {recState === 'empty' && (
              <p className="py-4 text-center text-[11px] text-sub">暂无同风格方案</p>
            )}
            {recState === 'ok' &&
              recPlans.map((r, i) => (
                <Reveal key={r.id} delay={i * 140}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => nav(`/product/${r.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      nav(`/product/${r.id}`)
                    }
                  }}
                  className="flex items-center gap-3 rounded-[4px] border border-line bg-white p-3"
                >
                  <SmartImage
                    imgKey={`plan_${r.id}`}
                    className="h-[52px] w-[52px] shrink-0 rounded-[2px]"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-serif-cn text-[15px] font-normal text-ink">{r.name}</p>
                    <p className="mt-0.5 line-clamp-1 text-[11px] text-sub">{r.desc}</p>
                    <p className="mt-1 flex items-center gap-1.5 text-[11px] text-ink">
                      <span className="text-[9px] text-stone">¥</span>
                      {Number(r.price).toFixed(2)}
                      {r.style && (
                        <span className="ml-1 rounded-[2px] bg-sand px-1.5 py-px text-[9px] text-gold-dark">
                          {r.style}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                </Reveal>
              ))}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-line bg-bg px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[12px] text-ink">合计预算：</span>
            <span className="text-[18px] font-medium text-ink">¥{Number(p.price).toFixed(2)}</span>
          </div>
          <Button style={{ width: 122 }} onClick={onConfirm} disabled={busy}>
            确认方案
          </Button>
        </div>
      </div>
    </div>
  )
}