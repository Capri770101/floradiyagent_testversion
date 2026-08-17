import React from 'react'
import { Routes, Route, Outlet, useNavigate } from 'react-router-dom'
import { TabBar } from './components/TabBar'
import { Button } from './components/Button'
import RequireAuth from './utils/RequireAuth'
import Home from './pages/Home'
import Agent from './pages/Agent'
import DiyDetail from './pages/DiyDetail'
import ProductDetail from './pages/ProductDetail'
import ShopDetail from './pages/ShopDetail'
import OrderConfirm from './pages/OrderConfirm'
import Pay from './pages/Pay'
import Profile from './pages/Profile'
import Service from './pages/Service'
import About from './pages/About'
import Settings from './pages/Settings'
import Category from './pages/Category'
import Cart from './pages/Cart'
import Admin from './pages/Admin'
import Addresses from './pages/Addresses'
import Favorites from './pages/Favorites'
import CouponCenter from './pages/CouponCenter'
import Merchant from './pages/Merchant'
import Logistics from './pages/Logistics'
import Orders from './pages/Orders'

// 404 兜底页：路由未命中时给出明确反馈与返回入口（review 点名缺失）
function NotFound() {
  const nav = useNavigate()
  return (
    <div className="flex h-full flex-col items-center justify-center bg-bg px-8 text-center">
      <p className="font-serif-cn text-[64px] font-medium text-pink/70">404</p>
      <p className="mt-2 text-[13px] text-sub">页面走丢了，回到首页继续逛逛吧</p>
      <div className="mt-6">
        <Button onClick={() => nav('/')}>返回首页</Button>
      </div>
    </div>
  )
}

// 状态栏（Maison 参考稿 §6：模拟原生 App 顶部 9:41 / 5G）
function StatusBar() {
  const [now, setNow] = React.useState(new Date())
  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(t)
  }, [])
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  return (
    <div className="flex h-[34px] shrink-0 items-center justify-between bg-bg px-5 text-[12px] font-medium text-ink">
      <span>{hh}:{mm}</span>
      <span className="flex items-center gap-1">
        <span className="tracking-[2px] text-[9px]">●●●</span>
        <span>5G</span>
        <svg width="16" height="11" viewBox="0 0 16 11" fill="none">
          <rect x="0" y="7" width="2.5" height="4" rx="0.5" fill="currentColor" />
          <rect x="4" y="5" width="2.5" height="6" rx="0.5" fill="currentColor" />
          <rect x="8" y="3" width="2.5" height="8" rx="0.5" fill="currentColor" />
          <rect x="12" y="0" width="2.5" height="11" rx="0.5" fill="currentColor" opacity="0.35" />
        </svg>
      </span>
    </div>
  )
}

// 每个页面底部都显示导航栏（含详情/订单/支付页），保证全局可达。
function Layout() {
  return (
    <div className="app-shell">
      <StatusBar />
      <div className="app-scroll">
        <Outlet />
      </div>
      <TabBar />
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/product/:id" element={<ProductDetail />} />
        <Route path="/shop/:id" element={<ShopDetail />} />
        <Route path="/category" element={<Category />} />
        {/* 涉及个人数据（对话/购物车/订单/收藏/地址/后台）：未登录先跳登录 */}
        <Route
          path="/agent"
          element={
            <RequireAuth>
              <Agent />
            </RequireAuth>
          }
        />
        <Route
          path="/cart"
          element={
            <RequireAuth>
              <Cart />
            </RequireAuth>
          }
        />
        <Route
          path="/order"
          element={
            <RequireAuth>
              <OrderConfirm />
            </RequireAuth>
          }
        />
        <Route
          path="/pay"
          element={
            <RequireAuth>
              <Pay />
            </RequireAuth>
          }
        />
        <Route
          path="/favorites"
          element={
            <RequireAuth>
              <Favorites />
            </RequireAuth>
          }
        />
        <Route path="/coupons" element={<CouponCenter />} />
        <Route
          path="/merchant"
          element={
            <RequireAuth>
              <Merchant />
            </RequireAuth>
          }
        />
        <Route
          path="/logistics/:orderId"
          element={
            <RequireAuth>
              <Logistics />
            </RequireAuth>
          }
        />
        <Route
          path="/orders"
          element={
            <RequireAuth>
              <Orders />
            </RequireAuth>
          }
        />
        <Route
          path="/addresses"
          element={
            <RequireAuth>
              <Addresses />
            </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <Admin />
            </RequireAuth>
          }
        />
        <Route path="/diy/:id" element={<DiyDetail />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/service" element={<Service />} />
        <Route path="/about" element={<About />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
