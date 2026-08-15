import React, { useState } from 'react'
import { LOCATIONS, locateNow } from '../utils/location'
import { IconPin } from './icons'

// 定位选择弹层：浏览器定位（先展示结果再确认）或预设区域。登录后首屏弹出；首页可随时重选。
export default function LocationPicker({ open, onConfirm, onClose }) {
  const [locating, setLocating] = useState(false)
  const [located, setLocated] = useState(null) // 定位成功待确认
  const [err, setErr] = useState('')

  if (!open) return null

  const pick = (loc) => {
    setErr('')
    setLocated(null)
    onConfirm(loc)
  }

  const locate = async () => {
    setLocating(true)
    setErr('')
    setLocated(null)
    try {
      const loc = await locateNow()
      setLocated(loc)
    } catch (e) {
      setErr(e.message || '定位失败，请选择下方区域')
    } finally {
      setLocating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-h5 rounded-t-[4px] bg-white px-5 pb-8 pt-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-[2px] w-9 bg-gold" />
        <h3 className="text-[17px] font-medium text-ink">选择收货位置</h3>
        <p className="mt-1 text-[11px] text-sub">确定当前位置后，为你推荐附近的花店与配送距离</p>

        <button
          onClick={locate}
          disabled={locating}
          className="press mt-5 flex h-[46px] w-full items-center justify-center gap-2 rounded-[2px] bg-gold text-[14px] font-medium tracking-wide text-[#FAF8F5] disabled:opacity-60"
        >
          {locating ? (
            '定位中…'
          ) : (
            <>
              <IconPin width={16} height={16} />
              使用我的位置
            </>
          )}
        </button>

        {/* 定位结果展示 + 确认 */}
        {located && (
          <div className="mt-4 rounded-[2px] border border-line bg-bg px-4 py-3">
            <p className="text-[12px] font-medium text-ink">
              已定位：{located.name}（{located.lat}, {located.lng}）
            </p>
            <div className="mt-3 flex items-center gap-3">
              <button
                onClick={() => pick(located)}
                className="flex-1 rounded-[2px] bg-dark py-2.5 text-[12px] font-medium tracking-wide text-[#FAF8F5]"
              >
                确认使用
              </button>
              <button onClick={locate} className="flex-1 rounded-[2px] border border-line py-2.5 text-[12px] text-ink">
                重新定位
              </button>
            </div>
          </div>
        )}
        {err && <p className="mt-2 text-center text-[11px] text-burgundy">{err}</p>}

        <div className="mt-6 grid grid-cols-3 gap-2.5">
          {LOCATIONS.map((loc) => (
            <button
              key={loc.name}
              onClick={() => pick(loc)}
              className="press rounded-[2px] border border-line bg-white py-3 text-[13px] text-ink"
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
