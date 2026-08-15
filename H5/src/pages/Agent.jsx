import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  sendChat,
  getUserId,
  listConversations,
  createConversation,
  getMessages,
  deleteConversation,
  renameConversation,
  getImageTask,
  withApiUrl,
} from '../api/chat'
import { createOrder } from '../api/shop'
import { calcPayable } from '../utils/price'
import { Placeholder } from '../components/Placeholder'
import { Pill } from '../components/Pill'
import { Button } from '../components/Button'
import DiyPlanCard from '../components/DiyPlanCard'
import SmartImage from '../components/SmartImage'
import { itemImagePath } from '../assets/imageMap'
import { IconFlower, IconPlus, IconMenu, IconTrash } from '../components/icons'
import { PLACEHOLDER } from '../tokens'

const GREETING = {
  role: 'assistant',
  content: '嗨～我是小兰，你的花艺设计助手',
  lead: '告诉我你想送给谁、什么场合、预算多少，我来为你设计专属花束。',
}

// 每一条助手回复都保证有文字：清理空行、纯空白/空回复时按 ui 类型给兜底文案，
// 避免出现只有卡片没有文字的「哑消息」或空白气泡。
const REPLY_FALLBACK = {
  plan_card: '为你找到了一个方案，看看下面的卡片吧～',
  image_task: '效果图已生成，展开卡片查看吧～',
  shop_card: '为你推荐了几家不错的店铺，选一家下单吧～',
  order_card: '订单已创建，去支付完成下单吧～',
  pay_jump: '订单已创建，去支付完成下单吧～',
  dialog_options: '请选择你想要的方案类型～',
  text: '好的，收到你的想法啦，请稍等～',
}

function bubbleText(m) {
  const raw = String(m.content || '')
    .replace(/\n{2,}/g, '\n')
    .trim()
  return raw || REPLY_FALLBACK[m.ui] || REPLY_FALLBACK.text
}

function flowersOf(plan) {
  const list = []
  if (plan.main_flowers) list.push(plan.main_flowers)
  if (plan.fillers) list.push(plan.fillers)
  if (plan.foliage) list.push(plan.foliage)
  if (!list.length && plan.desc) list.push(plan.desc)
  return list
}

function ChatPlanCard({ plan, onConfirm, onAdjust }) {
  const isShop = plan._type === 'shop'
  return (
    <div className="animate-fade-up mt-2 rounded-card-lg bg-white p-4 border border-line">
      <p className="text-[12px] text-sub">
        {isShop ? '为你找到的现成方案' : '我为你设计了一款'}
      </p>
      <h3 className="mt-1 text-[18px] font-medium text-dark">{plan.name}</h3>
      <div className="mt-3 flex gap-3">
        <SmartImage
          src={plan.plan_id ? itemImagePath('plans', plan.plan_id) : null}
          imgKey={isShop ? undefined : 'agent_plan'}
          color={isShop ? PLACEHOLDER.productBig : PLACEHOLDER.agentPlan}
          className="h-[128px] w-[112px] shrink-0 rounded-[4px]"
        />
        <div className="flex-1">
          <p className="text-[12px] leading-[26px] text-ink">
            {flowersOf(plan).map((f, i) => (
              <span key={i} className="block">
                {f}
              </span>
            ))}
          </p>
          {plan.merchant && (
            <p className="mt-1 text-[11px] text-sub">{plan.merchant}</p>
          )}
        </div>
      </div>
      {plan.price != null && (
        <p className="mt-3 text-[18px] font-medium text-pink">¥{plan.price}</p>
      )}
      <div className="mt-3 flex gap-3">
        {onAdjust && (
          <Button variant="secondary" className="flex-1" onClick={onAdjust}>
            调整方案
          </Button>
        )}
        {onConfirm && (
          <Button variant="primary" className="flex-1" onClick={onConfirm}>
            {isShop ? '立即购买' : '确认方案'}
          </Button>
        )}
      </div>
    </div>
  )
}

