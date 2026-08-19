import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopBar } from '../components/TopBar'
import { Button } from '../components/Button'
import Reveal from '../components/Reveal'
import { toast } from '../utils/toast'
import { clearSession, isLoggedIn, wxBind, inWeChat } from '../api/auth'

const NOTIFY_KEY = 'floradiy_notify'

// 设置：账号 / 通知 / 会员占位 + 微信绑定 + 退出登录
export default function Settings() {
  const nav = useNavigate()
  const [notify, setNotify] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem(NOTIFY_KEY)
    if (saved !== null) setNotify(saved === '1')
  }, [])

  const toggleNotify = () => {
    setNotify((v) => {
      localStorage.setItem(NOTIFY_KEY, v ? '0' : '1')
      return !v
    })
  }

  const logout = () => {
    clearSession()
    toast('已退出登录')
    nav('/profile', { replace: true })
  }

  const bindWx = async () => {
    if (!inWeChat()) {
      toast('请在微信中打开本页面后绑定', 'error')
      return
    }
    try {
      await wxBind()
      toast('微信绑定成功，下次可直接微信登录')
    } catch (e) {
      toast(e.message || '微信绑定失败', 'error')
    }
  }

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar title="设置" />
      <div className="flex-1 overflow-y-auto px-5 pt-4 pb-8">
        <Reveal>
          <div className="overflow-hidden rounded-card bg-white border border-line">
          <div className="flex items-center justify-between px-4 py-3.5">
            <span className="text-[12px] text-ink">账号状态</span>
            <span className="text-[12px] text-sub">{isLoggedIn() ? '已登录' : '未登录'}</span>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3.5">
            <span className="text-[12px] text-ink">接收消息推送</span>
            <button
              role="switch"
              aria-checked={notify}
              aria-label="接收消息推送"
              onClick={toggleNotify}
              className={`relative h-[22px] w-[38px] rounded-full transition-colors ${
                notify ? 'bg-pink' : 'bg-line'
              }`}
            >
              <span
                className={`absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white shadow transition-all ${
                  notify ? 'left-[18px]' : 'left-[2px]'
                }`}
              />
            </button>
          </div>
          <p className="border-t border-line px-4 py-2 text-[10px] text-sub/60">
            消息偏好仅作预留：本期所有消息统一在「消息通知」站内收件箱查看
          </p>
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
          {isLoggedIn() && (
            <div className="flex items-center justify-between border-t border-line px-4 py-3.5">
              <span className="text-[12px] text-ink">绑定微信</span>
              <span
                role="button"
                tabIndex={0}
                className="cursor-pointer text-[12px] text-pink"
                onClick={bindWx}
              >
                去绑定
              </span>
            </div>
          )}
        </div>
        </Reveal>
        <Reveal delay={140}>
        <Button
          variant="secondary"
          className="mt-6 w-full"
          disabled={!isLoggedIn()}
          onClick={logout}
        >
          退出登录
        </Button>
        </Reveal>
        <Reveal delay={220}>
        <div className="mt-4 text-center">
          <img
            src="/images/brand/logo.jpg"
            alt="跳舞兰"
            className="mx-auto h-8 w-8 rounded-full border border-line bg-white object-cover"
          />
          <p className="mt-2 text-[10px] text-sub/60">跳舞兰 v1.0</p>
        </div>
        </Reveal>
      </div>
    </div>
  )
}