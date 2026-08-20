import React, { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { IconHome, IconChat, IconGrid, IconCart, IconUser } from './icons'
import { getProfile, getToken, isLoggedIn } from '../api/auth'
import { unreadCount } from '../api/notify'

// 角色缓存：token 不变则不重复请求（登录/登出会换 token，缓存随之失效）
let roleCache = { token: '', role: '' }

const C_TABS = [
  { to: '/', label: '首页', Icon: IconHome },
  { to: '/agent', label: '小兰', Icon: IconChat },
  { to: '/category', label: '分类', Icon: IconGrid },
  { to: '/cart', label: '购物车', Icon: IconCart },
  { to: '/profile', label: '我的', Icon: IconUser, dot: true },
]

// 未读消息红点（任务书 §2.4：启动/切页时拉 unreadCount()，登录态才轮询）
function useUnread(location) {
  const [unread, setUnread] = useState(0)
  useEffect(() => {
    if (!isLoggedIn()) {
      setUnread(0)
      return
    }
    let alive = true
    unreadCount()
      .then((n) => alive && setUnread(n))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [location])
  return unread
}

// 底部导航 TabBar：高 56，5 项固定（规范 §2.4）。
// 三端独立架构：商家工作台已迁移独立入口（merchant.html），C 端不再承载商家导航。
export function TabBar() {
  const location = useLocation()
  const [role, setRole] = useState('')
  const unread = useUnread(location)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      roleCache = { token: '', role: '' }
      setRole('')
      return
    }
    if (token === roleCache.token) {
      setRole(roleCache.role)
      return
    }
    getProfile()
      .then((p) => {
        roleCache = { token, role: p?.role || '' }
        setRole(roleCache.role)
      })
      .catch(() => {})
  }, [location])

  return (
    <nav className="tabbar flex h-[56px] shrink-0 items-stretch border-t border-line bg-white">
      {C_TABS.map(({ to, label, Icon, dot }) => (
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
              <span className="relative">
                <Icon width={20} height={20} strokeWidth={isActive ? 2.1 : 1.8} />
                {dot && unread > 0 && (
                  <span className="absolute -right-1.5 -top-1 h-2 w-2 rounded-full bg-pink ring-2 ring-white" />
                )}
              </span>
              <span className="text-[10px]">{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}