import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { Pill } from '../components/Pill'
import { toast } from '../utils/toast'
import { statusMeta } from '../utils/status'
import {
  merchantStats,
  merchantOrders,
  merchantShip,
  merchantReviews,
  merchantOrderDetail,
  merchantPlans,
  merchantCreatePlan,
  merchantUpdatePlan,
  merchantTogglePlan,
  merchantDeletePlan,
  merchantBatchToggle,
  merchantUpdateShop,
  merchantUpload,
  merchantAddLogistics,
  merchantCategories,
  merchantCreateCategory,
  merchantRenameCategory,
  merchantDeleteCategory,
  merchantReplyReview,
  merchantChats,
  merchantChatMessages,
  merchantSendChatMessage,
} from '../api/shop'
import { getProfile } from '../api/auth'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'
import { IconStar, IconPin, IconClock, IconPlus, IconArrow, IconTrash, IconSearch } from '../components/icons'
import { planImage } from '../assets/imageMap'
import SmartImage from '../components/SmartImage'

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '配送中' },
  { key: 'done', label: '已完成' },
  { key: 'canceled', label: '已取消' },
]

const fmtMoney = (v) => `¥${Number(v || 0).toFixed(2)}`

// DIY 订单制作卡：花材配比 + 包装 + 步骤 + 卡片留言，商家按此备货
function DiyPlanCard({ plan }) {
  const design = plan?.design || {}
  const rows = [
    ...(design.main_flowers || []).map((f) => ({ ...f, bucket: '主花' })),
    ...(design.fillers || []).map((f) => ({ ...f, bucket: '填充' })),
    ...(design.foliage || []).map((f) => ({ ...f, bucket: '叶材' })),
  ]
  const steps = Array.isArray(plan?.diy_steps) ? plan.diy_steps : []
  return (
    <div className="mt-3 rounded-card border border-pink/30 bg-[#FDF6F3] p-4">
      <p className="eyebrow text-pink">DIY 方案制作卡</p>
      <h4 className="mt-1 font-serif-cn text-[16px] font-normal text-ink">{plan?.name}</h4>
      {plan?.requirement && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-sub">需求：{plan.requirement}</p>
      )}
      {rows.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-ink">花材配比</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {rows.map((f, i) => (
              <span
                key={i}
                className={`rounded-pill px-2.5 py-1 text-[11px] ${
                  f.bucket === '主花' ? 'bg-pink/15 text-pink' : 'bg-white text-sub border border-line'
                }`}
              >
                {f.name}
                {f.ratio ? ` ${f.ratio}` : ''}
              </span>
            ))}
          </div>
        </div>
      )}
      {design.packaging && (
        <p className="mt-2.5 text-[11px] text-sub">
          <span className="text-ink">包装：</span>
          {design.packaging}
        </p>
      )}
      {steps.length > 0 && (
        <div className="mt-2.5">
          <p className="text-[11px] font-medium text-ink">DIY 步骤</p>
          <ol className="mt-1 list-decimal pl-4 text-[11px] leading-[20px] text-sub">
            {steps.map((s, i) => (
              <li key={i}>{typeof s === 'string' ? s : s?.step || s?.text || JSON.stringify(s)}</li>
            ))}
          </ol>
        </div>
      )}
      {plan?.card_message && (
        <p className="mt-2.5 rounded-[2px] border border-line bg-white p-2.5 text-[11px] leading-relaxed text-sub">
          <span className="text-ink">卡片留言：</span>
          {plan.card_message}
        </p>
      )}
      <p className="mt-2 text-[10px] text-sub/60">方案 ID：{plan?.plan_id}</p>
    </div>
  )
}

