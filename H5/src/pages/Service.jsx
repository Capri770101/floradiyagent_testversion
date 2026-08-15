import React from 'react'
import { TopBar } from '../components/TopBar'

// 客服中心：静态服务信息页（FAQ 入口 + 联系方式）
const FAQS = [
  { q: '下单后多久发货？', a: '支付成功后 24 小时内由花店发货，配送时间 1-3 天，节假日顺延。' },
  { q: '花束可以指定配送时间吗？', a: '可以，在确认订单页填写期望配送时间，花店会按备注安排。' },
  { q: '收到的花不满意怎么办？', a: '可在订单完成后评价并联系客服，我们将按流程处理退换。' },
  { q: '积分有什么用？', a: '每笔支付都会返还积分，未来可在积分商城兑换鲜花券与周边。' },
]

export default function Service() {
  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="客服中心" />
      <div className="flex-1 overflow-y-auto px-5 pt-4 pb-8">
        <h2 className="text-[16px] font-medium text-dark">常见问题</h2>
        <div className="mt-3 space-y-3">
          {FAQS.map((f) => (
            <div key={f.q} className="rounded-card bg-white p-4 shadow-card">
              <p className="text-[13px] font-medium text-dark">Q：{f.q}</p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-sub">A：{f.a}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 rounded-card bg-white p-4 shadow-card">
          <p className="text-[13px] font-medium text-dark">联系客服</p>
          <p className="mt-1.5 text-[12px] leading-relaxed text-sub">
            服务时间：每日 9:00 - 21:00
            <br />
            服务热线：400-800-1234
            <br />
            邮箱：service@floradiy.example.com
          </p>
        </div>
      </div>
    </div>
  )
}