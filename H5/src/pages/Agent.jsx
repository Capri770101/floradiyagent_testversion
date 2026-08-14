import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  sendChat,
  getUserId,
  listConversations,
  createConversation,
  getMessages,
  deleteConversation,
} from '../api/chat'
import { createOrder } from '../api/shop'
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
    <div className="animate-fade-up mt-2 rounded-card-lg bg-white p-4 shadow-card">
      <p className="text-[12px] text-sub">
        {isShop ? '为你找到的现成方案' : '我为你设计了一款'}
      </p>
      <h3 className="mt-1 text-[18px] font-medium text-dark">{plan.name}</h3>
      <div className="mt-3 flex gap-3">
        <SmartImage
          src={plan.plan_id ? itemImagePath('plans', plan.plan_id) : null}
          imgKey={isShop ? undefined : 'agent_plan'}
          color={isShop ? PLACEHOLDER.productBig : PLACEHOLDER.agentPlan}
          className="h-[128px] w-[112px] shrink-0 rounded-[14px]"
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

export default function Agent() {
  const nav = useNavigate()
  const [messages, setMessages] = useState([GREETING])
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [input, setInput] = useState('')
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
            shop: p.merchant || 'FloraDIY',
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
    return arr
  }

  function renderMessage(m, idx) {
    if (m.role === 'user') {
      return (
        <div key={idx} className="flex justify-end px-4 pb-3">
          <div className="max-w-[220px] rounded-[16px] bg-pink px-3.5 py-2.5 text-right text-[12px] leading-relaxed text-white">
            {m.content}
          </div>
        </div>
      )
    }
    return (
      <div key={idx} className="px-4 pb-3">
        <div className="flex items-start gap-2">
          <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-pink text-white">
            <IconFlower width={16} height={16} />
          </div>
          <div className="max-w-[285px]">
            {m.content && (
              <div className="rounded-[16px] bg-white px-3.5 py-2.5">
                {m.lead ? (
                  <>
                    <p className="mb-1 font-medium text-dark">{m.content}</p>
                    <p className="text-[11px] text-sub">{m.lead}</p>
                  </>
                ) : (
                  <p className="text-[13px] leading-relaxed text-ink">
                    {m.content}
                  </p>
                )}
              </div>
            )}
            {m.ui === 'plan_card' &&
              extractPlans(m.data).map((p, i) =>
                p._type === 'diy' ? (
                <DiyPlanCard
                  key={i}
                  plan={p}
                  onConfirm={() =>
                    nav(`/diy/${p.plan_id || 'demo'}`, { state: { plan: p } })
                  }
                  onAdjust={() => send('调整方案')}
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
            {m.ui === 'dialog_options' &&
              m.data?.options?.map((o, i) => (
                <Pill
                  key={i}
                  label={o.label}
                  selected={i === 0}
                  onClick={() => send(o.value || o.label)}
                  style={{ marginTop: 8 }}
                />
              ))}
            {m.ui === 'pay_jump' && (
              <Button
                className="mt-2 w-full"
                onClick={() => {
                  const oid =
                    m.data?.params?.order_id || m.data?.order_id
                  nav('/pay', { state: { orderId: oid } })
                }}
              >
                去支付
              </Button>
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
        {messages.map(renderMessage)}
        {loading && (
          <div className="px-4 pb-3">
            <div className="flex items-start gap-2">
              <div className="mt-1 flex h-7 w-7 items-center justify-center rounded-full bg-pink text-white">
                <IconFlower width={16} height={16} />
              </div>
              <div className="rounded-[16px] bg-white px-4 py-3">
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
        <div className="flex h-[50px] flex-1 items-center rounded-[25px] bg-white px-4">
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
            <div className="flex-1 overflow-y-auto py-2">
              {conversations.length === 0 && (
                <p className="px-4 pt-4 text-[12px] text-sub">暂无历史对话</p>
              )}
              {conversations.map((c) => (
                <div
                  key={c.id}
                  onClick={() => switchTo(c.id)}
                  className={`flex cursor-pointer items-center px-4 py-3 ${
                    c.id === activeId ? 'bg-pink2' : ''
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] text-ink">
                      {c.title || '新对话'}
                    </p>
                    <p className="truncate text-[11px] text-sub">
                      {c.preview || ''}
                    </p>
                  </div>
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
