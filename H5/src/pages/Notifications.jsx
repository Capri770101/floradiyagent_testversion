import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { IconBell, IconStore } from '../components/icons'
import Reveal from '../components/Reveal'
import { listNotifications, markAllRead, unreadCount } from '../api/notify'
import { listUserChats } from '../api/shop'

// 用户消息中心：整合「与商家的历史对话」与「站内通知」。
// - 顶栏右侧显示总未读数（通知未读 + 商家会话未读）。
// - 页签：商家会话（与各商家的历史对话）/ 通知（订单/物流/评价/售后/公告）。
// - 商家会话点击进入 /chat/:shopId；通知点击进入详情页。

const TYPE_TABS = [
  { key: '', label: '全部' },
  { key: 'order_status', label: '订单' },
  { key: 'logistics', label: '物流' },
  { key: 'review_reply', label: '评价' },
  { key: 'aftersale', label: '售后' },
  { key: 'announcement', label: '公告' },
]

const TYPE_META = {
  order_status: { icon: 'bg-pink/10 text-pink' },
  logistics: { icon: 'bg-cream/20 text-gold-dark' },
  review_reply: { icon: 'bg-sand text-burgundy' },
  aftersale: { icon: 'bg-green/10 text-green' },
  announcement: { icon: 'bg-stone/10 text-stone' },
  system: { icon: 'bg-sub/10 text-sub' },
}

