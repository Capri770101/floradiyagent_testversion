import React from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import { toast } from '../utils/toast'
import { clearSession, isLoggedIn } from '../api/auth'

// 设置：账号 / 通知 / 会员占位 + 退出登录
export default function Settings() {
  const nav = useNavigate()

  const logout = () => {
    clearSession()
    toast('已退出登录')
    nav('/profile', { replace: true })
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="设置" />
      <div className="flex-1 overflow-y-auto px-5 pt-4 pb-8">
        <div className="overflow-hidden rounded-card bg-white shadow-card">
          <div className="flex items-center justify-between px-4 py-3.5">
            <span className="text-[12px] text-ink">账号状态</span>
            <span className="text-[12px] text-sub">{isLoggedIn() ? '已登录' : '未登录'}</span>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3.5">
            <span className="text-[12px] text-ink">新订单通知</span>
            <span className="text-[12px] text-sub">开启</span>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3.5">
            <span className="text-[12px] text-ink">收货地址管理</span>
            <span
              role="button"
              tabIndex={0}
              className="cursor-pointer text-[12px] text-pink"
              onClick={() => nav('/addresses')}
            >
              去管理
            </span>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3.5">
            <span className="text-[12px] text-ink">会员中心</span>
            <span
              role="button"
              tabIndex={0}
              className="cursor-pointer text-[12px] text-pink"
              onClick={() => toast('会员中心即将上线，敬请期待')}
            >
              立即开通
            </span>
          </div>
        </div>
        <Button
          variant="secondary"
          className="mt-6 w-full"
          disabled={!isLoggedIn()}
          onClick={logout}
        >
          退出登录
        </Button>
        <p className="mt-4 text-center text-[10px] text-sub/60">FloraDIY v1.0</p>
      </div>
    </div>
  )
}