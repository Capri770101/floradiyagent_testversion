import React, { useEffect, useRef, useState } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import Reveal from '../components/Reveal'
import { toast } from '../utils/toast'
import { userChatWithShop, userChatMessages, userSendChatMessage } from '../api/shop'

const QUICK_REPLIES = [
  '请问可以同城配送吗？',
  '能指定配送时间吗？',
  '支持哪些支付方式？',
  '可以开发票吗？',
]

// 顾客-商家会话页（/chat/:shopId）：取或建会话 → 气泡对话 → 5s 轮询新消息（契约 4.1）
export default function Chat() {
  const { shopId } = useParams()
  const location = useLocation()
  const ctx = location.state?.context
  const [chat, setChat] = useState(null)
  const [shopName, setShopName] = useState('')
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const data = await userChatWithShop(shopId)
        if (!alive) return
        setChat(data.chat)
        setShopName(data.shop_name || shopId)
        setMessages(data.messages || [])
      } catch (e) {
        if (alive) toast(e.message || '会话加载失败', 'error')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [shopId])

  useEffect(() => {
    if (!chat?.id) return
    const timer = setInterval(async () => {
      try {
        const data = await userChatMessages(chat.id)
        setMessages(data.messages || [])
      } catch {
        // 轮询失败静默，下次重试
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [chat?.id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length])

  const send = async (textOverride) => {
    const text = (textOverride ?? draft).trim()
    if (!text || !chat?.id || busy) return
    setBusy(true)
    try {
      await userSendChatMessage(chat.id, text)
      if (textOverride === undefined) setDraft('')
      const data = await userChatMessages(chat.id)
      setMessages(data.messages || [])
    } catch (e) {
      toast(e.message || '发送失败', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title={loading ? '会话' : shopName} />
      {ctx && (
        <div className="flex items-center gap-2 bg-gold/10 px-4 py-2 text-[11px] text-gold-dark">
          <span className="shrink-0 rounded-pill bg-gold/20 px-2 py-0.5">{ctx.kind || '关联'}</span>
          <span className="truncate text-sub">{ctx.label}</span>
        </div>
      )}
      <div className="flex-1 space-y-2.5 overflow-y-auto px-4 py-4">
        {loading ? (
          <p className="py-12 text-center text-[12px] text-sub">加载中…</p>
        ) : messages.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-[11px] text-sub">还没有消息，向商家打个招呼吧</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2 px-4">
              {QUICK_REPLIES.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  disabled={busy}
                  className="press rounded-pill border border-line bg-white px-3 py-1.5 text-[11px] text-ink"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <Reveal
              key={m.id}
              className={`flex ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              delay={Math.min(i, 8) * 100}
            >
              <div
                className={`max-w-[78%] rounded-[10px] px-3 py-2 text-[12px] leading-relaxed ${
                  m.sender === 'user'
                    ? 'rounded-tr-[2px] bg-gold text-[#FAF8F5]'
                    : 'rounded-tl-[2px] border border-line bg-white text-ink'
                }`}
              >
                <p>{m.content}</p>
                <p className={`mt-0.5 text-[9px] ${m.sender === 'user' ? 'text-[#FAF8F5]/70' : 'text-sub/70'}`}>
                  {m.created_at}
                </p>
              </div>
            </Reveal>
          ))
        )}
        <div ref={bottomRef} />
      </div>
      {messages.length > 0 && (
        <div className="app-scroll flex gap-2 overflow-x-auto border-t border-line bg-white px-4 py-2">
          {QUICK_REPLIES.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              disabled={busy}
              className="press shrink-0 rounded-pill border border-line bg-bg px-3 py-1 text-[11px] text-sub"
            >
              {q}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2 border-t border-line bg-white px-4 py-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`咨询 ${shopName || '商家'}…`}
          maxLength={1000}
          className="maison-field flex-1 !h-[40px] !text-[12px]"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
              e.preventDefault()
              send()
            }
          }}
        />
        <Button
          className="!h-[40px] !text-[12px] !tracking-[1px]"
          disabled={busy || !draft.trim()}
          onClick={() => send()}
        >
          {busy ? '发送中…' : '发送'}
        </Button>
      </div>
    </div>
  )
}