// 订单卡：明细 + 收件信息 + 状态操作（查看 DIY 方案 / 代发货 / 物流时间线）
function OrderCard({ o, expanded, onToggle, plan, planBusy, busyId, onShip, onViewLogistics }) {
  const meta = statusMeta(o.status)
  const items = o.items || []
  const recipient = o.recipient || {}
  const shopNames = o.shop_id ? [o.shop_id] : []
  return (
    <div className="mt-3 overflow-hidden rounded-card bg-white shadow-card border border-line">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-[11px] text-sub">{o.order_id}</p>
          <p className="mt-0.5 text-[10px] text-sub/70">{o.created_at}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {o.plan_id?.startsWith('DIY_') && (
            <span className="rounded-pill bg-pink/10 px-2 py-0.5 text-[10px] text-pink">DIY</span>
          )}
          <span className={`rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
            {meta.label}
          </span>
        </div>
      </div>

      <div className="px-4 py-2">
        {items.map((it) => (
          <div key={it.plan_id} className="flex items-center gap-3 py-1.5">
            <SmartImage
              src={planImage(it)}
              imgKey="home_rec_1"
              className="h-[40px] w-[40px] shrink-0 rounded-[4px]"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] text-dark">{it.name}</p>
              <p className="text-[11px] text-sub">
                {fmtMoney(it.price)} × {it.qty}
                {it.shop ? ` · ${it.shop}` : ''}
              </p>
            </div>
          </div>
        ))}
      </div>

      {recipient.name && (
        <div className="border-t border-line bg-bg/60 px-4 py-2.5">
          <p className="text-[12px] text-ink">
            {recipient.name}
            {recipient.phone ? <span className="ml-2 text-[11px] text-sub">{recipient.phone}</span> : null}
          </p>
          {recipient.address && (
            <p className="mt-1 flex items-start gap-1 text-[11px] leading-relaxed text-sub">
              <IconPin width={12} height={12} className="mt-0.5 shrink-0" />
              {recipient.address}
            </p>
          )}
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-sub/80">
            <span>店铺：{shopNames.join(' / ') || '—'}</span>
            {o.delivery_time && (
              <span className="flex items-center gap-1">
                <IconClock width={11} height={11} />
                预约 {o.delivery_time}
              </span>
            )}
          </div>
          {o.note && (
            <p className="mt-1.5 rounded-[2px] bg-white px-2.5 py-1.5 text-[11px] text-sub border border-line">
              备注：{o.note}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">
        <p className="mr-auto font-serif-cn text-[15px] font-normal text-ink">共 {fmtMoney(o.total_price)}</p>
        <button
          onClick={() => onViewLogistics(o.order_id)}
          className="press flex items-center gap-1 text-[12px] tracking-[1px] text-gold"
        >
          查看物流
          <IconArrow width={10} height={10} />
        </button>
        {o.plan_id?.startsWith('DIY_') && (
          <button
            onClick={onToggle}
            className="press flex items-center gap-1 text-[12px] tracking-[1px] text-gold"
            disabled={planBusy && !plan}
          >
            {expanded ? '收起方案' : '查看方案'}
          </button>
        )}
        {o.status === 'paid' && (
          <Button
            className="!h-[34px] !text-[12px] !tracking-[1px]"
            disabled={busyId === o.order_id}
            onClick={() => onShip(o.order_id)}
          >
            {busyId === o.order_id ? '发货中…' : '代发货'}
          </Button>
        )}
      </div>

      {expanded && (
        <div className="border-t border-line px-4 py-3">
          {plan ? (
            <DiyPlanCard plan={plan} />
          ) : planBusy && !plan ? (
            <p className="py-2 text-center text-[11px] text-sub">方案加载中…</p>
          ) : (
            <p className="rounded-card bg-bg p-4 text-center text-[11px] text-sub">
              该订单无 DIY 方案制作卡
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// 物流管理：订单物流汇总 + 时间线 + 追加物流节点
function LogisticsTab({
  orders,
  shops,
  filterShop,
  onSelectShop,
  status,
  onStatus,
  logiExpandedId,
  onToggleExpanded,
  logiDraft,
  onDraft,
  logiBusy,
  onAddNode,
}) {
  const activeCount = orders.filter((o) => o.status === 'paid' || o.status === 'shipped').length
  return (
    <>
      <div className="mt-3 flex flex-wrap gap-1.5 px-5">
        <Pill
          label="全部店铺"
          selected={!filterShop}
          onClick={() => onSelectShop('')}
          style={{ width: 'auto', padding: '0 10px' }}
        />
        {shops.map((s) => (
          <Pill
            key={s.id}
            label={s.name}
            selected={filterShop === s.id}
            onClick={() => onSelectShop(s.id)}
            style={{ width: 'auto', padding: '0 10px', maxWidth: 132 }}
          />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 px-5">
        {STATUS_TABS.map((t) => (
          <Pill
            key={t.key}
            label={t.label}
            selected={status === t.key}
            onClick={() => onStatus(t.key)}
            style={{ width: 'auto', padding: '0 10px' }}
          />
        ))}
      </div>

      <div className="mx-5 mt-4 flex items-center justify-between rounded-card bg-white shadow-card px-4 py-3 border border-line">
        <p className="text-[11px] tracking-[0.15em] text-sub">
          进行中订单 <span className="font-serif-cn text-[15px] font-normal text-ink">{activeCount}</span> 笔
        </p>
        <p className="text-[10px] text-sub/70">配送中订单可手动追加物流节点</p>
      </div>

      {orders.length === 0 ? (
        <p className="mx-5 mt-6 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
          {status ? `暂无「${STATUS_TABS.find((t) => t.key === status)?.label || status}」订单` : '还没有订单'}
        </p>
      ) : (
        <div className="px-5">
          {orders.map((o) => {
            const meta = statusMeta(o.status)
            const logs = o.logistics || []
            const expanded = logiExpandedId === o.order_id
            return (
              <div key={o.order_id} className="mt-3 overflow-hidden rounded-card bg-white shadow-card border border-line">
                <div className="flex items-center justify-between border-b border-line px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-[11px] text-sub">{o.order_id}</p>
                    <p className="mt-0.5 text-[10px] text-sub/70">{o.created_at}</p>
                  </div>
                  <span className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                    {meta.label}
                  </span>
                </div>

                <div className="px-4 py-2">
                  {(o.items || []).map((it) => (
                    <div key={it.plan_id} className="flex items-center gap-3 py-1.5">
                      <SmartImage
                        src={planImage(it)}
                        imgKey="home_rec_1"
                        className="h-[40px] w-[40px] shrink-0 rounded-[4px]"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] text-dark">{it.name}</p>
                        <p className="text-[11px] text-sub">
                          {fmtMoney(it.price)} × {it.qty}
                          {it.shop ? ` · ${it.shop}` : ''}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="border-t border-line bg-bg/50 px-4 py-2.5">
                  {logs.length > 0 ? (
                    <p className="flex items-center gap-1.5 text-[11px] leading-relaxed text-ink">
                      <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gold" />
                      最新：{logs[0].text}
                      <span className="ml-auto shrink-0 text-[10px] text-sub/70">{logs[0].created_at}</span>
                    </p>
                  ) : (
                    <p className="text-[11px] text-sub">暂无物流记录</p>
                  )}
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">
                  <p className="mr-auto font-serif-cn text-[15px] font-normal text-ink">共 {fmtMoney(o.total_price)}</p>
                  <button
                    onClick={() => onToggleExpanded(o.order_id)}
                    className="press flex items-center gap-1 text-[12px] tracking-[1px] text-gold"
                  >
                    {expanded ? '收起' : '物流时间线'}
                    <IconArrow width={10} height={10} />
                  </button>
                </div>

                {expanded && (
                  <div className="border-t border-line px-4 py-3">
                    {logs.length === 0 ? (
                      <p className="rounded-[2px] bg-bg p-3 text-center text-[11px] text-sub">
                        暂无物流信息
                      </p>
                    ) : (
                      <div>
                        {logs.map((e, i) => (
                          <div key={e.seq} className="flex gap-3">
                            <div className="flex flex-col items-center">
                              <span className={`mt-1 h-2 w-2 rounded-full ${i === 0 ? 'bg-pink' : 'bg-line'}`} />
                              {i < logs.length - 1 && <span className="w-px flex-1 bg-line" />}
                            </div>
                            <div className="pb-3">
                              <p className={`text-[12px] ${i === 0 ? 'font-medium text-dark' : 'text-sub'}`}>
                                {e.text}
                              </p>
                              <p className="text-[10px] text-sub/70">{e.created_at}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {o.status === 'shipped' && (
                      <div className="mt-2 flex gap-2 border-t border-line pt-3">
                        <input
                          value={logiDraft[o.order_id] || ''}
                          onChange={(e) => onDraft(o.order_id, e.target.value)}
                          placeholder="如：包裹已到达广州转运中心"
                          maxLength={200}
                          className="maison-field flex-1 !h-[38px] !text-[12px]"
                        />
                        <Button
                          className="!h-[38px] !text-[12px] !tracking-[1px]"
                          disabled={logiBusy}
                          onClick={() => onAddNode(o)}
                        >
                          追加
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

// 工作台首页：今日经营 + 待办提醒 + 店铺状态 + 快捷入口 + 最近订单
function DashboardTab({ stats, orders, reviews, shops, onGoTab, onShip, busyId, onViewShop }) {
  if (!stats) return null
  const pendingShip = (orders || []).filter((o) => o.status === 'paid')
  const badReviews = (reviews || []).filter((r) => r.rating <= 3)
  const recent = (orders || []).slice(0, 3)

  const cards = [
    { label: '今日订单', value: stats.today_order_count ?? '-', hint: `累计 ${stats.order_count ?? '-'} 单` },
    { label: '今日GMV', value: `¥${Number(stats.today_gmv || 0).toFixed(0)}`, hint: `累计 ¥${Number(stats.gmv || 0).toFixed(0)}` },
    { label: '待发货', value: stats.pending_ship ?? 0, hint: 'paid 订单', accent: (stats.pending_ship || 0) > 0 },
    { label: '待付款', value: stats.pending_payment ?? 0, hint: '超时自动取消', accent: (stats.pending_payment || 0) > 0 },
  ]
  const quick = [
    { key: 'orders', label: '订单管理', sub: `${stats.pending_ship ?? 0} 单待发货` },
    { key: 'plans', label: '商品管理', sub: '上下架 / 编辑' },
    { key: 'reviews', label: '评价管理', sub: badReviews.length ? `${badReviews.length} 条中差评` : `${stats.review_count ?? 0} 条评价` },
    { key: 'shop', label: '店铺设置', sub: '资料 / 装修' },
  ]

  return (
    <div className="px-5">
      {/* 今日经营大数字卡 */}
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        {cards.map((c) => (
          <div key={c.label} className="rounded-card bg-white shadow-card p-3.5 border border-line">
            <p className="text-[10px] tracking-[0.15em] text-sub">{c.label}</p>
            <p className={`mt-1 font-serif-cn text-[22px] font-normal ${c.accent ? 'text-burgundy' : 'text-ink'}`}>
              {c.value}
            </p>
            <p className="mt-0.5 text-[10px] text-sub/70">{c.hint}</p>
          </div>
        ))}
      </div>

      {/* 待办提醒 */}
      <div className="mt-5">
        <p className="eyebrow">待办提醒</p>
        {pendingShip.length === 0 && badReviews.length === 0 ? (
          <p className="mt-2 rounded-card bg-white shadow-card p-5 text-center text-[12px] text-sub border border-line">
            暂无待办，一切正常 🎉
          </p>
        ) : (
          <div className="mt-2 space-y-2">
            {pendingShip.slice(0, 4).map((o) => (
              <div
                key={o.order_id}
                onClick={() => onGoTab('orders')}
                className="press flex w-full cursor-pointer items-center justify-between rounded-card bg-white shadow-card p-3 text-left border border-line"
              >
                <div className="min-w-0">
                  <p className="truncate text-[12px] text-ink">{o.order_id}</p>
                  <p className="mt-0.5 truncate text-[10px] text-sub">
                    {(o.items || []).map((it) => it.name).join('、')} · 共 {fmtMoney(o.total_price)}
                  </p>
                </div>
                <Button
                  className="!h-[30px] !px-4 !text-[11px] !tracking-[1px]"
                  disabled={busyId === o.order_id}
                  onClick={(e) => {
                    e.stopPropagation()
                    onShip(o.order_id)
                  }}
                >
                  {busyId === o.order_id ? '发货中…' : '去发货'}
                </Button>
              </div>
            ))}
            {badReviews.slice(0, 2).map((r) => (
              <button
                key={r.id}
                onClick={() => onGoTab('reviews')}
                className="press flex w-full items-center justify-between rounded-card bg-white shadow-card p-3 text-left border border-line"
              >
                <div className="min-w-0">
                  <p className="text-[12px] text-ink">
                    {'★'.repeat(r.rating)}
                    <span className="ml-2 text-[10px] text-sub">中差评待处理</span>
                  </p>
                  <p className="mt-0.5 truncate text-[10px] text-sub">{r.content || '（无文字评价）'}</p>
                </div>
                <IconArrow width={12} height={12} className="shrink-0 text-sub" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 快捷入口 */}
      <div className="mt-6">
        <p className="eyebrow">快捷入口</p>
        <div className="mt-2 grid grid-cols-2 gap-2.5">
          {quick.map((q) => (
            <button
              key={q.key}
              onClick={() => onGoTab(q.key)}
              className="press rounded-card bg-white shadow-card p-3.5 text-left border border-line"
            >
              <p className="text-[13px] font-medium text-ink">{q.label}</p>
              <p className="mt-1 text-[10px] text-sub">{q.sub}</p>
            </button>
          ))}
        </div>
      </div>

      {/* 店铺状态 */}
      {shops.length > 0 && (
        <div className="mt-6">
          <p className="eyebrow">我的店铺</p>
          <div className="mt-2 space-y-2">
            {shops.map((s) => (
              <div
                key={s.id || s.shop_id}
                className="flex items-center justify-between rounded-card bg-white shadow-card p-3 border border-line"
              >
                <div className="min-w-0">
                  <p className="truncate font-serif-cn text-[15px] font-normal text-ink">{s.name}</p>
                  <p className="mt-0.5 flex items-center gap-2 text-[10px] text-sub">
                    <span className="flex items-center gap-0.5">
                      <IconStar width={10} height={10} className="text-cream" /> {s.rating || '-'}
                    </span>
                    <span>月售 {s.sales ?? '-'}</span>
                  </p>
                </div>
                <button
                  onClick={() => onViewShop(s.id || s.shop_id)}
                  className="press shrink-0 text-[11px] tracking-[1px] text-gold"
                >
                  店铺设置 →
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 最近订单 */}
      {recent.length > 0 && (
        <div className="mt-6 pb-2">
          <p className="eyebrow">最近订单</p>
          <div className="mt-2 space-y-2">
            {recent.map((o) => {
              const meta = statusMeta(o.status)
              return (
                <div key={o.order_id} className="rounded-card bg-white shadow-card p-3 border border-line">
                  <div className="flex items-center justify-between">
                    <p className="truncate text-[11px] text-sub">{o.order_id}</p>
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>{meta.label}</span>
                  </div>
                  <p className="mt-1 truncate text-[12px] text-ink">
                    {(o.items || []).map((it) => it.name).join('、')}
                  </p>
                  <p className="mt-0.5 text-[11px] text-gold">{fmtMoney(o.total_price)}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// 商品管理：店铺选择 + 在售/下架列表 + 新建/编辑/上下架/删除 + 批量上下架
function ShopPlansTab({ shops, plans, onSelectShop, shopId, planBusy, onOpenForm, onEdit, onToggle, onRemove, onBatchToggle, categories, onPreviewShop }) {
  const catName = (id) => (categories.find((c) => c.id === id) || {}).name || ''
  const [batchMode, setBatchMode] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [planFilter, setPlanFilter] = useState('all') // all | on | off
  const [planKw, setPlanKw] = useState('')
  const [planCat, setPlanCat] = useState('')
  const filteredPlans = plans.filter((p) => {
    if (planFilter !== 'all' && p.shop_status !== planFilter) return false
    if (planCat && p.category_id !== planCat) return false
    if (planKw) {
      const hay = `${p.name || ''} ${p.desc || ''} ${(p.tags || []).join(' ')}`.toLowerCase()
      if (!hay.includes(planKw.toLowerCase())) return false
    }
    return true
  })
  const allSelected = filteredPlans.length > 0 && filteredPlans.every((p) => selected.has(p.plan_id))
  const toggleSelect = (id) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  if (shops.length === 0) {
    return (
      <p className="mx-5 mt-6 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
        尚未绑定任何店铺，请联系管理员在后台绑定后使用
      </p>
    )
  }
  const rowBtn =
    'press inline-flex h-[30px] items-center justify-center gap-1 rounded-[2px] border px-3.5 text-[11px] font-medium tracking-[1px] transition disabled:opacity-50 disabled:pointer-events-none'
  return (
    <>
      <div className="mt-3 flex flex-wrap gap-1.5 px-5">
        {shops.map((s) => (
          <Pill
            key={s.id || s}
            label={s.name || s}
            selected={shopId === (s.id || s)}
            onClick={() => onSelectShop(s.id || s)}
            style={{ width: 'auto', padding: '0 10px', maxWidth: 132 }}
          />
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between px-5">
        <p className="eyebrow">{shopId ? '店铺商品' : '请先选择店铺'}</p>
        <div className="flex items-center gap-3">
          {shopId && plans.length > 0 && !batchMode && (
            <button
              onClick={() => setBatchMode(true)}
              className="press text-[12px] tracking-[1px] text-gold"
            >
              批量管理
            </button>
          )}
          {shopId && plans.length > 0 && batchMode && (
            <button
              onClick={() => {
                setBatchMode(false)
                setSelected(new Set())
              }}
              className="press text-[12px] tracking-[1px] text-sub"
            >
              退出批量
            </button>
          )}
          {shopId && (
            <button
              onClick={() => onPreviewShop()}
              className="press flex items-center gap-1 text-[12px] tracking-[1px] text-gold"
            >
              店铺装修
              <IconArrow width={10} height={10} />
            </button>
          )}
          {shopId && (
            <Button className="!h-[34px] !text-[12px] !tracking-[1px]" onClick={() => onOpenForm()}>
              <IconPlus width={13} height={13} className="mr-1" />
              新建商品
            </Button>
          )}
        </div>
      </div>
      {shopId && batchMode && plans.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 px-5">
          <button
            onClick={() =>
              setSelected(allSelected ? new Set() : new Set(filteredPlans.map((p) => p.plan_id)))
            }
            className="press flex items-center gap-1.5 text-[12px] text-ink"
          >
            <span
              className={`flex h-[16px] w-[16px] items-center justify-center rounded-[3px] border ${
                allSelected ? 'border-gold bg-gold text-white' : 'border-line bg-white'
              }`}
            >
              {allSelected && <span className="text-[10px] leading-none">✓</span>}
            </span>
            全选
          </button>
          <span className="text-[11px] text-sub">已选 {selected.size} 件</span>
          <div className="ml-auto flex gap-2">
            <button
              className={`${rowBtn} border-gold bg-gold text-[#FAF8F5] disabled:opacity-40`}
              disabled={selected.size === 0 || planBusy}
              onClick={async () => {
                await onBatchToggle(shopId, [...selected], true)
                setSelected(new Set())
              }}
            >
              批量上架
            </button>
            <button
              className={`${rowBtn} border-gold/40 bg-white text-gold disabled:opacity-40`}
              disabled={selected.size === 0 || planBusy}
              onClick={async () => {
                await onBatchToggle(shopId, [...selected], false)
                setSelected(new Set())
              }}
            >
              批量下架
            </button>
          </div>
        </div>
      )}
      {/* 商品筛选：状态 / 关键词 / 分类 */}
      {shopId && plans.length > 0 && (
        <div className="mt-3 px-5">
          <div className="flex gap-1.5">
            {[
              { k: 'all', l: '全部' },
              { k: 'on', l: '在售' },
              { k: 'off', l: '已下架' },
            ].map((f) => (
              <button
                key={f.k}
                onClick={() => setPlanFilter(f.k)}
                className={`flex-1 rounded-full border py-1.5 text-center text-[11px] transition ${
                  planFilter === f.k
                    ? 'border-gold bg-gold/10 font-medium text-gold'
                    : 'border-line bg-white text-sub'
                }`}
              >
                {f.l}
              </button>
            ))}
          </div>
          <div className="mt-2 flex gap-1.5">
            <div className="relative flex-1">
              <IconSearch
                width={13}
                height={13}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sub/60"
              />
              <input
                value={planKw}
                onChange={(e) => setPlanKw(e.target.value)}
                placeholder="搜索商品名 / 描述 / 标签"
                className="w-full rounded-[4px] border border-line bg-bg/50 py-1.5 pl-8 pr-3 text-[11px] text-ink outline-none transition placeholder:text-sub/50 focus:border-gold"
              />
            </div>
            <select
              value={planCat}
              onChange={(e) => setPlanCat(e.target.value)}
              className="max-w-[110px] shrink-0 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold"
            >
              <option value="">全部分类</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      {plans.length === 0 ? (
        <p className="mx-5 mt-3 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
          {shopId ? '该店铺还没有商品，点「新建商品」上架第一款吧' : '从上方选择一个店铺'}
        </p>
      ) : filteredPlans.length === 0 ? (
        <p className="mx-5 mt-3 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
          没有符合条件的商品，试试调整筛选条件
        </p>
      ) : (
        <div className="px-5">
          {filteredPlans.map((p) => (
            <div
              key={p.plan_id}
              className={`mt-3 rounded-card bg-white shadow-card p-4 border ${
                batchMode && selected.has(p.plan_id) ? 'border-gold' : 'border-line'
              }`}
            >
              <div className="flex gap-3">
                {batchMode && (
                  <button
                    onClick={() => toggleSelect(p.plan_id)}
                    className={`mt-[22px] flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] border ${
                      selected.has(p.plan_id) ? 'border-gold bg-gold text-white' : 'border-line bg-white'
                    }`}
                    aria-label={selected.has(p.plan_id) ? '取消选择' : '选择'}
                  >
                    {selected.has(p.plan_id) && <span className="text-[11px] leading-none">✓</span>}
                  </button>
                )}
                <SmartImage
                  src={planImage(p)}
                  imgKey="home_rec_1"
                  className="h-[64px] w-[64px] shrink-0 rounded-[4px]"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate font-serif-cn text-[16px] font-normal text-ink">{p.name}</p>
                    <span
                      className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] ${
                        p.shop_status === 'on' ? 'bg-green-50 text-green-600' : 'bg-line/40 text-sub'
                      }`}
                    >
                      {p.shop_status === 'on' ? '在售' : '已下架'}
                    </span>
                  </div>
                  <p className="mt-1 text-[13px] text-gold">{fmtMoney(p.price)}</p>
                  {p.desc && <p className="mt-0.5 truncate text-[11px] text-sub">{p.desc}</p>}
                  <p className="mt-1 flex items-center gap-1.5 text-[10px] text-sub/70">
                    {catName(p.category_id) && (
                      <span className="rounded-pill bg-gold/10 px-1.5 py-0.5 text-gold">{catName(p.category_id)}</span>
                    )}
                    {p.tags?.length > 0 && <span className="truncate">{p.tags.join(' · ')}</span>}
                  </p>
                </div>
              </div>
              {!batchMode && (
                <div className="mt-3 flex justify-end gap-2 border-t border-line pt-3">
                  <button
                    className={`${rowBtn} border-gold/40 bg-white text-gold hover:border-gold`}
                    onClick={() => onEdit(p)}
                  >
                    编辑
                  </button>
                  {p.shop_status === 'on' ? (
                    <button
                      className={`${rowBtn} border-gold/40 bg-white text-gold hover:border-gold`}
                      disabled={planBusy}
                      onClick={() => onToggle(p)}
                    >
                      下架
                    </button>
                  ) : (
                    <button
                      className={`${rowBtn} border-gold bg-gold text-[#FAF8F5]`}
                      disabled={planBusy}
                      onClick={() => onToggle(p)}
                    >
                      上架
                    </button>
                  )}
                  <button
                    className={`${rowBtn} border-gold/40 bg-white text-gold hover:border-gold`}
                    disabled={planBusy}
                    onClick={() => onRemove(p)}
                  >
                    <IconTrash width={11} height={11} />
                    删除
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

// 店铺设置：店名 / 简介 / 价格区间 / 营业状态 / 店铺图片
function ShopSettingsTab({ shop, saving, onSave, onChange, imgBusy, onUploadImage, onPreviewShop }) {
  if (!shop) {
    return (
      <p className="mx-5 mt-6 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
        从上方选择一个店铺进行设置
      </p>
    )
  }

  const uploadBlock = ({ field, label, hint, previewCls, src, fallback }) => (
    <div>
      <label className="mb-1 block text-[11px] text-sub">{label}</label>
      <div className="flex items-center gap-3">
        {src ? (
          <img src={src} alt={label} className={`${previewCls} shrink-0 rounded-[4px] border border-line object-cover`} />
        ) : (
          <div
            className={`${previewCls} flex shrink-0 items-center justify-center rounded-[4px] border border-gold/20 bg-gold/10 text-[10px] text-gold`}
          >
            {fallback || '未设置'}
          </div>
        )}
        <div className="flex-1">
          <label className="press inline-block cursor-pointer rounded-[4px] border border-line bg-bg px-3 py-2 text-[11px] text-sub">
            {imgBusy ? '上传中…' : '上传'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              disabled={imgBusy}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onUploadImage(field, f)
                e.target.value = ''
              }}
            />
          </label>
          <p className="mt-1 text-[10px] text-sub/70">{hint}</p>
        </div>
      </div>
    </div>
  )

  return (
    <div className="mx-5 mt-4 rounded-card bg-white shadow-card p-4 border border-line">
      <div className="flex items-center justify-between">
        <p className="eyebrow">{shop.name}</p>
        <button
          onClick={() => onPreviewShop()}
          className="press flex items-center gap-1 text-[12px] tracking-[1px] text-gold"
        >
          店铺预览
          <IconArrow width={10} height={10} />
        </button>
      </div>
      <div className="mt-4 space-y-3">
        {uploadBlock({
          field: 'cover',
          label: '店铺封面（横幅，建议 750×300）',
          hint: '未上传时店铺页展示默认封面，支持 jpg/png/webp/gif，≤5MB',
          previewCls: 'h-[56px] w-full max-w-[220px]',
          src: shop.cover || shop.image,
          fallback: '默认封面',
        })}
        {uploadBlock({
          field: 'logo',
          label: '店铺 Logo（方形）',
          hint: '未上传时店铺页不显示头像，支持 jpg/png/webp/gif，≤5MB',
          previewCls: 'h-[64px] w-[64px]',
          src: shop.logo,
          fallback: '默认 Logo',
        })}
        <div>
          <label className="mb-1 block text-[11px] text-sub">店铺名称</label>
          <input
            value={shop.name}
            onChange={(e) => onChange({ ...shop, name: e.target.value })}
            maxLength={40}
            className="maison-field"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-sub">店铺简介</label>
          <textarea
            value={shop.intro || ''}
            onChange={(e) => onChange({ ...shop, intro: e.target.value })}
            maxLength={120}
            rows={3}
            placeholder="一句话介绍你的花店特色"
            className="maison-field w-full resize-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-sub">价格区间（如 100-300）</label>
          <input
            value={shop.price_range || ''}
            onChange={(e) => onChange({ ...shop, price_range: e.target.value })}
            maxLength={30}
            placeholder="100-300"
            className="maison-field"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-sub">营业时间（如 09:00 - 21:00）</label>
          <input
            value={shop.hours || ''}
            onChange={(e) => onChange({ ...shop, hours: e.target.value })}
            maxLength={30}
            placeholder="09:00 - 21:00"
            className="maison-field"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-sub">门店地址</label>
          <input
            value={shop.address || ''}
            onChange={(e) => onChange({ ...shop, address: e.target.value })}
            maxLength={120}
            placeholder="如 广东省深圳市盐田区海山路 18 号"
            className="maison-field"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-sub">店铺公告</label>
          <textarea
            value={shop.notice || ''}
            onChange={(e) => onChange({ ...shop, notice: e.target.value })}
            maxLength={200}
            rows={2}
            placeholder="节假日备货提醒、配送说明等"
            className="maison-field w-full resize-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-sub">营业状态</label>
          <div className="flex gap-2">
            {['营业中', '休息中'].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onChange({ ...shop, status: s })}
                className={`press flex-1 rounded-[2px] border py-2.5 text-[12px] tracking-[1px] ${
                  shop.status === s
                    ? 'border-gold bg-gold/10 text-gold'
                    : 'border-line bg-white text-sub'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
      <Button className="mt-5 w-full !text-[12px] !tracking-[1px]" disabled={saving} onClick={() => onSave(shop)}>
        {saving ? '保存中…' : '保存店铺资料'}
      </Button>
    </div>
  )
}

// 分类管理：商品分类的 新增 / 改名 / 删除（店铺装修 · 分类管理）
function CategoriesTab({ categories, draft, onDraft, busy, onAdd, onRename, onRemove }) {
  const [editingId, setEditingId] = useState('')
  const [editName, setEditName] = useState('')
  const startEdit = (c) => {
    setEditingId(c.id)
    setEditName(c.name)
  }
  return (
    <div className="mx-5 mt-3 rounded-card bg-white shadow-card p-4 border border-line">
      <p className="eyebrow">商品分类</p>
      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          maxLength={20}
          placeholder="新分类名，如 情人节限定"
          className="maison-field flex-1 !py-2 text-[12px]"
        />
        <button
          onClick={onAdd}
          disabled={busy || !draft.trim()}
          className="press inline-flex h-[38px] shrink-0 items-center rounded-[2px] bg-gold px-4 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
        >
          新增
        </button>
      </div>
      {categories.length === 0 ? (
        <p className="mt-3 text-center text-[11px] text-sub">暂无分类，先新增一个吧</p>
      ) : (
        <div className="mt-3 space-y-2">
          {categories.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-[2px] border border-line px-3 py-2.5">
              {editingId === c.id ? (
                <>
                  <input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    maxLength={20}
                    autoFocus
                    className="maison-field !py-1.5 text-[12px]"
                  />
                  <div className="ml-2 flex shrink-0 gap-2">
                    <button
                      className="press text-[11px] tracking-[1px] text-gold"
                      disabled={busy}
                      onClick={async () => {
                        await onRename(c, editName)
                        setEditingId('')
                      }}
                    >
                      保存
                    </button>
                    <button
                      className="press text-[11px] tracking-[1px] text-sub"
                      onClick={() => setEditingId('')}
                    >
                      取消
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="min-w-0">
                    <p className="truncate text-[12px] text-ink">{c.name}</p>
                    <p className="mt-0.5 text-[10px] text-sub/70">{c.plan_count} 件商品</p>
                  </div>
                  <div className="ml-2 flex shrink-0 gap-2">
                    <button
                      className="press text-[11px] tracking-[1px] text-gold"
                      onClick={() => startEdit(c)}
                    >
                      改名
                    </button>
                    <button
                      className="press text-[11px] tracking-[1px] text-sub"
                      disabled={busy}
                      onClick={() => onRemove(c)}
                    >
                      删除
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// 商家-顾客会话：会话列表 + 消息气泡 + 发送（契约 4.1）
function ChatsTab({ chats, loading, activeChat, messages, draft, busy, onOpen, onBack, onDraft, onSend }) {
  if (activeChat) {
    return (
      <div className="flex min-h-[60vh] flex-col">
        {/* 会话头部 */}
        <div className="flex items-center gap-2 border-b border-line bg-white px-4 py-3">
          <button onClick={onBack} className="press text-[12px] tracking-[1px] text-gold">
            ← 返回
          </button>
          <div className="min-w-0">
            <p className="truncate font-serif-cn text-[15px] font-normal text-ink">
              {activeChat.nickname || '顾客'}
            </p>
            <p className="text-[10px] text-sub/70">{activeChat.shop_name || activeChat.shop_id}</p>
          </div>
        </div>
        {/* 消息列表 */}
        <div className="flex-1 space-y-2.5 overflow-y-auto px-4 py-4">
          {messages.length === 0 ? (
            <p className="py-10 text-center text-[11px] text-sub">还没有消息，打个招呼吧</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={`flex ${m.sender === 'merchant' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[78%] rounded-[10px] px-3 py-2 text-[12px] leading-relaxed ${
                    m.sender === 'merchant'
                      ? 'rounded-tr-[2px] bg-gold text-[#FAF8F5]'
                      : 'rounded-tl-[2px] border border-line bg-white text-ink'
                  }`}
                >
                  <p>{m.content}</p>
                  <p className={`mt-0.5 text-[9px] ${m.sender === 'merchant' ? 'text-[#FAF8F5]/70' : 'text-sub/70'}`}>
                    {m.created_at}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
        {/* 输入区 */}
        <div className="flex items-center gap-2 border-t border-line bg-white px-4 py-3">
          <input
            value={draft}
            onChange={(e) => onDraft(e.target.value)}
            placeholder="回复顾客…"
            maxLength={1000}
            className="maison-field flex-1 !h-[40px] !text-[12px]"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                e.preventDefault()
                onSend()
              }
            }}
          />
          <Button className="!h-[40px] !text-[12px] !tracking-[1px]" disabled={busy || !draft.trim()} onClick={onSend}>
            {busy ? '发送中…' : '发送'}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="px-5">
      {loading ? (
        <p className="mt-6 rounded-card bg-white shadow-card p-8 text-center text-[12px] text-sub border border-line">加载中…</p>
      ) : chats.length === 0 ? (
        <p className="mt-6 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
          暂无会话，顾客在店铺发起咨询后会显示在这里
        </p>
      ) : (
        chats.map((c) => (
          <button
            key={c.id}
            onClick={() => onOpen(c)}
            className="press mt-3 flex w-full items-center gap-3 rounded-card bg-white shadow-card p-3.5 text-left border border-line"
          >
            <span className="flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-full bg-gold/10 font-serif-cn text-[15px] font-normal text-gold">
              {(c.nickname || '客')[0]}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-[13px] text-ink">{c.nickname || '顾客'}</p>
                {c.unread_merchant > 0 && (
                  <span className="shrink-0 rounded-full bg-pink px-1.5 py-0.5 text-[9px] leading-none text-white">
                    {c.unread_merchant}
                  </span>
                )}
              </div>
              <p className="mt-0.5 flex items-center gap-1.5 text-[10px] text-sub">
                <span className="truncate">{c.last_msg || '（暂无消息）'}</span>
                <span className="shrink-0 text-sub/60">{c.last_at}</span>
              </p>
              <p className="mt-0.5 text-[10px] text-sub/70">{c.shop_name || c.shop_id}</p>
            </div>
            <IconArrow width={12} height={12} className="shrink-0 text-sub/60" />
          </button>
        ))
      )}
    </div>
  )
}

// 商家工作台：经营看板 + 订单管理 + 商品管理 + 评价管理 + 店铺设置
export default function Merchant() {
  const nav = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [profile, setProfile] = useState(null)
  const [forbidden, setForbidden] = useState(false)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState(null)
  const [orders, setOrders] = useState([])
  const [reviews, setReviews] = useState([])
  const [status, setStatus] = useState('')
  const [filterShop, setFilterShop] = useState('')
  const [keyword, setKeyword] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [tab, setTab] = useState(() => searchParams.get('tab') || 'dashboard')
  const [busyId, setBusyId] = useState('')
  const [expandedId, setExpandedId] = useState('')
  const [logiExpandedId, setLogiExpandedId] = useState('')
  const [logiDraft, setLogiDraft] = useState({})
  const [logiBusy, setLogiBusy] = useState(false)
  const [plans, setPlans] = useState({})
  const [planBusy, setPlanBusy] = useState(false)
  const [shopId, setShopId] = useState('')
  const [shopPlans, setShopPlans] = useState([])
  const [shopForm, setShopForm] = useState(null)
  const [shopSaving, setShopSaving] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [planForm, setPlanForm] = useState({ name: '', price: '', desc: '', style: '', tags: '', effect_image_url: '', category_id: '' })
  const [formBusy, setFormBusy] = useState(false)
  const [imgBusy, setImgBusy] = useState(false)
  const [categories, setCategories] = useState([])
  const [catBusy, setCatBusy] = useState(false)
  const [catDraft, setCatDraft] = useState('')
  const [replyDraft, setReplyDraft] = useState({})
  const [replyOpen, setReplyOpen] = useState('')
  const [replyBusy, setReplyBusy] = useState('')
  const [chats, setChats] = useState([])
  const [chatLoading, setChatLoading] = useState(false)
  const [activeChat, setActiveChat] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [chatDraft, setChatDraft] = useState('')
  const [chatBusy, setChatBusy] = useState(false)

  // 店铺选择变化时同步加载该店商品 / 店铺资料
  useEffect(() => {
    if (!shopId || tab !== 'plans') return
    merchantPlans(shopId)
      .then(setShopPlans)
      .catch(() => setShopPlans([]))
  }, [shopId, tab])

  const load = useCallback(async (p = null) => {
    setLoading(true)
    try {
      if (p && p.role !== 'merchant') {
        setForbidden(true)
        return
      }
      const [st, os, rs] = await Promise.all([
        merchantStats(),
        merchantOrders(filterShop, status, keyword, dateFrom, dateTo),
        merchantReviews(),
      ])
      setStats(st)
      setOrders(os)
      setReviews(rs)
      setShopId((cur) => cur || st.shops?.[0]?.id || '')
      setForbidden(false)
    } catch (e) {
      if (/403/.test(e.message)) {
        setForbidden(true)
      } else if (/401/.test(e.message)) {
        toast('请先登录商家账号', 'error')
        nav('/profile')
      } else {
        toast(e.message || '加载失败', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [status, filterShop, keyword, dateFrom, dateTo])

  // 权限预检：先取账号角色，非商家/管理员直接进拒绝页，不发任何商家接口请求
  // （避免普通用户打开 /merchant 时刷出一串 403 控制台噪音）。
  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p)
        if (!p?.role) {
          toast('请先登录商家账号', 'error')
          nav('/profile')
          return
        }
        if (p.role !== 'merchant') {
          setForbidden(true)
          setLoading(false)
          return
        }
        load()
      })
      .catch(() => {
        setForbidden(true)
        setLoading(false)
      })
  }, [load])

  useEffect(() => {
    if (!shopId || tab !== 'shop') return
    const s = stats?.shops?.find((x) => (x.id || x) === shopId)
    setShopForm(s ? { ...s } : null)
  }, [shopId, tab, stats])

  const ship = async (oid) => {
    if (busyId) return
    setBusyId(oid)
    try {
      await merchantShip(oid)
      toast('已代发货')
      load()
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setBusyId('')
    }
  }

  const addLogisticsNode = async (o) => {
    const text = (logiDraft[o.order_id] || '').trim()
    if (!text) {
      toast('请填写物流节点内容', 'error')
      return
    }
    if (logiBusy) return
    setLogiBusy(true)
    try {
      await merchantAddLogistics(o.order_id, text)
      toast('物流节点已追加')
      setLogiDraft((d) => ({ ...d, [o.order_id]: '' }))
      load()
    } catch (e) {
      toast(e.message || '追加失败', 'error')
    } finally {
      setLogiBusy(false)
    }
  }

  const togglePlan = async (o) => {
    if (expandedId === o.order_id) {
      setExpandedId('')
      return
    }
    setExpandedId(o.order_id)
    if (!o.plan_id || plans[o.order_id]) return
    setPlanBusy(true)
    try {
      const detail = await merchantOrderDetail(o.order_id)
      setPlans((prev) => ({ ...prev, [o.order_id]: detail.plan || null }))
    } catch (e) {
      toast(e.message || '加载方案失败', 'error')
      setPlans((prev) => ({ ...prev, [o.order_id]: null }))
    } finally {
      setPlanBusy(false)
    }
  }

  const openForm = (p = null) => {
    setEditing(p)
    setPlanForm(
      p
        ? { name: p.name || '', price: String(p.price ?? ''), desc: p.desc || '', style: p.style || '', tags: (p.tags || []).join('，'), effect_image_url: p.effect_image_url || '', category_id: p.category_id || '' }
        : { name: '', price: '', desc: '', style: '', tags: '', effect_image_url: '', category_id: '' },
    )
    setFormOpen(true)
  }

  // 图片上传（商品图 / 店铺图共用）：上传成功回填 url 到对应表单
  const uploadImage = async (file, target) => {
    if (imgBusy) return
    if (file.size > 5 * 1024 * 1024) {
      toast('图片不能超过 5MB', 'error')
      return
    }
    if (!/\.(jpe?g|png|webp|gif)$/i.test(file.name)) {
      toast('仅支持 jpg/png/webp/gif 格式', 'error')
      return
    }
    setImgBusy(true)
    try {
      const url = await merchantUpload(file)
      if (target === 'plan') {
        setPlanForm((f) => ({ ...f, effect_image_url: url }))
      } else if (target === 'cover') {
        setShopForm((s) => (s ? { ...s, cover: url } : s))
      } else if (target === 'logo') {
        setShopForm((s) => (s ? { ...s, logo: url } : s))
      } else {
        setShopForm((s) => (s ? { ...s, image: url } : s))
      }
      toast('图片已上传')
    } catch (e) {
      toast(e.message || '上传失败', 'error')
    } finally {
      setImgBusy(false)
    }
  }

  const submitPlanForm = async (e) => {
    e.preventDefault()
    if (formBusy) return
    if (!planForm.name.trim() || !Number(planForm.price) || Number(planForm.price) <= 0) {
      toast('请填写商品名称和正确的价格', 'error')
      return
    }
    setFormBusy(true)
    try {
      const payload = {
        name: planForm.name.trim(),
        price: Number(planForm.price),
        desc: planForm.desc.trim(),
        style: planForm.style.trim(),
        tags: planForm.tags.split(/[，,]/).map((t) => t.trim()).filter(Boolean),
        effect_image_url: planForm.effect_image_url,
        category_id: planForm.category_id || 'cat_daily',
      }
      if (editing) {
        await merchantUpdatePlan(shopId, editing.plan_id, payload)
        toast('商品已更新')
      } else {
        await merchantCreatePlan(shopId, payload)
        toast('商品已上架')
      }
      setFormOpen(false)
      const list = await merchantPlans(shopId)
      setShopPlans(list)
    } catch (err) {
      toast(err.message || '操作失败', 'error')
    } finally {
      setFormBusy(false)
    }
  }

  const toggleShopPlan = async (p) => {
    if (planBusy) return
    setPlanBusy(true)
    try {
      await merchantTogglePlan(shopId, p.plan_id)
      toast(p.shop_status === 'on' ? '已下架' : '已上架')
      setShopPlans(await merchantPlans(shopId))
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setPlanBusy(false)
    }
  }

  const removeShopPlan = async (p) => {
    if (!window.confirm(`确定删除「${p.name}」吗？删除后将从本店下架。`)) return
    if (planBusy) return
    setPlanBusy(true)
    try {
      await merchantDeletePlan(shopId, p.plan_id)
      toast('商品已删除')
      setShopPlans(await merchantPlans(shopId))
    } catch (e) {
      toast(e.message || '操作失败', 'error')
    } finally {
      setPlanBusy(false)
    }
  }

  const batchTogglePlans = async (sid, planIds, on) => {
    const targetShop = sid || shopId
    if (!targetShop || planIds.length === 0) return
    if (planBusy) return
    setPlanBusy(true)
    try {
      await merchantBatchToggle(targetShop, planIds, on)
      toast(on ? `已上架 ${planIds.length} 件` : `已下架 ${planIds.length} 件`)
      if (targetShop === shopId) setShopPlans(await merchantPlans(shopId))
    } catch (e) {
      toast(e.message || '批量操作失败', 'error')
    } finally {
      setPlanBusy(false)
    }
  }

  // 切换 Tab：进入工作台首页时重置筛选，保证看到全量经营数据
  const switchTab = (t) => {
    setTab(t)
    setSearchParams(t === 'dashboard' ? {} : { tab: t }, { replace: true })
    if (t === 'dashboard') {
      setStatus('')
      setFilterShop('')
      setKeyword('')
      setDateFrom('')
      setDateTo('')
    }
  }

  // 底部商家导航 / 外部链接通过 ?tab= 切换工作台页签；URL 变化时同步内部 tab
  useEffect(() => {
    const t = searchParams.get('tab') || 'dashboard'
    setTab(t)
  }, [searchParams])

  // 商家内部预览：店铺装修 Tab（替代跳 C 端 /shop/:id）
  const viewShop = (id) => {
    setShopId(id || '')
    setTab('shop')
    setSearchParams({ tab: 'shop' }, { replace: true })
  }

  // 商家内部预览：物流 Tab 并展开该单（替代跳 C 端 /logistics/:id）
  const viewLogistics = (oid) => {
    setStatus('')
    setLogiExpandedId(oid)
    setTab('logistics')
    setSearchParams({ tab: 'logistics' }, { replace: true })
  }

  // 评价回复：写 reviews.reply / reply_at 后刷新列表
  const submitReviewReply = async (r) => {
    const text = (replyDraft[r.id] || '').trim()
    if (!text) {
      toast('请输入回复内容', 'error')
      return
    }
    if (replyBusy) return
    setReplyBusy(r.id)
    try {
      await merchantReplyReview(r.id, text)
      toast('回复已发布')
      setReplyOpen('')
      setReplyDraft((d) => ({ ...d, [r.id]: '' }))
      load()
    } catch (e) {
      toast(e.message || '回复失败', 'error')
    } finally {
      setReplyBusy('')
    }
  }

  // 商家-顾客会话：列表加载 / 打开会话 / 发送
  const refreshChats = useCallback(async () => {
    setChatLoading(true)
    try {
      setChats(await merchantChats())
    } catch (e) {
      toast(e.message || '会话加载失败', 'error')
    } finally {
      setChatLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab !== 'chats') return
    refreshChats()
  }, [tab, refreshChats])

  const openChat = async (chat) => {
    setActiveChat(chat)
    setChatMessages([])
    setChatDraft('')
    try {
      const data = await merchantChatMessages(chat.id)
      setChatMessages(data.messages || [])
    } catch (e) {
      toast(e.message || '消息加载失败', 'error')
    }
  }

  const sendChat = async () => {
    const text = chatDraft.trim()
    if (!text || !activeChat) return
    if (chatBusy) return
    setChatBusy(true)
    try {
      await merchantSendChatMessage(activeChat.id, text)
      setChatDraft('')
      const data = await merchantChatMessages(activeChat.id)
      setChatMessages(data.messages || [])
    } catch (e) {
      toast(e.message || '发送失败', 'error')
    } finally {
      setChatBusy(false)
    }
  }

  // 分类管理：列表加载 + 新增 / 改名 / 删除（店铺装修）
  const refreshCategories = useCallback(async () => {
    try {
      setCategories(await merchantCategories())
    } catch (e) {
      toast(e.message || '分类加载失败', 'error')
    }
  }, [])

  useEffect(() => {
    refreshCategories()
  }, [refreshCategories])

  const addCategory = async () => {
    const name = catDraft.trim()
    if (!name) return
    if (catBusy) return
    setCatBusy(true)
    try {
      await merchantCreateCategory(name)
      setCatDraft('')
      await refreshCategories()
      toast(`已新增分类「${name}」`)
    } catch (e) {
      toast(e.message || '新增失败', 'error')
    } finally {
      setCatBusy(false)
    }
  }

  const renameCategory = async (cat, name) => {
    const next = (name || '').trim()
    if (!next || next === cat.name) return
    if (catBusy) return
    setCatBusy(true)
    try {
      await merchantRenameCategory(cat.id, next)
      await refreshCategories()
      toast('分类已改名')
    } catch (e) {
      toast(e.message || '改名失败', 'error')
    } finally {
      setCatBusy(false)
    }
  }

  const removeCategory = async (cat) => {
    if (catBusy) return
    if (cat.plan_count > 0 && !window.confirm(`「${cat.name}」下还有 ${cat.plan_count} 件商品，删除后它们将归入默认分类，确定删除？`)) return
    if (cat.plan_count === 0 && !window.confirm(`确定删除分类「${cat.name}」？`)) return
    setCatBusy(true)
    try {
      await merchantDeleteCategory(cat.id)
      await refreshCategories()
      toast('分类已删除')
    } catch (e) {
      toast(e.message || '删除失败', 'error')
    } finally {
      setCatBusy(false)
    }
  }

  const saveShop = async (s) => {
    if (shopSaving) return
    setShopSaving(true)
    try {
      await merchantUpdateShop(s.id || s.shop_id, {
        name: s.name?.trim(),
        intro: s.intro?.trim(),
        price_range: s.price_range?.trim(),
        status: s.status,
        image: s.image || '',
        cover: s.cover || '',
        logo: s.logo || '',
        hours: s.hours || '',
        address: s.address || '',
        notice: s.notice || '',
      })
      toast('店铺资料已保存')
      load()
    } catch (e) {
      toast(e.message || '保存失败', 'error')
    } finally {
      setShopSaving(false)
    }
  }

  if (forbidden) {
    return (
      <div className="min-h-full bg-bg pb-8">
        <div className="hero-flora relative px-5 pb-6 pt-8 text-center shadow-soft">
          <FloraCorner
            className="pointer-events-none absolute -right-2 -top-1 text-white/50"
            style={{ width: 92, height: 92 }}
          />
          <p className="eyebrow">Merchant Console</p>
          <h1 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">商家工作台</h1>
          <div className="mx-auto mt-3 h-px w-9 bg-gold" />
          <p className="mt-3 text-[12px] text-sub">专属花艺，温柔收藏</p>
        </div>
        <div className="px-5 pt-6 text-center">
          <p className="rounded-card bg-white shadow-card p-8 text-[13px] text-sub border border-line">
            无商家权限
            <br />
            <span className="mt-1 block text-[11px] text-sub/70">
              仅商家角色可查看经营数据，请联系系统管理员授权
            </span>
          </p>
        </div>
      </div>
    )
  }

  const shops = (stats?.shops || []).map((s) => (typeof s === 'string' ? { id: s, name: s } : s))
  const shopNames = shops.map((s) => s.name).join(' / ')
  const pendingCount = stats?.pending_ship ?? 0
  const currentShop = shops.find((s) => s.id === shopId)

  return (
    <div className="min-h-full bg-bg pb-8">
      <div className="hero-flora relative px-5 pb-6 pt-8 text-center shadow-soft">
        <FloraCorner
          className="pointer-events-none absolute -right-2 -top-1 text-white/50"
          style={{ width: 92, height: 92 }}
        />
        <p className="eyebrow">Merchant Console</p>
        <h1 className="mt-2 font-serif-cn text-[28px] font-normal text-ink">商家工作台</h1>
        <div className="mx-auto mt-3 h-px w-9 bg-gold" />
        <p className="mt-3 text-[12px] text-sub">
          {profile?.nickname || profile?.username || '商家'} · 打理每一束花的旅程
        </p>
      </div>

      <div className="relative mx-5 mt-5 overflow-hidden rounded-card bg-white shadow-card p-4 border border-line">
        <FloraSprig
          className="pointer-events-none absolute -right-2 -bottom-3 text-gold/20"
          style={{ width: 64, height: 64 }}
        />
        <div className="flex items-baseline justify-between">
          <p className="eyebrow">经营总览</p>
          {shopNames && <span className="max-w-[55%] truncate text-[10px] text-sub">{shopNames}</span>}
        </div>
        <div className="mt-3 grid grid-cols-4">
          {[
            { label: '订单', value: stats ? `${stats.order_count}` : '-' },
            { label: 'GMV', value: stats ? fmtMoney(stats.gmv) : '-' },
            { label: '待发货', value: stats ? `${stats.pending_ship}` : '-' },
            { label: '已完成', value: stats ? `${stats.done_count}` : '-' },
          ].map((c, i) => (
            <div key={c.label} className={`flex flex-col items-center ${i > 0 ? 'border-l border-line' : ''}`}>
              <span className="max-w-full truncate font-serif-cn text-[17px] font-normal text-ink">{c.value}</span>
              <span className="mt-1 text-[10px] tracking-[0.15em] text-sub">{c.label}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-center gap-5 border-t border-line pt-3 text-center">
          <span className="text-[10px] tracking-[0.15em] text-sub">
            评价{' '}
            <span className="font-serif-cn text-[13px] font-normal text-ink">
              {stats?.review_count ?? '-'}
            </span>
          </span>
          <span className="text-[10px] tracking-[0.15em] text-sub">
            平均分{' '}
            <span className="font-serif-cn text-[13px] font-normal text-ink">
              {stats && stats.avg_rating ? Number(stats.avg_rating).toFixed(1) : '-'}
            </span>
          </span>
          <span className="text-[10px] tracking-[0.15em] text-sub">
            已取消{' '}
            <span className="font-serif-cn text-[13px] font-normal text-ink">
              {stats?.canceled_count ?? '-'}
            </span>
          </span>
        </div>
      </div>

      {/* 内部导航：只保留底部导航没有的页签（经营/订单/商品/会话 已由底部导航承载） */}
      <div className="mt-6 grid grid-cols-3 border-b border-line/60 px-2">
        {[
          { key: 'logistics', label: '物流管理' },
          { key: 'reviews', label: '评价管理', badge: reviews.length },
          { key: 'shop', label: '店铺设置' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => switchTab(t.key)}
            className={`relative flex items-center justify-center gap-1 pb-2.5 pt-1 text-[13px] tracking-[0.02em] transition ${
              tab === t.key
                ? 'font-medium text-gold after:absolute after:-bottom-px after:left-1/2 after:h-[2px] after:w-9 after:-translate-x-1/2 after:bg-gold'
                : 'text-sub'
            }`}
          >
            {t.label}
            {!!t.badge && (
              <span className="flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-gold/15 px-1 text-[9px] leading-none text-gold">
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="mx-5 mt-6 rounded-card bg-white shadow-card p-8 text-center text-[12px] text-sub border border-line">
          加载中…
        </p>
      ) : tab === 'dashboard' ? (
        <DashboardTab
          stats={stats}
          orders={orders}
          reviews={reviews}
          shops={stats?.shops || []}
          onGoTab={switchTab}
          onShip={ship}
          busyId={busyId}
          onViewShop={viewShop}
        />
      ) : tab === 'orders' ? (
        <>
          {/* 筛选卡片：关键词 + 日期区间 */}
          <div className="mx-5 mt-3 rounded-card border border-line bg-white shadow-card p-3">
            <div className="relative">
              <IconSearch
                width={14}
                height={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sub/60"
              />
              <input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜索订单号 / 收货人 / 商品名"
                className="w-full rounded-[4px] border border-line bg-bg/50 py-2 pl-9 pr-3 text-[12px] text-ink outline-none transition placeholder:text-sub/50 focus:border-gold"
              />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold"
              />
              <span className="shrink-0 text-[10px] text-sub/60">至</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="flex-1 rounded-[4px] border border-line bg-bg/50 px-2 py-1.5 text-[11px] text-ink outline-none transition focus:border-gold"
              />
              {(keyword || dateFrom || dateTo) && (
                <button
                  onClick={() => {
                    setKeyword('')
                    setDateFrom('')
                    setDateTo('')
                  }}
                  className="press shrink-0 rounded-[4px] border border-gold/40 px-2.5 py-1.5 text-[11px] tracking-[1px] text-gold"
                >
                  清除
                </button>
              )}
            </div>
          </div>
          {/* 状态筛选：胶囊均分一行 */}
          <div className="mt-3 flex gap-1.5 px-5">
            {STATUS_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setStatus(t.key)}
                className={`flex-1 rounded-full border py-1.5 text-center text-[11px] transition ${
                  status === t.key
                    ? 'border-gold bg-gold/10 font-medium text-gold'
                    : 'border-line bg-white text-sub'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {/* 店铺筛选：横向滚动胶囊 */}
          {shops.length > 0 && (
            <div className="mt-2 flex gap-1.5 overflow-x-auto px-5 pb-1 [scrollbar-width:none]">
              <button
                onClick={() => setFilterShop('')}
                className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${
                  !filterShop ? 'border-gold bg-gold/10 font-medium text-gold' : 'border-line bg-white text-sub'
                }`}
              >
                全部店铺
              </button>
              {shops.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setFilterShop(s.id)}
                  className={`shrink-0 rounded-pill border px-3 py-1 text-[11px] transition ${
                    filterShop === s.id
                      ? 'border-gold bg-gold/10 font-medium text-gold'
                      : 'border-line bg-white text-sub'
                  }`}
                >
                  {s.name}
                </button>
              ))}
            </div>
          )}
          {orders.length === 0 ? (
            <p className="mx-5 mt-6 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
              {status ? `暂无「${STATUS_TABS.find((t) => t.key === status)?.label || status}」订单` : '还没有订单'}
            </p>
          ) : (
            <div className="px-5">
              {orders.map((o) => (
                <OrderCard
                  key={o.order_id}
                  o={o}
                  expanded={expandedId === o.order_id}
                  onToggle={() => togglePlan(o)}
                  plan={plans[o.order_id]}
                  planBusy={planBusy}
                  busyId={busyId}
                  onShip={ship}
                  onViewLogistics={viewLogistics}
                />
              ))}
            </div>
          )}
          {pendingCount > 0 && status === 'paid' && (
            <p className="mt-3 px-5 text-[10px] text-sub/70">
              {pendingCount} 笔订单待发货，请尽快安排备货
            </p>
          )}
        </>
      ) : tab === 'logistics' ? (
        <LogisticsTab
          orders={orders}
          shops={shops}
          filterShop={filterShop}
          onSelectShop={setFilterShop}
          status={status}
          onStatus={setStatus}
          logiExpandedId={logiExpandedId}
          onToggleExpanded={(id) => setLogiExpandedId(logiExpandedId === id ? '' : id)}
          logiDraft={logiDraft}
          onDraft={(id, v) => setLogiDraft((d) => ({ ...d, [id]: v }))}
          logiBusy={logiBusy}
          onAddNode={addLogisticsNode}
        />
      ) : tab === 'plans' ? (
        <ShopPlansTab
          shops={shops}
          plans={shopPlans}
          shopId={shopId}
          onSelectShop={(id) => setShopId(id)}
          planBusy={planBusy}
          onOpenForm={() => openForm()}
          onEdit={openForm}
          onToggle={toggleShopPlan}
          onRemove={removeShopPlan}
          onBatchToggle={batchTogglePlans}
          categories={categories}
          onPreviewShop={() => viewShop(shopId)}
        />
      ) : tab === 'shop' ? (
        <>
          <ShopSettingsTab
            shop={shopForm}
            saving={shopSaving}
            onSave={saveShop}
            onChange={setShopForm}
            imgBusy={imgBusy}
            onUploadImage={(field, f) => uploadImage(f, field)}
            onPreviewShop={() => viewShop(shopForm?.id || shopForm?.shop_id || '')}
          />
          <CategoriesTab
            categories={categories}
            draft={catDraft}
            onDraft={setCatDraft}
            busy={catBusy}
            onAdd={addCategory}
            onRename={renameCategory}
            onRemove={removeCategory}
          />
        </>
      ) : tab === 'reviews' ? (
        reviews.length === 0 ? (
          <p className="mx-5 mt-6 rounded-card bg-white shadow-card p-6 text-center text-[12px] text-sub border border-line">
            暂无评价
          </p>
        ) : (
          <div className="px-5">
            {reviews.map((r) => (
              <div key={r.id} className="mt-3 rounded-card bg-white shadow-card p-4 border border-line">
                <div className="flex items-center justify-between">
                  <span className="font-serif-cn text-[14px] font-normal text-ink">{r.nickname || '匿名用户'}</span>
                  <span className="text-[10px] text-sub">{r.created_at}</span>
                </div>
                <div className="mt-1 flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <IconStar
                      key={s}
                      width={13}
                      height={13}
                      filled={s <= r.rating}
                      className={s <= r.rating ? 'text-pink' : 'text-line'}
                    />
                  ))}
                  {r.plan_id && <span className="ml-2 text-[10px] text-sub/70">{r.plan_id}</span>}
                </div>
                {r.content && (
                  <p className="mt-2 rounded-[2px] bg-bg px-3 py-2 text-[12px] leading-relaxed text-ink">
                    {r.content}
                  </p>
                )}
                {/* 商家回复（已回复展示 / 未回复可输入） */}
                {r.reply ? (
                  <div className="mt-2 rounded-[2px] bg-gold/10 px-3 py-2">
                    <p className="text-[10px] tracking-[0.1em] text-gold">商家回复{r.reply_at ? ` · ${r.reply_at}` : ''}</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-dark">{r.reply}</p>
                  </div>
                ) : replyOpen === r.id ? (
                  <div className="mt-2">
                    <textarea
                      value={replyDraft[r.id] || ''}
                      onChange={(e) => setReplyDraft((d) => ({ ...d, [r.id]: e.target.value }))}
                      placeholder="回复顾客评价…（选填，最多 500 字）"
                      maxLength={500}
                      rows={2}
                      className="maison-field w-full resize-none"
                    />
                    <div className="mt-1.5 flex justify-end gap-2">
                      <button
                        onClick={() => {
                          setReplyOpen('')
                          setReplyDraft((d) => ({ ...d, [r.id]: '' }))
                        }}
                        className="press px-3 text-[11px] tracking-[1px] text-sub"
                      >
                        取消
                      </button>
                      <Button
                        className="!h-[32px] !px-4 !text-[11px] !tracking-[1px]"
                        disabled={replyBusy === r.id}
                        onClick={() => submitReviewReply(r)}
                      >
                        {replyBusy === r.id ? '发布中…' : '发布回复'}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setReplyOpen(r.id)}
                    className="press mt-2 text-[11px] tracking-[1px] text-gold"
                  >
                    回复
                  </button>
                )}
              </div>
            ))}
          </div>
        )
      ) : tab === 'chats' ? (
        <ChatsTab
          chats={chats}
          loading={chatLoading}
          activeChat={activeChat}
          messages={chatMessages}
          draft={chatDraft}
          busy={chatBusy}
          onOpen={openChat}
          onBack={() => {
            setActiveChat(null)
            refreshChats()
          }}
          onDraft={setChatDraft}
          onSend={sendChat}
        />
      ) : null}

      {/* 新建 / 编辑商品弹层 */}
      {formOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setFormOpen(false)}
        >
          <div
            className="w-full max-w-h5 rounded-t-[20px] bg-white px-5 pb-8 pt-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-4 h-[2px] w-9 bg-gold" />
            <h3 className="font-serif-cn text-[19px] font-normal text-ink">
              {editing ? '编辑商品' : '新建商品'}
            </h3>
            <p className="mt-1 text-[11px] text-sub">
              商品将上架到「{currentShop?.name || shopId}」
            </p>
            <form onSubmit={submitPlanForm} className="mt-4 space-y-3">
              {/* 商品图片上传 */}
              <div>
                <label className="mb-1 block text-[11px] text-sub">商品图片</label>
                <div className="flex items-center gap-3">
                  <SmartImage
                    src={planImage({ effect_image_url: planForm.effect_image_url, plan_id: editing?.plan_id })}
                    imgKey="home_rec_1"
                    className="h-[64px] w-[84px] shrink-0 rounded-[4px]"
                  />
                  <div className="flex-1">
                    <label className="press inline-block cursor-pointer rounded-[4px] border border-line bg-bg px-3 py-2 text-[11px] text-sub">
                      {imgBusy ? '上传中…' : planForm.effect_image_url ? '更换图片' : '上传图片'}
                      <input
                        type="file"
                        accept="image/jpeg,image/png,image/webp,image/gif"
                        className="hidden"
                        disabled={imgBusy}
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) uploadImage(f, 'plan')
                          e.target.value = ''
                        }}
                      />
                    </label>
                    <p className="mt-1 text-[10px] text-sub/70">支持 jpg/png/webp/gif，≤5MB</p>
                  </div>
                </div>
              </div>
              <input
                placeholder="商品名称（必填）"
                value={planForm.name}
                onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
                maxLength={60}
                className="maison-field"
              />
              <input
                placeholder="价格 ¥（必填）"
                inputMode="decimal"
                value={planForm.price}
                onChange={(e) => setPlanForm({ ...planForm, price: e.target.value.replace(/[^\d.]/g, '') })}
                className="maison-field"
              />
              <textarea
                placeholder="商品描述（选填）"
                value={planForm.desc}
                onChange={(e) => setPlanForm({ ...planForm, desc: e.target.value })}
                maxLength={200}
                rows={3}
                className="maison-field w-full resize-none"
              />
              <input
                placeholder="风格（选填，如 韩式）"
                value={planForm.style}
                onChange={(e) => setPlanForm({ ...planForm, style: e.target.value })}
                maxLength={20}
                className="maison-field"
              />
              <select
                value={planForm.category_id}
                onChange={(e) => setPlanForm({ ...planForm, category_id: e.target.value })}
                className="maison-field w-full !py-3 text-[12px]"
              >
                <option value="">商品分类（选填，默认 日常陪伴）</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <input
                placeholder="标签（选填，逗号分隔，如 母亲节,粉色）"
                value={planForm.tags}
                onChange={(e) => setPlanForm({ ...planForm, tags: e.target.value })}
                maxLength={60}
                className="maison-field"
              />
              <Button type="submit" className="w-full !text-[12px] !tracking-[1px]" disabled={formBusy}>
                {formBusy ? '保存中…' : editing ? '保存修改' : '上架商品'}
              </Button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}