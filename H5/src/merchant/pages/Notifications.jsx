// 商家通知中心：站内通知列表 + 已读/全部已读。
import React, { useCallback, useEffect, useState } from 'react'
import { merchantNotifications, merchantNotificationsUnreadCount, merchantMarkNotificationsRead } from '../api'

const TYPE_META = {
  order_status: { label: '订单', cls: 'bg-teal/15 text-teal' },
  logistics: { label: '物流', cls: 'bg-ink/10 text-ink' },
  review_reply: { label: '评价', cls: 'bg-gold/15 text-gold' },
  aftersale: { label: '售后', cls: 'bg-burgundy/10 text-burgundy' },
  announcement: { label: '公告', cls: 'bg-bg text-sub' },
  system: { label: '系统', cls: 'bg-bg text-sub' },
}

export function Notifications() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [unreadCount, setUnreadCount] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const [list, count] = await Promise.all([
        merchantNotifications(),
        merchantNotificationsUnreadCount(),
      ])
      setItems(list)
      setUnreadCount(count)
    } catch (e) {
      setErr(e.message || '通知加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const markAll = async () => {
    try {
      await merchantMarkNotificationsRead(null, true)
      setUnreadCount(0)
      setItems((prev) => prev.map((n) => ({ ...n, is_read: 1 })))
    } catch (e) {
      setErr(e.message)
    }
  }

  const markOne = async (id) => {
    try {
      await merchantMarkNotificationsRead([id])
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: 1 } : n)))
      setUnreadCount((c) => Math.max(0, c - 1))
    } catch (e) {
      /* ignore */
    }
  }

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif-cn text-[22px] font-normal text-ink">通知中心</h2>
        {unreadCount > 0 && (
          <button onClick={markAll} className="text-[11px] tracking-[1px] text-gold">
            全部已读（{unreadCount}）
          </button>
        )}
      </div>

      {err && <p className="mt-3 text-[12px] text-burgundy">{err}</p>}

      <div className="mt-4 space-y-2">
        {loading ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">加载中…</p>
        ) : items.length === 0 ? (
          <p className="rounded-card border border-line bg-white p-8 text-center text-[12px] text-sub">暂无通知</p>
        ) : (
          items.map((n) => {
            const t = TYPE_META[n.type] || { label: n.type, cls: 'bg-bg text-sub' }
            const isUnread = !n.is_read
            return (
              <button
                key={n.id}
                onClick={() => isUnread && markOne(n.id)}
                className={`w-full rounded-card border p-4 text-left transition ${
                  isUnread ? 'border-gold/30 bg-gold/5' : 'border-line bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`rounded-pill px-2 py-0.5 text-[10px] ${t.cls}`}>{t.label}</span>
                    {isUnread && <span className="h-1.5 w-1.5 rounded-full bg-gold" />}
                  </div>
                  <span className="text-[10px] text-sub">
                    {n.created_at?.replace('T', ' ').slice(0, 16) || ''}
                  </span>
                </div>
                <p className="mt-1.5 text-[13px] font-medium text-ink">{n.title}</p>
                {n.body && <p className="mt-1 text-[11px] text-sub">{n.body}</p>}
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