// 生图结果卡片：同步任务带 result_url 直接渲染；异步任务轮询 /tasks/{id} 至 done
// 仅在无前置方案卡时独立展示（通常效果图会并入方案卡片）
function ImageTaskCard({ data }) {
  // 防御：无 task_id 也无 result_url 的空生图卡片（LLM 幻觉）不渲染
  if (!data?.task_id && !data?.result_url && !data?.image_url) return null
  // 后端 result_url 为 /generated/{id}.jpg 形式，经 Vite 代理需补 /api 前缀
  const doneUrl = withApiUrl(data?.result_url || data?.image_url)
  const [state, setState] = useState(() =>
    doneUrl ? { status: 'done', result_url: doneUrl } : { status: 'pending' }
  )

  useEffect(() => {
    if (!data?.task_id || doneUrl) return
    let alive = true
    const poll = async () => {
      try {
        const r = await getImageTask(data.task_id)
        if (!alive) return
        if (r.status === 'done') {
          setState({ status: 'done', result_url: withApiUrl(r.result_url) })
        } else if (r.status === 'failed') {
          setState({ status: 'failed' })
        } else {
          setTimeout(poll, 2000)
        }
      } catch (e) {
        if (alive) setState({ status: 'failed' })
      }
    }
    poll()
    return () => {
      alive = false
    }
  }, [data?.task_id, doneUrl])

  if (state.status === 'failed') {
    return (
      <p className="mt-2 rounded-[4px] bg-pink-2 px-3 py-2 text-[11px] text-pink">
        效果图生成失败了，可以让我重新生成试试。
      </p>
    )
  }
  return (
    <div className="mt-2 rounded-card-lg bg-white p-3 border border-line">
      {state.status === 'pending' && (
        <div className="mb-2">
          <div className="h-1 w-full overflow-hidden rounded-full bg-pink-2">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-pink" />
          </div>
          <p className="mt-1.5 text-[12px] text-sub">
            效果图生成中，约需 30 秒…
          </p>
        </div>
      )}
      {state.status === 'done' && state.result_url && (
        <SmartImage
          src={state.result_url}
          imgKey="agent_plan"
          color={PLACEHOLDER.agentPlan}
          className="w-full rounded-[4px]"
          alt="效果图"
        />
      )}
    </div>
  )
}

