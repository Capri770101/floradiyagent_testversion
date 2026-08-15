import React, { useState } from 'react'
import { LOCATIONS, locateNow } from '../utils/location'

// 定位选择弹层：浏览器定位 + 预设区域二选一。登录后首屏弹出；首页可随时重新选择。
export default function LocationPicker({ open, onConfirm, onClose }) {
  const [locating, setLocating] = useState(false)
  const [err, setErr] = useState('')

  if (!open) return null

  const pick = (loc) => {
    setErr('')
    onConfirm(loc)
  }

  const locate = async () => {
    setLocating(true)
    setErr('')
    try {
      const loc = await locateNow()
      onConfirm(loc)
    } catch (e) {
      setErr(e.message || '定位失败')
    } finally {
      setLocating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-h5 rounded-t-[24px] bg-white px-5 pb-8 pt-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1 w-9 rounded bg-line" />
        <h3 className="text-[17px] font-medium text-dark">选择收货位置</h3>
        <p className="mt-1 text-[11px] text-sub">确定当前位置后，为你推荐附近的花店与配送距离</p>

        <button
          onClick={locate}
          disabled={locating}
          className="press mt-4 flex h-[46px] w-full items-center justify-center gap-2 rounded-btn bg-pink text-[14px] font-medium text-white disabled:opacity-60"
        >
          {locating ? '定位中…' : '📍 使用我的位置'}
        </button>
        {err && <p className="mt-2 text-center text-[11px] text-pink">{err}</p>}

        <div className="mt-5 grid grid-cols-3 gap-2.5">
          {LOCATIONS.map((loc) => (
            <button
              key={loc.name}
              onClick={() => pick(loc)}
              className="press rounded-[12px] border border-line bg-bg py-3 text-[13px] text-ink"
            >
              {loc.name}
            </button>
          ))}
        </div>

        <button onClick={onClose} className="mt-5 w-full text-center text-[12px] text-sub">
          暂不选择，随便逛逛
        </button>
      </div>
    </div>
  )
}
