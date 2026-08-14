import React, { useState, useEffect } from 'react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Pill } from '../components/Pill'
import { Button } from '../components/Button'
import { IconRefresh, IconFlower } from '../components/icons'
import { normalizePlan } from '../components/DiyPlanCard'
import { createOrder, getPlan } from '../api/shop'
import { generateEffectImage, pollImageTask, API_BASE } from '../api/image'
import { getUserId } from '../api/chat'
import { toast } from '../utils/toast'
import SmartImage from '../components/SmartImage'

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

  const onConfirm = async () => {
    if (busy || !plan) return
    setBusy(true)
    try {
      const order = await createOrder(getUserId(), [
        {
          plan_id: plan.plan_id,
          name: p?.name || plan.name,
          price: p?.price ?? plan.price,
          qty: 1,
          shop: plan.merchant || 'FloraDIY 定制',
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
        <div className="relative mx-4 mt-3 h-[210px] overflow-hidden rounded-[20px] bg-line">
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
        <div className="px-6 pt-4">
          <h1 className="text-[19px] font-medium text-dark">{p.name}</h1>
          <div className="mt-2 flex flex-wrap gap-2">
            {(plan.tags || []).map((t, i) => (
              <Pill key={t} label={t} selected={i === 0} />
            ))}
          </div>
        </div>

        <div className="px-6 pt-6">
          <h2 className="text-[16px] font-medium text-dark">花材清单</h2>
          <div className="mt-3 space-y-3">
            {p.flowers.length ? (
              p.flowers.map((f, i) => (
                <div key={i} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-4 w-4 items-center justify-center text-pink">
                    <IconFlower width={16} height={16} />
                  </span>
                  <span className="text-[12px] text-ink">
                    {f.role ? `${f.role}：` : ''}
                    {f.name}
                    {f.flower_language && f.flower_language.length > 0 && (
                      <span className="text-sub">
                        （{f.flower_language.join('、')}）
                      </span>
                    )}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-[12px] text-sub">—</p>
            )}
          </div>
        </div>

        <div className="px-6 pt-7">
          <h2 className="text-[16px] font-medium text-dark">包装设计</h2>
          <p className="mt-2 text-[12px] text-sub">{p.packaging || '—'}</p>
        </div>

        {p.diySteps && (
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">DIY 操作步骤</h2>
            <p className="mt-2 whitespace-pre-line text-[12px] text-sub">
              {p.diySteps}
            </p>
          </div>
        )}
        {p.careTips && (
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">养护建议</h2>
            <p className="mt-2 whitespace-pre-line text-[12px] text-sub">
              {p.careTips}
            </p>
          </div>
        )}
        {p.meaning && (
          <div className="px-6 pt-7">
            <h2 className="text-[16px] font-medium text-dark">花语寓意</h2>
            <p className="mt-2 whitespace-pre-line text-[12px] text-sub">
              {p.meaning}
            </p>
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-line bg-bg px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[12px] text-ink">合计预算：</span>
            <span className="text-[18px] font-medium text-pink">¥{p.price}</span>
          </div>
          <Button style={{ width: 122 }} onClick={onConfirm} disabled={busy}>
            确认方案
          </Button>
        </div>
      </div>
    </div>
  )
}
