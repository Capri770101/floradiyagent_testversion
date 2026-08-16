import React from 'react'
import { TopBar } from '../components/TopBar'

// 关于 MAISON·FLORA：品牌介绍（轻奢花艺）
export default function About() {
  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="关于 MAISON·FLORA" />
      <div className="flex-1 overflow-y-auto px-5 pt-5 pb-10">
        {/* 品牌卡：衬线 logo + 金句 */}
        <div className="hero-flora rounded-[4px] px-6 py-8 text-center">
          <img
            src="/images/brand/logo.jpg"
            alt="跳舞兰"
            className="mx-auto h-14 w-14 rounded-full border border-line bg-white object-cover shadow-soft"
          />
          <p className="eyebrow mt-3">Atelier de Fleurs</p>
          <h2 className="mt-2 font-serif-cn text-[26px] font-normal text-ink">MAISON·FLORA</h2>
          <p className="mt-3 font-serif-cn text-[15px] font-normal text-ink/80">
            真正的奢侈，是把时间，
            <br />
            温柔地交还给一朵花。
          </p>
          <p className="quote-credit mt-4">— MAISON·FLORA —</p>
        </div>

        <div className="mt-8 rounded-[4px] border border-line bg-white p-5">
          <p className="text-[13px] font-medium text-ink">MAISON·FLORA 是什么？</p>
          <p className="mt-2 text-[12px] leading-relaxed text-sub">
            MAISON·FLORA 是一家轻奢 AI 花艺设计平台。告诉我们的智能花艺师你的心意，
            它会结合场景、花语与预算，为你生成专属插花方案、贺卡文案与养护指南，
            并支持在线下单、配送跟踪与售后评价，让送花这件事更有仪式感。
          </p>
        </div>
        <div className="mt-5 rounded-[4px] border border-line bg-white p-5">
          <p className="text-[13px] font-medium text-ink">平台特性</p>
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[12px] leading-relaxed text-sub">
            <li>AI 花艺师：懂花语、懂场景、懂预算</li>
            <li>一键下单：方案直达本地认证花店</li>
            <li>全链路追踪：支付 → 发货 → 收货 → 评价</li>
            <li>优惠与积分：新人礼券 + 每单返积分</li>
          </ul>
        </div>
        <p className="mt-8 text-center text-[10px] tracking-[0.2em] text-sub/70">
          MAISON·FLORA v1.0 · 让花语更懂人心
        </p>
      </div>
    </div>
  )
}