export default function Notifications() {
  const nav = useNavigate()
  const [section, setSection] = useState('chats') // chats | notices
  const [type, setType] = useState('')
  const [items, setItems] = useState(null) // null=加载中
  const [err, setErr] = useState('')
  const [markedOnce, setMarkedOnce] = useState(false)
  const [chats, setChats] = useState(null) // null=加载中
  const [chatErr, setChatErr] = useState('')
  const [unreadTotal, setUnreadTotal] = useState(0)

  // 顶栏总未读数：通知未读 + 商家会话未读
  const loadUnread = useCallback(async () => {
    try {
      const [notiUnread, chatList] = await Promise.all([
        unreadCount().catch(() => 0),
        listUserChats().catch(() => []),
      ])
      const chatUnread = (chatList || []).reduce((s, c) => s + (c.unread_user || 0), 0)
      setUnreadTotal((notiUnread || 0) + chatUnread)
    } catch {
      setUnreadTotal(0)
    }
  }, [])

  useEffect(() => {
    loadUnread()
  }, [loadUnread])

  // 通知列表
  const load = useCallback(
    async (t) => {
      setErr('')
      setItems(null)
      try {
        const list = await listNotifications({ type: t, limit: 50 })
        setItems(list)
        if (!markedOnce) {
          setMarkedOnce(true)
          markAllRead().catch(() => {})
          loadUnread()
        }
      } catch (e) {
        setErr(e.message || '消息加载失败，请稍后重试')
        setItems([])
      }
    },
    [markedOnce, loadUnread],
  )

  useEffect(() => {
    if (section === 'notices') load(type)
  }, [section, load, type])

  // 商家会话列表
  const loadChats = useCallback(async () => {
    setChatErr('')
    setChats(null)
    try {
      const list = await listUserChats()
      setChats(list)
    } catch (e) {
      setChatErr(e.message || '会话加载失败，请稍后重试')
      setChats([])
    }
  }, [])

  useEffect(() => {
    if (section === 'chats') loadChats()
  }, [section, loadChats])

  const fmtTime = (t) => {
    if (!t) return ''
    const d = new Date(String(t).replace(' ', 'T'))
    if (Number.isNaN(d.getTime())) return String(t).slice(5, 16)
    const now = new Date()
    const sameDay = d.toDateString() === now.toDateString()
    const hhmm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    if (sameDay) return hhmm
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hhmm}`
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar
        title="消息"
        right={
          unreadTotal > 0 ? (
            <span className="rounded-pill bg-pink/10 px-2 py-0.5 text-[10px] font-medium text-pink">
              {unreadTotal} 条未读
            </span>
          ) : (
            <span className="text-[10px] text-sub/70">全部已读</span>
          )
        }
      />

      {/* 顶部主页签：商家会话 / 通知 */}
      <div className="flex shrink-0 border-b border-line bg-white px-3 py-2">
        {[
          { key: 'chats', label: '商家会话' },
          { key: 'notices', label: '通知' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setSection(t.key)}
            className={`flex-1 rounded-pill py-1.5 text-[12px] ${
              section === t.key ? 'bg-pink text-white' : 'text-sub'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {section === 'chats' ? (
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {chatErr ? (
            <div className="rounded-card border border-line bg-white p-6 text-center">
              <p className="text-[12px] text-sub">{chatErr}</p>
              <button
                onClick={loadChats}
                className="press mt-3 rounded-pill bg-pink px-5 py-2 text-[12px] text-white"
              >
                重新加载
              </button>
            </div>
          ) : chats === null ? (
            <p className="py-10 text-center text-[12px] text-sub">加载中…</p>
          ) : chats.length === 0 ? (
            <Reveal>
              <div className="rounded-card border border-line bg-white p-8 text-center">
                <IconStore width={30} height={30} className="mx-auto text-line" />
                <p className="mt-3 text-[12px] text-sub">
                  暂无商家会话
                  <br />
                  <span className="mt-1 block text-[11px] text-sub/70">
                    去店铺页点「联系商家」开始对话
                  </span>
                </p>
              </div>
            </Reveal>
          ) : (
            <div className="space-y-2.5">
              {chats.map((c, i) => (
                <Reveal key={c.id} delay={i * 100}>
                  <button
                    onClick={() => nav(`/chat/${encodeURIComponent(c.shop_id)}`)}
                    className="flex w-full items-center gap-3 rounded-card border border-line bg-white p-3.5 text-left"
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold/10 text-gold">
                      <IconStore width={18} height={18} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between">
                        <span className="truncate text-[13px] font-medium text-dark">
                          {c.shop_name || c.shop_id}
                        </span>
                        <span className="ml-2 shrink-0 text-[10px] text-sub/70">
                          {fmtTime(c.last_at)}
                        </span>
                      </span>
                      <span className="mt-1 flex items-center justify-between">
                        <span className="truncate text-[12px] text-sub">
                          {c.last_msg || '开始对话吧'}
                        </span>
                        {c.unread_user > 0 && (
                          <span className="ml-2 flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full bg-pink px-1 text-[10px] font-medium leading-none text-white">
                            {c.unread_user > 99 ? '99+' : c.unread_user}
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                </Reveal>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* 通知类型页签 */}
          <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-white px-3 py-2">
            {TYPE_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setType(t.key)}
                className={`shrink-0 rounded-pill px-3 py-1.5 text-[12px] ${
                  type === t.key ? 'bg-pink text-white' : 'text-sub'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {err ? (
              <div className="rounded-card border border-line bg-white p-6 text-center">
                <p className="text-[12px] text-sub">{err}</p>
                <button
                  onClick={() => load(type)}
                  className="press mt-3 rounded-pill bg-pink px-5 py-2 text-[12px] text-white"
                >
                  重新加载
                </button>
              </div>
            ) : items === null ? (
              <p className="py-10 text-center text-[12px] text-sub">加载中…</p>
            ) : items.length === 0 ? (
              <Reveal>
                <div className="rounded-card border border-line bg-white p-8 text-center">
                  <IconBell width={30} height={30} className="mx-auto text-line" />
                  <p className="mt-3 text-[12px] text-sub">暂无通知</p>
                </div>
              </Reveal>
            ) : (
              <div className="space-y-2.5">
                {items.map((n, i) => {
                  const meta = TYPE_META[n.type] || TYPE_META.system
                  return (
                    <Reveal key={n.id} delay={i * 140}>
                      <button
                        onClick={() => nav(`/notifications/${n.id}`)}
                        className="flex w-full items-start gap-3 rounded-card border border-line bg-white p-3.5 text-left"
                      >
                        <span
                          className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${meta.icon}`}
                        >
                          <IconBell width={16} height={16} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-1.5">
                            <span className="truncate text-[13px] font-medium text-dark">{n.title}</span>
                            {!n.is_read && <span className="h-2 w-2 shrink-0 rounded-full bg-pink" />}
                          </span>
                          {n.body && <span className="mt-1 block truncate text-[12px] text-sub">{n.body}</span>}
                          <span className="mt-1.5 block text-[10px] text-sub/70">
                            {String(n.created_at || '').slice(0, 16)}
                          </span>
                        </span>
                      </button>
                    </Reveal>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}