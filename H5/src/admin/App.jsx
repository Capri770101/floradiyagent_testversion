// 管理后台应用骨架：登录守卫（role=admin）+ 左侧菜单 + 顶栏 + 内容区。
import React, { useCallback, useEffect, useState } from 'react'
import { api, clearToken, fetchProfile, getToken } from './api'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Users } from './pages/Users'
import { Orders } from './pages/Orders'
import { Aftersales } from './pages/Aftersales'
import { MerchantApply } from './pages/MerchantApply'
import { Reviews } from './pages/Reviews'
import { Config } from './pages/Config'
import { Content } from './pages/Content'

const MENU = [
  { key: 'dashboard', label: '数据看板', sub: 'GMV / 订单 / 热销' },
  { key: 'users', label: '用户管理', sub: '禁用 / 提权' },
  { key: 'orders', label: '订单管理', sub: '全局视角 / 状态干预' },
  { key: 'aftersales', label: '售后管理', sub: '退款 / 退货 / 换货' },
  { key: 'apply', label: '商家入驻', sub: '审核申请 / 已入驻' },
  { key: 'reviews', label: '评价审核', sub: '隐藏 / 显示 / 删除' },
  { key: 'config', label: '运营配置', sub: '配送时段 / 运费' },
  { key: 'content', label: '内容管理', sub: 'FAQ / 公告 / 分类' },
]

export function AdminApp() {
  const [user, setUser] = useState(null) // null=未登录/校验中
  const [page, setPage] = useState('dashboard')
  const [checking, setChecking] = useState(true)

  const verify = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setChecking(false)
      return
    }
    try {
      const u = await fetchProfile()
      if (u && u.role === 'admin') {
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

  // 任意接口 401/403 → 回登录
  useEffect(() => {
    const onFail = () => {
      clearToken()
      setUser(null)
    }
    window.addEventListener('admin:auth-fail', onFail)
    return () => window.removeEventListener('admin:auth-fail', onFail)
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
    users: Users,
    orders: Orders,
    aftersales: Aftersales,
    apply: MerchantApply,
    reviews: Reviews,
    config: Config,
    content: Content,
  }[page]

  return (
    <div className="flex min-h-screen bg-bg text-ink">
      {/* 左侧菜单 */}
      <aside className="sticky top-0 flex h-screen w-[220px] shrink-0 flex-col border-r border-line bg-white">
        <div className="border-b border-line px-5 py-5">
          <p className="eyebrow">Flora Console</p>
          <h1 className="mt-1 font-serif-cn text-[20px] font-normal">管理后台</h1>
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
              <p className={`text-[13px] ${page === m.key ? 'font-medium text-gold' : 'text-ink'}`}>{m.label}</p>
              <p className="mt-0.5 text-[10px] text-sub">{m.sub}</p>
            </button>
          ))}
        </nav>
        <div className="border-t border-line px-5 py-4">
          <p className="truncate text-[12px] text-ink">{user.nickname || user.username}</p>
          <p className="text-[10px] text-sub">{user.username}</p>
          <button onClick={logout} className="press mt-2 text-[11px] tracking-[1px] text-sub">
            退出登录
          </button>
        </div>
      </aside>

      {/* 内容区 */}
      <main className="min-w-0 flex-1 px-8 py-6">
        <Page />
      </main>
    </div>
  )
}

// 通用分页控件
export function Pager({ offset, total, limit, onChange }) {
  const pageNo = Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / limit))
  if (pages <= 1 && total === 0) return null
  return (
    <div className="mt-4 flex items-center justify-between text-[12px] text-sub">
      <span>
        共 {total} 条 · 第 {pageNo}/{pages} 页
      </span>
      <div className="flex gap-2">
        <button
          className="press rounded-[2px] border border-line bg-white px-3 py-1.5 disabled:opacity-40"
          disabled={pageNo <= 1}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          上一页
        </button>
        <button
          className="press rounded-[2px] border border-line bg-white px-3 py-1.5 disabled:opacity-40"
          disabled={pageNo >= pages}
          onClick={() => onChange(offset + limit)}
        >
          下一页
        </button>
      </div>
    </div>
  )
}

export { api }
