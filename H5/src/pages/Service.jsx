import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import Reveal from '../components/Reveal'
import { publicConfig } from '../api/shop'

// 客服中心：FAQ 与公告由运营配置后端下发（红线2：不写死在页面）
const QUICK_ACTIONS = [
  { label: '我的订单', desc: '查看 / 支付订单', to: '/orders' },
  { label: '我的售后', desc: '退款 / 退换进度', to: '/my-aftersales' },
  { label: '消息通知', desc: '物流 / 平台提醒', to: '/notifications' },
  { label: '领券中心', desc: '领取优惠福利', to: '/coupons' },
]

const DEFAULT_SERVICE = {
  hotline: '400-800-1234',
  email: 'service@tiaowulan.com',
  hours: '每日 9:00 - 21:00',
  wechat: 'tiaowulan_service',
}

export default function Service() {
  const nav = useNavigate()
  const [faqs, setFaqs] = useState([])
  const [announcements, setAnnouncements] = useState([])
  const [service, setService] = useState(DEFAULT_SERVICE)
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [open, setOpen] = useState(-1)

  useEffect(() => {
    publicConfig()
      .then((cfg) => {
        setFaqs(cfg.faqs || [])
        setAnnouncements(cfg.announcements || [])
        if (cfg.service) setService({ ...DEFAULT_SERVICE, ...cfg.service })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const k = keyword.trim().toLowerCase()
    if (!k) return faqs
    return faqs.filter(
      (f) => (f.q || '').toLowerCase().includes(k) || (f.a || '').toLowerCase().includes(k),
    )
  }, [faqs, keyword])

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="客服中心" />
      <div className="flex-1 overflow-y-auto px-5 pt-4 pb-8">
        {/* 平台公告 */}
        {announcements.length > 0 && (
          <>
            <Reveal>
              <h2 className="text-[16px] font-medium text-dark">平台公告</h2>
            </Reveal>
            <div className="mt-3 space-y-3">
              {announcements.map((a, i) => (
                <Reveal key={i} delay={i * 140}>
                  <div className="rounded-card border border-line bg-white p-4">
                    <p className="text-[12px] leading-relaxed text-sub">{a.content}</p>
                  </div>
                </Reveal>
              ))}
            </div>
            <div className="mt-6" />
          </>
        )}

        {/* 快捷入口 */}
        <Reveal delay={80}>
          <div className="grid grid-cols-2 gap-3">
            {QUICK_ACTIONS.map((q) => (
              <button
                key={q.to}
                onClick={() => nav(q.to)}
                className="press flex flex-col items-start rounded-card border border-line bg-white p-4 text-left"
              >
                <p className="text-[13px] font-medium text-dark">{q.label}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-sub">{q.desc}</p>
              </button>
            ))}
          </div>
        </Reveal>

        {/* 常见问题 */}
        <Reveal delay={120}>
          <h2 className="mt-7 text-[16px] font-medium text-dark">常见问题</h2>
        </Reveal>
        <div className="mt-3">
          <div className="field-shell flex h-[40px] items-center gap-2 rounded-[2px] border border-line bg-white px-3">
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜索问题关键词"
              className="maison-field-inline flex-1"
            />
          </div>
        </div>
        {loading ? (
          <p className="mt-3 rounded-card border border-line bg-white p-6 text-center text-[12px] text-sub">
            加载中…
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            {filtered.map((f, i) => {
              const isOpen = open === i
              return (
                <Reveal key={f.q} delay={200 + i * 80}>
                  <button
                    onClick={() => setOpen(isOpen ? -1 : i)}
                    className="w-full rounded-card border border-line bg-white p-4 text-left"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[13px] font-medium text-dark">Q：{f.q}</p>
                      <span className={`shrink-0 text-[14px] text-gold transition-transform ${isOpen ? 'rotate-45' : ''}`}>
                        +
                      </span>
                    </div>
                    {isOpen && (
                      <p className="mt-2 text-[12px] leading-relaxed text-sub">A：{f.a}</p>
                    )}
                  </button>
                </Reveal>
              )
            })}
            {filtered.length === 0 && (
              <p className="rounded-card border border-line bg-white p-6 text-center text-[12px] text-sub">
                没有找到相关问题
              </p>
            )}
          </div>
        )}

        {/* 联系客服（来源：后端 publicConfig.service，不写死） */}
        <Reveal delay={320}>
          <div className="mt-7 rounded-card border border-line bg-white p-4">
            <p className="text-[13px] font-medium text-dark">联系客服</p>
            <div className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-sub">
              <p>
                服务时间：{service.hours}
              </p>
              <p>
                服务热线：
                <a href={`tel:${service.hotline}`} className="text-gold-dark underline-offset-2 hover:underline">
                  {service.hotline}
                </a>
              </p>
              <p>
                客服邮箱：
                <a href={`mailto:${service.email}`} className="text-gold-dark underline-offset-2 hover:underline">
                  {service.email}
                </a>
              </p>
              {service.wechat && <p>微信客服：{service.wechat}</p>}
            </div>
          </div>
        </Reveal>
      </div>
    </div>
  )
}
