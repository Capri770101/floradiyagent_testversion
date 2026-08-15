import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { isLoggedIn } from '../api/auth'

// 登录守卫：涉及个人数据（对话/购物车/订单/收藏/地址/后台）的路由，
// 未登录一律重定向到 /profile（登录/注册页），登录成功后跳回原页面。
export default function RequireAuth({ children }) {
  const location = useLocation()
  if (!isLoggedIn()) {
    return <Navigate to="/profile" state={{ from: location.pathname }} replace />
  }
  return children
}