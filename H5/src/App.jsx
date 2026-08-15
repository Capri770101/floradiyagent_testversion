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

// 每个页面底部都显示导航栏（含详情/订单/支付页），保证全局可达。
function Layout() {
  return (
    <div className="app-shell">
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