// 店铺推荐卡片：展示后端 search_shops / LLM 透传的店铺列表。
// 卡片主体 → 进店（店铺详情页）；「去这家下单」→ 向智能体发出选店确认，由 create_order 产出订单。
function ShopCard({ shops, onPick }) {
  const nav = useNavigate()
  return (
    <div className="mt-2 space-y-2">
      {shops.map((s) => (
        <div
          key={s.shop_id || s.id}
          className="press block w-full rounded-card-lg bg-white p-3 text-left border border-line"
        >
          <button
            onClick={() => nav(`/shop/${s.shop_id || s.id}`)}
            className="block w-full text-left"
          >
            <div className="flex items-center gap-3">
              <SmartImage
                src={itemImagePath('shops', s.shop_id || s.id)}
                imgKey="shop_logo"
                className="h-[52px] w-[52px] shrink-0 rounded-[4px]"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium text-dark">
                  {s.name}
                </p>
                <p className="mt-0.5 text-[11px] text-sub">
                  {s.rating != null && (
                    <span className="mr-1">评分 {s.rating}</span>
                  )}
                  {s.distance_km != null && (
                    <span className="mr-1">{s.distance_km}km</span>
                  )}
                  {s.price_range && <span>¥{s.price_range}</span>}
                </p>
                {s.intro && (
                  <p className="mt-0.5 truncate text-[11px] text-sub">
                    {s.intro}
                  </p>
                )}
              </div>
            </div>
          </button>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-[11px] text-sub">起送 ¥{s.min_delivery ?? '—'} · 配送 ¥{s.delivery_fee ?? '—'}</span>
            <button
              onClick={() => onPick(s)}
              className="text-[12px] font-medium text-pink"
            >
              去这家下单 →
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

// 订单卡片：展示 create_order 产出的订单摘要，附「去支付」跳转
function OrderCard({ data, onPay }) {
  const items = Array.isArray(data?.items) ? data.items : []
  const total =
    data?.total_price ??
    items.reduce((a, b) => a + Number(b.price || b.amount || 0), 0)
  const discount =
    data?.pay_jump?.params?.discount ?? data?.discount ?? 0
  const oid = data?.pay_jump?.params?.order_id || data?.order_id
  return (
    <div className="mt-2 rounded-card-lg bg-white p-4 border border-line">
      <p className="text-[12px] text-sub">订单已创建，确认信息后去支付</p>
      {items.map((it, i) => (
        <div
          key={i}
          className="mt-2 flex items-center justify-between text-[13px]"
        >
          <span className="min-w-0 truncate text-ink">
            {it.name || it.plan_name}
          </span>
          <span className="shrink-0 text-pink">
            ¥{it.price ?? it.amount}
          </span>
        </div>
      ))}
      <div className="mt-2 flex justify-between border-t border-line pt-2 text-[13px]">
        <span className="text-sub">应付合计</span>
        <span className="font-medium text-pink">¥{calcPayable(total, discount).toFixed(2)}</span>
      </div>
      <p className="mt-1 text-[10px] text-sub">
        含配送费，已减优惠券 ¥{Number(discount || 0).toFixed(2)}；以支付页为准
      </p>
      {oid && <p className="mt-1 text-[11px] text-sub">订单号：{oid}</p>}
      {onPay && (
        <Button className="mt-3 w-full" onClick={onPay}>
          去支付
        </Button>
      )}
    </div>
  )
}

export default function Agent() {
  const nav = useNavigate()
  const [messages, setMessages] = useState([GREETING])
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [input, setInput] = useState('')
  const [search, setSearch] = useState('')
  const [renamingId, setRenamingId] = useState(null)
  const [renameText, setRenameText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)

  // 进入页面：拉取会话列表；若有历史则自动打开最近的会话（保留对话记录）
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const convs = await listConversations(getUserId())
        if (!alive) return
        setConversations(convs)
        if (convs.length > 0) {
          const latest = convs[0]
          setActiveId(latest.id)
          const msgs = await getMessages(latest.id, getUserId())
          if (alive) setMessages(msgs.length ? msgs : [GREETING])
        }
      } catch (e) {
        if (alive) console.warn('加载会话列表失败', e)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // 刷新会话列表（保留当前 activeId），用于新建/发送/删除后同步预览与排序
  const refreshConversations = useCallback(async () => {
    try {
      const convs = await listConversations(getUserId())
      setConversations(convs)
    } catch (e) {
      console.warn('刷新会话列表失败', e)
    }
  }, [])

  const openNewChat = useCallback(async () => {
    try {
      const cid = await createConversation(getUserId(), '新对话')
      setActiveId(cid)
      setMessages([GREETING])
      setDrawerOpen(false)
      await refreshConversations()
    } catch (e) {
      setError(e.message || '新建会话失败')
    }
  }, [refreshConversations])

  const switchTo = useCallback(async (convId) => {
    try {
      const msgs = await getMessages(convId, getUserId())
      setActiveId(convId)
      setMessages(msgs.length ? msgs : [GREETING])
      setDrawerOpen(false)
    } catch (e) {
      setError(e.message || '加载会话失败')
    }
  }, [])

  const removeConv = useCallback(
    async (convId, e) => {
      e.stopPropagation()
      try {
        await deleteConversation(convId, getUserId())
        if (activeId === convId) {
          setActiveId(null)
          setMessages([GREETING])
        }
        await refreshConversations()
      } catch (err) {
        setError(err.message || '删除失败')
      }
    },
    [activeId, refreshConversations]
  )

  const startRename = useCallback(
    (c, e) => {
      e.stopPropagation()
      setRenamingId(c.id)
      setRenameText(c.title || '')
    },
    []
  )

  const submitRename = useCallback(
    async (e) => {
      e?.stopPropagation()
      const title = renameText.trim()
      if (!title || !renamingId) return
      try {
        await renameConversation(renamingId, title, getUserId())
        setRenamingId(null)
        await refreshConversations()
      } catch (err) {
        setError(err.message || '重命名失败')
      }
    },
    [renamingId, renameText, refreshConversations]
  )

  const visibleConvs = conversations.filter((c) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return (
      (c.title || '').toLowerCase().includes(q) ||
      (c.preview || '').toLowerCase().includes(q)
    )
  })

  // 现成方案「立即购买」：先落单拿到 orderId，再带单号跳订单确认页
  const handleBuyShop = useCallback(
    async (p) => {
      if (!p?.plan_id) return
      try {
        const order = await createOrder(getUserId(), [
          {
            plan_id: p.plan_id,
            name: p.name,
            price: p.price,
            qty: 1,
            shop: p.merchant || 'MAISON·FLORA',
          },
        ])
        nav('/order', { state: { orderId: order.order_id } })
      } catch (e) {
        setError(e.message || '下单失败')
      }
    },
    [nav]
  )

  async function send(text) {
    const msg = (text ?? input).trim()
    if (!msg || loading) return
    // 首条消息前确保有会话（无则先建）
    let sid = activeId
    if (!sid) {
      try {
        sid = await createConversation(getUserId(), msg.slice(0, 20))
        setActiveId(sid)
      } catch (e) {
        setError(e.message || '创建会话失败')
        return
      }
    }
    const userMsg = { role: 'user', content: msg }
    const hist = [...messages, userMsg]
    setMessages(hist)
    setInput('')
    setError(null)
    setLoading(true)
    try {
      const resp = await sendChat({
        message: msg,
        sessionId: sid,
        userId: getUserId(),
      })
      // 智能体可能因「新需求」开新会话（DONE 后重购），以返回的会话 ID 为准
      if (resp.session_id) setActiveId(resp.session_id)
      setMessages([
        ...hist,
        {
          role: 'assistant',
          content: resp.reply || '',
          ui: resp.ui,
          data: resp.data,
        },
      ])
      await refreshConversations()
    } catch (e) {
      setError(e.message || '请求失败')
      setMessages([
        ...hist,
        {
          role: 'assistant',
          content:
            '抱歉，连接后端失败了，请确认服务已启动（后端 uvicorn 在 8080，且 H5 用 npm run dev 访问）。',
          error: true,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function extractPlans(data) {
    if (!data) return []
    if (Array.isArray(data.plans))
      return data.plans.map((p) => {
        // 兼容 LLM 不返回 type 字段的情况：用 diy 标记 / DIY_ 前缀 / design 嵌套识别 DIY 方案
        const isDiy =
          p.diy === true ||
          (typeof p.plan_id === 'string' && p.plan_id.startsWith('DIY_')) ||
          !!p.design
        return { ...p, _type: isDiy ? 'diy' : 'shop' }
      })
    const arr = []
    if (data.plan) arr.push({ ...data.plan, _type: 'diy' })
    if (data.existing_plan) arr.push({ ...data.existing_plan, _type: 'shop' })
    // LLM 有时把方案对象平铺在 data 顶层（无 plans 包装），按 DIY 方案兜底识别
    if (!arr.length && (data.plan_id || data.name)) {
      arr.push({ ...data, _type: 'diy' })
    }
    return arr
  }

  // 把生图结果（image_task）挂到最近的前一张方案卡片上，效果图并入卡片展示；
  // 无前置方案卡时才保留为独立生图卡片；生图消息若带文本内容则保留为纯文本气泡
  // （如「效果图已生成，展开卡片查看」/ 确认类提示），避免整条消息被吞掉。
  function attachImages(msgs) {
    const out = []
    for (let i = 0; i < msgs.length; i++) {
      const m = msgs[i]
      if (m.ui === 'image_task' && m.data) {
        const img = {
          task_id: m.data.task_id,
          result_url: m.data.result_url || m.data.image_url,
          poll: m.data.poll,
        }
        let attached = false
        if (img.task_id || img.result_url) {
          for (let j = out.length - 1; j >= 0; j--) {
            if (out[j].ui === 'plan_card') {
              out[j] = { ...out[j], _img: img }
              attached = true
              break
            }
          }
        }
        if (!attached) out.push(m)
        else if (m.content) out.push({ ...m, ui: 'text' })
      } else {
        out.push(m)
      }
    }
    return out
  }

  function renderMessage(m, idx) {
    if (m.role === 'user') {
      return (
        <div key={idx} className="flex justify-end px-4 pb-3">
          <div className="max-w-[220px] rounded-[4px] bg-pink px-3.5 py-2.5 text-right text-[12px] leading-relaxed text-white">
            {m.content}
          </div>
        </div>
      )
    }
    const content = bubbleText(m)
    return (
      <div key={idx} className="px-4 pb-3">
        <div className="flex items-start gap-2">
          <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-pink text-white">
            <IconFlower width={16} height={16} />
          </div>
          <div className="max-w-[285px]">
            <div className="rounded-[4px] bg-white px-3.5 py-2.5">
              {m.lead ? (
                <>
                  <p className="mb-1 font-medium text-dark">{content}</p>
                  <p className="text-[11px] text-sub">{m.lead}</p>
                </>
              ) : (
                <p className="text-[13px] leading-relaxed text-ink">{content}</p>
              )}
            </div>
            {m.ui === 'plan_card' &&
              extractPlans(m.data).map((p, i) =>
                p._type === 'diy' ? (
                <DiyPlanCard
                  key={i}
                  plan={p}
                  img={m._img}
                  onConfirm={() =>
                    nav(`/diy/${p.plan_id || 'demo'}`, { state: { plan: p } })
                  }
                  onAdjust={(d) => send(d || '调整方案')}
                />
                ) : (
                <ChatPlanCard
                  key={i}
                  plan={p}
                  onConfirm={() => handleBuyShop(p)}
                  onAdjust={() => send('调整方案')}
                />
                )
              )}
            {m.ui === 'image_task' && <ImageTaskCard data={m.data} />}
            {m.ui === 'shop_card' && m.data?.shops?.length > 0 && (
              <ShopCard
                shops={m.data.shops}
                onPick={(s) => send(`选择 ${s.name} 帮我下单`)}
              />
            )}
            {m.ui === 'order_card' && (
              <OrderCard
                data={m.data}
                onPay={() => {
                  const oid =
                    m.data?.pay_jump?.params?.order_id || m.data?.order_id
                  nav('/pay', { state: { orderId: oid } })
                }}
              />
            )}
            {m.ui === 'dialog_options' &&
              m.data?.options?.map((o, i) => {
                const opt =
                  typeof o === 'string' ? { label: o, value: o } : o
                return (
                  <Pill
                    key={i}
                    label={opt?.label}
                    selected={i === 0}
                    onClick={() => send(opt?.value || opt?.label)}
                    style={{ marginTop: 8 }}
                  />
                )
              })}
            {m.ui === 'pay_jump' && (
              <OrderCard
                data={{
                  order_id: m.data?.order_id,
                  items: [
                    {
                      name: m.data?.plan_name || '花束',
                      price: m.data?.total_price ?? 0,
                    },
                  ],
                  total_price: m.data?.total_price ?? 0,
                }}
                onPay={() => {
                  const oid =
                    m.data?.pay_jump?.params?.order_id || m.data?.order_id
                  nav('/pay', { state: { orderId: oid } })
                }}
              />
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex h-full flex-col bg-bg">
      <div className="relative flex h-[56px] shrink-0 items-center justify-center border-b border-line bg-bg px-4">
        <button
          onClick={() => setDrawerOpen(true)}
          className="press absolute left-3 text-ink"
          aria-label="会话列表"
        >
          <IconMenu width={22} height={22} />
        </button>
        <span className="text-[16px] font-medium text-dark">小兰</span>
        <span className="ml-2 text-[9px] text-sub">AI花艺师</span>
        <button
          onClick={openNewChat}
          className="press absolute right-3 text-pink text-[13px]"
        >
          + 新对话
        </button>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto py-3">
        {attachImages(messages).map(renderMessage)}
        {loading && (
          <div className="px-4 pb-3">
            <div className="flex items-start gap-2">
              <div className="mt-1 flex h-7 w-7 items-center justify-center rounded-full bg-pink text-white">
                <IconFlower width={16} height={16} />
              </div>
              <div className="rounded-[4px] bg-white px-4 py-3">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-sub" />
                <span
                  className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-sub"
                  style={{ animationDelay: '0.2s' }}
                />
                <span
                  className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-sub"
                  style={{ animationDelay: '0.4s' }}
                />
              </div>
            </div>
          </div>
        )}
        {error && <p className="px-4 pb-2 text-[11px] text-pink">{error}</p>}
      </div>

      <div className="flex shrink-0 items-center gap-2 border-t border-line bg-bg px-4 py-3">
        <div className="flex h-[50px] flex-1 items-center rounded-[4px] bg-white px-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="说说你的想法…"
            className="w-full bg-transparent text-[12px] text-ink outline-none placeholder:text-sub"
          />
        </div>
        <button
          onClick={() => send()}
          className="press flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-full bg-pink text-white"
          aria-label="发送"
        >
          <IconPlus width={20} height={20} />
        </button>
      </div>

      {/* 会话抽屉（类 ChatGPT 多会话列表） */}
      {drawerOpen && (
        <div className="absolute inset-0 z-30 flex">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="relative flex h-full w-[78%] max-w-[300px] flex-col bg-white shadow-xl">
            <div className="flex h-[56px] shrink-0 items-center justify-between border-b border-line px-4">
              <span className="text-[15px] font-medium text-dark">对话</span>
              <button
                onClick={openNewChat}
                className="text-[13px] text-pink"
              >
                + 新对话
              </button>
            </div>
            <div className="px-3 pt-3">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索对话…"
                className="w-full rounded-[4px] border border-line bg-bg px-3 py-2 text-[12px] text-ink outline-none placeholder:text-sub"
              />
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {visibleConvs.length === 0 && (
                <p className="px-4 pt-4 text-[12px] text-sub">
                  {search ? '没有匹配的对话' : '暂无历史对话'}
                </p>
              )}
              {visibleConvs.map((c) => (
                <div
                  key={c.id}
                  onClick={() => switchTo(c.id)}
                  className={`flex cursor-pointer items-center px-4 py-3 ${
                    c.id === activeId ? 'bg-pink-2' : ''
                  }`}
                >
                  {renamingId === c.id ? (
                    <div className="min-w-0 flex-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        autoFocus
                        value={renameText}
                        onChange={(e) => setRenameText(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && submitRename(e)}
                        className="w-full rounded-[2px] border border-pink bg-white px-2 py-1 text-[13px] text-ink outline-none"
                      />
                      <div className="mt-1 flex gap-2">
                        <button
                          onClick={submitRename}
                          className="text-[12px] text-pink"
                        >
                          保存
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setRenamingId(null)
                          }}
                          className="text-[12px] text-sub"
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] text-ink">
                        {c.title || '新对话'}
                      </p>
                      <p className="truncate text-[11px] text-sub">
                        {c.preview || ''}
                      </p>
                    </div>
                  )}
                  {renamingId !== c.id && (
                    <button
                      onClick={(e) => startRename(c, e)}
                      className="press ml-2 text-[12px] text-sub"
                      aria-label="重命名会话"
                    >
                      改名
                    </button>
                  )}
                  <button
                    onClick={(e) => removeConv(c.id, e)}
                    className="press ml-2 text-sub"
                    aria-label="删除会话"
                  >
                    <IconTrash width={16} height={16} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
