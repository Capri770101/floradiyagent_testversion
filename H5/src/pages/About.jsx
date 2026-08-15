import React from 'react'
import { TopBar } from '../components/TopBar'
import { FloraCorner, FloraSprig } from '../components/FloralDecor'

// 关于 FloraDIY：项目介绍
export default function About() {
  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="关于 FloraDIY" />
      <div className="flex-1 overflow-y-auto px-5 pt-4 pb-8">
        <div className="hero-flora relative overflow-hidden rounded-card p-6 shadow-soft">
          <FloraCorner className="absolute left-0 top-0" />
          <FloraSprig className="absolute bottom-0 right-0" />
          <h2 className="text-[20px] font-medium text-dark">FloraDIY</h2>
          <p className="mt-2 text-[12px] leading-relaxed text-ink">
            让每一束花，都为你而开。
          </p>
        </div>
        <div className="mt-5 rounded-card bg-white p-4 shadow-card">
          <p className="text-[13px] font-medium text-dark">FloraDIY 是什么？</p>
          <p className="mt-1.5 text-[12px] leading-relaxed text-sub">
            FloraDIY 是一款 AI 花艺设计平台。告诉我们的智能花艺师你的心意，
            它会结合场景、花语与预算，为你生成专属插花方案、贺卡文案与养护指南，
            并支持在线下单、配送跟踪与售后评价，让送花这件事更有温度。
          </p>
        </div>
        <div className="mt-3 rounded-card bg-white p-4 shadow-card">
          <p className="text-[13px] font-medium text-dark">平台特性</p>
          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[12px] leading-relaxed text-sub">
            <li>AI 花艺师：懂花语、懂场景、懂预算</li>
            <li>一键下单：方案直达本地认证花店</li>
            <li>全链路追踪：支付 → 发货 → 收货 → 评价</li>
            <li>优惠与积分：新人礼券 + 每单返积分</li>
          </ul>
        </div>
        <p className="mt-6 text-center text-[10px] text-sub/60">FloraDIY v1.0 · 让花语更懂人心</p>
      </div>
    </div>
  )
}