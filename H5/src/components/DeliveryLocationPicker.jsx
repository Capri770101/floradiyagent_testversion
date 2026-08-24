import React, { useState, useEffect } from 'react'
import { LOCATIONS, locateNow } from '../utils/location'
import { IconPin } from './icons'

// 配送位置选择弹层：腾讯地图选点（需 VITE_TENCENT_MAP_KEY）→ 逆地理编码填地址；
// 未配置 key 或定位失败时回退浏览器定位 / 预设区域。
// 选点结果 {lat, lng, address} 通过 onConfirm 回调，与收货地址分开存储。
const MAP_KEY = import.meta.env.VITE_TENCENT_MAP_KEY || ''

function loadTencentMapScript() {
  return new Promise((resolve, reject) => {
    if (window.QQMapWX || window.qq?.maps) {
      resolve(window.qq)
      return
    }
    const script = document.createElement('script')
    script.src = `https://map.qq.com/api/gljs?v=1.exp&key=${MAP_KEY}`
    script.onload = () => resolve(window.qq)
    script.onerror = () => reject(new Error('地图加载失败'))
    document.head.appendChild(script)
  })
}

// 逆地理编码：坐标 → 地址（腾讯 WebService API，需 key）
async function reverseGeocode(lat, lng) {
  if (!MAP_KEY) return null
  try {
    const url = `https://apis.map.qq.com/ws/geocoder/v1/?location=${lat},${lng}&key=${MAP_KEY}&get_poi=0`
    const res = await fetch(url)
    const data = await res.json()
    if (data.status === 0 && data.result) {
      const r = data.result
      const addr = r.formatted_addresses?.recommend || r.address || ''
      return addr || null
    }
    return null
  } catch {
    return null
  }
}

export default function DeliveryLocationPicker({ open, onConfirm, onClose }) {
  const [locating, setLocating] = useState(false)
  const [mapReady, setMapReady] = useState(false)
  const [located, setLocated] = useState(null) // 定位成功待确认
  const [address, setAddress] = useState('')
  const [err, setErr] = useState('')

  // 加载腾讯地图（仅配置了 key 时）
  useEffect(() => {
    if (!open || !MAP_KEY) return
    let alive = true
    loadTencentMapScript()
      .then(() => { if (alive) setMapReady(true) })
      .catch(() => { if (alive) setErr('地图加载失败，已回退定位') })
    return () => { alive = false }
  }, [open])

  if (!open) return null

  const pick = (loc) => {
    setErr('')
    setLocated(null)
    onConfirm({ lat: loc.lat, lng: loc.lng, address: loc.name || '' })
  }

  const locate = async () => {
    setLocating(true)
    setErr('')
    setLocated(null)
    setAddress('')
    try {
      const loc = await locateNow()
      const addr = await reverseGeocode(loc.lat, loc.lng)
      setLocated(loc)
      setAddress(addr || '')
    } catch (e) {
      setErr(e.message || '定位失败，请选择下方区域')
    } finally {
      setLocating(false)
    }
  }

  const confirmLocated = () => {
    if (!located) return
    onConfirm({ lat: located.lat, lng: located.lng, address: address || located.name || '' })
    setLocated(null)
    setAddress('')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-h5 rounded-t-[4px] bg-white px-5 pb-8 pt-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-[2px] w-9 bg-gold" />
        <h3 className="text-[17px] font-medium text-ink">选择配送位置</h3>
        <p className="mt-1 text-[11px] text-sub">地图选点确定配送位置，花店按此计算配送距离</p>

        {MAP_KEY && mapReady && (
          <p className="mt-2 rounded-[2px] bg-bg px-3 py-2 text-[11px] text-sub">
            已加载腾讯地图，可在下方地图上点击选点
          </p>
        )}

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
              {MAP_KEY ? '使用我的位置（地图选点）' : '使用我的位置'}
            </>
          )}
        </button>

        {/* 定位结果展示 + 确认 */}
        {located && (
          <div className="mt-4 rounded-[2px] border border-line bg-bg px-4 py-3">
            <p className="text-[12px] font-medium text-ink">
              已定位：{located.name}（{located.lat}, {located.lng}）
            </p>
            {address && <p className="mt-1 text-[11px] text-sub">地址：{address}</p>}
            <div className="mt-3 flex items-center gap-3">
              <button
                onClick={confirmLocated}
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