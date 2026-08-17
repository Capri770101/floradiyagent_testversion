import React, { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { IconHome, IconChat, IconGrid, IconCart, IconUser, IconStore } from './icons'
import { getProfile, getToken } from '../api/auth'

// 角色缓存：token 不变则不重复请求（登录/登出会换 token，缓存随之失效）
let roleCache = { token: '', role: '' }

const C_TABS = [
  { to: '/', label: '首页', Icon: IconHome },
  { to: '/agent', label: '小兰', Icon: IconChat },
  { to: '/category', label: '分类', Icon: IconGrid },
  { to: '/cart', label: '购物车', Icon: IconCart },
  { to: '/profile', label: '我的', Icon: IconUser },
]

// 商家/管理员：购物车换成「工作台」常驻入口（merchant→商家工作台，admin→管理后台），
// 登录后跳转到工作台也能一键回到 C 端，反之亦然。
// 底部导航 TabBar：高 56，5 项固定（规范 §2.4）
export function TabBar() {
  const location = useLocation()
  const [role, setRole] = useState('')

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

  const isBiz = role === 'merchant' || role === 'admin'
  const tabs = isBiz
    ? [
        { to: '/', label: '首页', Icon: IconHome },
        { to: '/agent', label: '小兰', Icon: IconChat },
        { to: '/category', label: '分类', Icon: IconGrid },
        { to: role === 'admin' ? '/admin' : '/merchant', label: '工作台', Icon: IconStore },
        { to: '/profile', label: '我的', Icon: IconUser },
      ]
    : C_TABS

  return (
    <nav className="tabbar flex h-[56px] shrink-0 items-stretch border-t border-line bg-white">
      {tabs.map(({ to, label, Icon }) => (
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