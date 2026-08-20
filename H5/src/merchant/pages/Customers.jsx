// 商家-顾客会话：会话列表 + 聊天窗口 + 5s 轮询新消息。
// contact prop：订单「联系顾客」请求，到达后自动打开/创建该顾客会话。
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { merchantChatMessages, merchantChats, merchantChatWithUser, merchantSendChatMessage } from '../api'

export function Customers({ contact, onContactConsumed }) {
  const [chats, setChats] = useState([])
  const [activeChat, setActiveChat] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const listRef = useRef(null)

  // 订单「联系顾客」：直达该顾客的会话（无会话则创建）
  useEffect(() => {
    if (!contact?.user_id || !contact?.shop_id) return
    const open = async () => {
      try {
        const data = await merchantChatWithUser(contact.user_id, contact.shop_id)
        setActiveChat({
          ...data.chat,
          nickname: contact.recipient_name || '顾客',
          shop_name: contact.shop_id,
        })
        setMessages(data.messages || [])
        setDraft('')
        refresh()
      } catch (e) {
        setErr(e.message || '会话打开失败')
      } finally {
        if (onContactConsumed) onContactConsumed()
      }
    }
    open()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact?.user_id])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setChats(await merchantChats())
    } catch (e) {
      setErr(e.message || '会话加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const openChat = async (chat) => {
    setActiveChat(chat)
    setMessages([])
    setDraft('')
    try {
      const data = await merchantChatMessages(chat.id)
      setMessages(data.messages || [])
    } catch (e) {
      setErr(e.message || '消息加载失败')
    }
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || !activeChat || busy) return
    setBusy(true)
    try {
      await merchantSendChatMessage(activeChat.id, text)
      setDraft('')
      const data = await merchantChatMessages(activeChat.id)
      setMessages(data.messages || [])
      refresh()
    } catch (e) {
      setErr(e.message || '发送失败')
    } finally {
      setBusy(false)
    }
  }

  // 打开会话期间每 5s 拉取新消息
  useEffect(() => {
    if (!activeChat?.id) return
    const timer = setInterval(async () => {
      try {
        const data = await merchantChatMessages(activeChat.id)
        setMessages(data.messages || [])
      } catch {
        /* 静默重试 */
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [activeChat?.id])

  // 新消息自动滚到底
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages])

  const unread = chats.reduce((n, c) => n + (c.unread_merchant || 0), 0)

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">顾客会话</h2>
        {unread > 0 && <span className="text-[11px] text-gold">{unread} 条未读</span>}
      </div>

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      <div className="mt-4 grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* 会话列表 */}
        <div className="h-[62vh] overflow-y-auto rounded-card border border-line bg-white">
          {loading ? (
            <p className="p-8 text-center text-[12px] text-sub">加载中…</p>
          ) : chats.length === 0 ? (
            <p className="p-8 text-center text-[12px] text-sub">暂无会话</p>
          ) : (
            chats.map((c) => (
              <button
                key={c.id}
                onClick={() => openChat(c)}
                className={`block w-full border-b border-line/60 px-4 py-3 text-left transition ${
                  activeChat?.id === c.id ? 'bg-gold/10' : 'hover:bg-bg'
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="truncate text-[13px] text-ink">{c.nickname || c.shop_name || '顾客'}</p>
                  {(c.unread_merchant || 0) > 0 && (
                    <span className="flex h-[16px] min-w-[16px] items-center justify-center rounded-full bg-gold px-1 text-[9px] text-[#FAF8F5]">
                      {c.unread_merchant}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 truncate text-[11px] text-sub">{c.last_message || ''}</p>
              </button>
            ))
          )}
        </div>

        {/* 聊天窗口 */}
        <div className="flex h-[62vh] flex-col rounded-card border border-line bg-white">
          {!activeChat ? (
            <div className="flex flex-1 items-center justify-center text-[12px] text-sub">
              选择左侧会话开始沟通
            </div>
          ) : (
            <>
              <div className="border-b border-line px-4 py-3">
                <p className="text-[13px] text-ink">{activeChat.nickname || '顾客'}</p>
                <p className="text-[10px] text-sub">{activeChat.shop_name || ''}</p>
              </div>
              <div ref={listRef} className="flex-1 space-y-2 overflow-y-auto bg-bg/30 p-4">
                {messages.length === 0 ? (
                  <p className="text-center text-[11px] text-sub/60">暂无消息</p>
                ) : (
                  messages.map((m) => (
                    <div key={m.id} className={`flex ${m.from_merchant ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className={`max-w-[75%] rounded-[4px] px-3 py-2 text-[12px] leading-relaxed ${
                          m.from_merchant ? 'bg-gold text-[#FAF8F5]' : 'bg-white text-ink border border-line'
                        }`}
                      >
                        <p>{m.content}</p>
                        <p className={`mt-1 text-[9px] ${m.from_merchant ? 'text-[#FAF8F5]/70' : 'text-sub/60'}`}>
                          {m.created_at?.replace('T', ' ').slice(0, 16) || ''}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="flex items-center gap-2 border-t border-line p-3">
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && send()}
                  placeholder="输入回复内容…"
                  className="flex-1 rounded-[4px] border border-line bg-bg/50 px-3 py-2 text-[12px] text-ink outline-none transition placeholder:text-sub/50 focus:border-gold"
                />
                <button
                  onClick={send}
                  disabled={busy || !draft.trim()}
                  className="press rounded-[4px] bg-gold px-4 py-2 text-[12px] tracking-[1px] text-[#FAF8F5] disabled:opacity-40"
                >
                  {busy ? '发送中…' : '发送'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}