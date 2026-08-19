import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { IconBell } from '../components/icons'
import Reveal from '../components/Reveal'
import { getNotification, markRead } from '../api/notify'

// 通知详情页（NEW_FEATURES 模块一，任务书 §2.4）：
// - onMount 即 markRead([id])（进入即视为已读）。
// - 展示标题/正文/时间，可跳转到关联业务页（jumpRef）。

const TYPE_LABEL = {
  order_status: '订单',
  logistics: '物流',
  review_reply: '评价',
  aftersale: '售后',
  announcement: '公告',
  system: '系统',
}

export default function NotificationDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [item, setItem] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!id) return
    markRead([id]).catch(() => {})
    getNotification(id)
      .then(setItem)
      .catch((e) => setErr(e.message || '消息不存在或已被删除'))
  }, [id])

  // 点击通知 → jumpRef（任务书 §2.4）：物流 → /logistics/:orderId；
  // 订单/评价回复 → /orders；售后 → /my-aftersales；方案/店铺 → 详情页；公告/系统不跳转。
  const jumpRef = () => {
    if (!item) return
    if (item.type === 'logistics' && item.ref_id) nav(`/logistics/${item.ref_id}`)
    else if (item.ref_type === 'aftersale') nav('/my-aftersales')
    else if (item.ref_type === 'order' && item.ref_id) nav('/orders')
    else if (item.ref_type === 'plan' && item.ref_id) nav(`/product/${item.ref_id}`)
    else if (item.ref_type === 'shop' && item.ref_id) nav(`/shop/${item.ref_id}`)
  }

  const jumpLabel = () => {
    if (!item) return ''
    if (item.type === 'logistics') return '查看物流详情'
    if (item.ref_type === 'aftersale') return '查看我的售后'
    if (item.ref_type === 'order') return '查看我的订单'
    if (item.ref_type === 'plan') return '查看方案'
    if (item.ref_type === 'shop') return '查看店铺'
    return ''
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="通知详情" />
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {err ? (
          <Reveal>
          <div className="rounded-card border border-line bg-white p-8 text-center">
            <IconBell width={30} height={30} className="mx-auto text-line" />
            <p className="mt-3 text-[12px] text-sub">{err}</p>
            <Button variant="secondary" className="mt-4" onClick={() => nav(-1)}>
              返回
            </Button>
          </div>
          </Reveal>
        ) : !item ? (
          <p className="py-10 text-center text-[12px] text-sub">加载中…</p>
        ) : (
          <Reveal>
          <div className="rounded-card border border-line bg-white p-5">
            <p className="eyebrow">{TYPE_LABEL[item.type] || '通知'}</p>
            <h2 className="mt-2 font-serif-cn text-[20px] leading-snug text-ink">{item.title}</h2>
            {item.body && <p className="mt-3 text-[13px] leading-relaxed text-sub">{item.body}</p>}
            <p className="mt-4 text-[10px] text-sub/70">{item.created_at}</p>
            {jumpLabel() && (
              <Button className="mt-5 w-full" onClick={jumpRef}>
                {jumpLabel()}
              </Button>
            )}
          </div>
          </Reveal>
        )}
      </div>
    </div>
  )
}