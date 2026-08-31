// 商家工作台骨架：登录守卫（role=merchant）+ 左侧菜单 + 顶栏 + 内容区。
// 三端独立架构：令牌键 floradiy_merchant_token，与 C 端/管理后台互不干扰。
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { clearToken, fetchProfile, getToken, merchantNotificationsUnreadCount } from './api'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Orders } from './pages/Orders'
import { Customers } from './pages/Customers'
import { Aftersale } from './pages/Aftersale'
import { Notifications } from './pages/Notifications'
import { Withdrawal } from './pages/Withdrawal'
import { Products } from './pages/Products'
import { Profile } from './pages/Profile'

const MENU = [
  { key: 'dashboard', label: '数据看板', sub: '订单 / GMV / 今日经营' },
  { key: 'orders', label: '订单管理', sub: '发货 / 物流' },
  { key: 'customers', label: '顾客会话', sub: '售前咨询回复' },
  { key: 'aftersale', label: '售后处理', sub: '退款 / 退货 / 换货' },
  { key: 'notifications', label: '通知中心', sub: '订单 / 售后 / 系统' },
  { key: 'withdrawal', label: '余额提现', sub: '发起 / 查询提现' },
  { key: 'products', label: '商品管理', sub: '上架 / 下架 / 分类' },
  { key: 'profile', label: '店铺设置', sub: '资料 / 装修 / 评价' },
]

export function MerchantApp() {
  const [user, setUser] = useState(null) // null=未登录/校验中
  const [page, setPage] = useState('dashboard')
  const [contact, setContact] = useState(null) // 订单「联系顾客」请求（{user_id, shop_id, ...}）
  const [checking, setChecking] = useState(true)
  const [unreadCount, setUnreadCount] = useState(0)
  const unreadTimer = useRef(null)

  const verify = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setChecking(false)
      return
    }
    try {
      const u = await fetchProfile()
      if (u && u.role === 'merchant') {
        setUser(u)
      } else {
        clearToken()
        setUser(null)
      }
    } catch (e) {
      setUser(null)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    verify()
  }, [verify])

  // 轮询未读通知数（登录后每 30 秒）
  useEffect(() => {
    if (!user) return
    const poll = async () => {
      try {
        const c = await merchantNotificationsUnreadCount()
        setUnreadCount(c)
      } catch (e) { /* ignore */ }
    }
    poll()
    unreadTimer.current = setInterval(poll, 30000)
    return () => clearInterval(unreadTimer.current)
  }, [user])

  // 进入通知页时清零本地计数
  useEffect(() => {
    if (page === 'notifications') setUnreadCount(0)
  }, [page])

  // 任意接口 401/403 → 回登录
  useEffect(() => {
    const onFail = () => {
      clearToken()
      setUser(null)
    }
    window.addEventListener('merchant:auth-fail', onFail)
    return () => window.removeEventListener('merchant:auth-fail', onFail)
  }, [])

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg text-[13px] text-sub">
        加载中…
      </div>
    )
  }

  if (!user) {
    return <Login onLogin={(u) => setUser(u)} />
  }

  const logout = () => {
    clearToken()
    setUser(null)
  }

  const Page = {
    dashboard: Dashboard,
    orders: Orders,
    customers: Customers,
    aftersale: Aftersale,
    notifications: Notifications,
    withdrawal: Withdrawal,
    products: Products,
    profile: Profile,
  }[page]

  return (
    <div className="flex min-h-screen bg-bg text-ink">
      {/* 左侧菜单 */}
      <aside className="sticky top-0 flex h-screen w-[220px] shrink-0 flex-col border-r border-line bg-white">
        <div className="border-b border-line px-5 py-5">
          <p className="eyebrow">Flora Merchant</p>
          <h1 className="mt-1 font-serif-cn text-[20px] font-normal">商家工作台</h1>
        </div>
        <nav className="flex-1 overflow-y-auto py-3">
          {MENU.map((m) => (
            <button
              key={m.key}
              onClick={() => setPage(m.key)}
              className={`press w-full px-5 py-3 text-left transition ${
                page === m.key ? 'border-l-2 border-gold bg-gold/10' : 'border-l-2 border-transparent hover:bg-bg'
              }`}
            >
              <div className="flex items-center justify-between">
                <p className={`text-[13px] ${page === m.key ? 'font-medium text-gold' : 'text-ink'}`}>{m.label}</p>
                {m.key === 'notifications' && unreadCount > 0 && (
                  <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-burgundy px-1 text-[9px] text-white">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-[10px] text-sub">{m.sub}</p>
            </button>
          ))}
        </nav>
        <div className="border-t border-line px-5 py-4">
          <p className="truncate text-[12px] text-ink">{user.nickname || user.phone || user.username}</p>
          <p className="text-[10px] text-sub">{user.username}</p>
          <button onClick={logout} className="press mt-2 text-[11px] tracking-[1px] text-sub">
            退出登录
          </button>
        </div>
      </aside>

      {/* 内容区 */}
      <main className="min-w-0 flex-1 px-8 py-6">
        <Page
          user={user}
          goTo={(k) => setPage(k)}
          onContact={(o) => {
            setContact(o)
            setPage('customers')
          }}
          contact={contact}
          onContactConsumed={() => setContact(null)}
        />
      </main>
    </div>
  )
}