import React, { useEffect, useState } from 'react'
import { TopBar } from '../components/TopBar'
import Reveal from '../components/Reveal'
import { publicConfig } from '../api/shop'

// 客服中心：FAQ 与公告由运营配置后端下发（红线2：不写死在页面）
export default function Service() {
  const [faqs, setFaqs] = useState([])
  const [announcements, setAnnouncements] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    publicConfig()
      .then((cfg) => {
        setFaqs(cfg.faqs || [])
        setAnnouncements(cfg.announcements || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

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
                  <div className="rounded-card bg-white p-4 border border-line">
                    <p className="text-[12px] leading-relaxed text-sub">{a.content}</p>
                  </div>
                </Reveal>
              ))}
            </div>
            <div className="mt-6" />
          </>
        )}

        <Reveal delay={120}>
          <h2 className="text-[16px] font-medium text-dark">常见问题</h2>
        </Reveal>
        {loading ? (
          <p className="mt-3 rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
            加载中…
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {faqs.map((f, i) => (
              <Reveal key={f.q} delay={200 + i * 140}>
                <div className="rounded-card bg-white p-4 border border-line">
                  <p className="text-[13px] font-medium text-dark">Q：{f.q}</p>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-sub">A：{f.a}</p>
                </div>
              </Reveal>
            ))}
            {faqs.length === 0 && (
              <p className="rounded-card bg-white p-6 text-center text-[12px] text-sub border border-line">
                暂无常见问题
              </p>
            )}
          </div>
        )}

        <Reveal delay={320}>
          <div className="mt-6 rounded-card bg-white p-4 border border-line">
            <p className="text-[13px] font-medium text-dark">联系客服</p>
            <p className="mt-1.5 text-[12px] leading-relaxed text-sub">
              服务时间：每日 9:00 - 21:00
              <br />
              服务热线：400-800-1234
              <br />
              邮箱：service@floradiy.example.com
            </p>
          </div>
        </Reveal>
      </div>
    </div>
  )
}
