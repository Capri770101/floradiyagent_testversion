import React, { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { IconHome, IconChat, IconGrid, IconCart, IconUser, IconStore, IconMenu, IconFlower } from './icons'
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

// 商家/管理员：底部导航换成商家自己的功能（替代无用的 C 端入口）。
// 每项通过 /merchant?tab=xxx 与工作台顶部页签联动；「我的」保留退出登录/账号设置。
const M_TABS = [
  { to: '/merchant', tab: '', label: '经营', Icon: IconStore },
  { to: '/merchant', tab: 'orders', label: '订单', Icon: IconMenu },
  { to: '/merchant', tab: 'plans', label: '商品', Icon: IconFlower },
  { to: '/merchant', tab: 'chats', label: '会话', Icon: IconChat },
  { to: '/profile', label: '我的', Icon: IconUser },
]

// 底部导航 TabBar：高 56，5 项固定（规范 §2.4）
export function TabBar() {
  const location = useLocation()
  const nav = useNavigate()
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
  if (isBiz) {
    const activeTab = new URLSearchParams(location.search).get('tab') || ''
    return (
      <nav className="tabbar flex h-[56px] shrink-0 items-stretch border-t border-line bg-white">
        {M_TABS.map(({ to, tab, label, Icon }) => {
          const active = tab === undefined ? location.pathname === to : location.pathname === to && activeTab === tab
          return (
            <button
              key={`${to}${tab || ''}`}
              onClick={() => nav(tab === undefined ? to : tab ? `${to}?tab=${tab}` : to)}
              className={`press flex flex-1 flex-col items-center justify-center gap-0.5 ${
                active ? 'text-pink' : 'text-sub'
              }`}
            >
              <Icon width={20} height={20} strokeWidth={active ? 2.1 : 1.8} />
              <span className="text-[10px]">{label}</span>
            </button>
          )
        })}
      </nav>
    )
  }

  return (
    <nav className="tabbar flex h-[56px] shrink-0 items-stretch border-t border-line bg-white">
      {C_TABS.map(({ to, label, Icon }) => (
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