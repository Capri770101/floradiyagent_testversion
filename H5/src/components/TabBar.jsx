import React from 'react'
import { NavLink } from 'react-router-dom'
import { IconHome, IconChat, IconGrid, IconCart, IconUser } from './icons'

const TABS = [
  { to: '/', label: '首页', Icon: IconHome },
  { to: '/agent', label: '小兰', Icon: IconChat },
  { to: '/category', label: '分类', Icon: IconGrid },
  { to: '/cart', label: '购物车', Icon: IconCart },
  { to: '/profile', label: '我的', Icon: IconUser },
]

// 底部导航 TabBar：高 56，5 项固定（规范 §2.4）
export function TabBar() {
  return (
    <nav className="tabbar flex h-[56px] shrink-0 items-stretch border-t border-line bg-white">
      {TABS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `press flex flex-1 flex-col items-center justify-center gap-0.5 ${
              isActive ? 'text-pink' : 'text-sub'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon width={20} height={20} strokeWidth={isActive ? 2.1 : 1.8} />
              <span className="text-[10px]">{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
