import React, { useState, useEffect, useRef } from 'react'
import { LOCATIONS, locateNow } from '../utils/location'
import { IconPin } from './icons'

// 配送位置选择弹层：腾讯地图 GL JS（TMap）选点 → 点击地图拾取坐标 + 逆地理编码填地址；
// 未配置 VITE_TENCENT_MAP_KEY 或地图加载失败时回退浏览器定位 / 预设区域。
// 选点结果 {lat, lng, address} 通过 onConfirm 回调，与收货地址分开存储。
const MAP_KEY = import.meta.env.VITE_TENCENT_MAP_KEY || ''

// 定位针图标（内联 SVG data URI，无外部依赖）
const PIN_SVG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">' +
  '<path d="M14 0C6.3 0 0 6.3 0 14c0 10.5 14 22 14 22s14-11.5 14-22C28 6.3 21.7 0 14 0z" fill="#C39B6A"/>' +
  '<circle cx="14" cy="14" r="6" fill="#ffffff"/></svg>'
)

// 加载腾讯地图 GL JS（挂载到 window.TMap）
function loadTMap() {
  return new Promise((resolve, reject) => {
    if (window.TMap) {
      resolve(window.TMap)
      return
    }
    const script = document.createElement('script')
    script.src = `https://map.qq.com/api/gljs?v=1.exp&key=${MAP_KEY}`
    script.onload = () => (window.TMap ? resolve(window.TMap) : reject(new Error('TMap 未就绪')))
    script.onerror = () => reject(new Error('地图脚本加载失败'))
    document.head.appendChild(script)
  })
}

// 逆地理编码：坐标 → 地址（走后端代理 /geocode，避免腾讯 WebService API 的浏览器 CORS 限制）
async function reverseGeocode(lat, lng) {
  try {
    const res = await fetch(`/api/geocode?lat=${lat}&lng=${lng}`)
    const data = await res.json()
    return data.address || null
  } catch {
    return null
  }
}

export default function DeliveryLocationPicker({ open, onConfirm, onClose }) {
  const [locating, setLocating] = useState(false)
  const [mapStatus, setMapStatus] = useState('idle') // idle|loading|ready|fail
  const [located, setLocated] = useState(null) // {lat, lng} 待确认
  const [address, setAddress] = useState('')
  const [err, setErr] = useState('')
  const mapRef = useRef(null) // TMap.Map 实例
  const markerRef = useRef(null) // TMap.MultiMarker 实例
  const containerRef = useRef(null) // 地图容器 div

  // 初始化腾讯地图（仅配置了 key 且弹层打开时）
  useEffect(() => {
    if (!open || !MAP_KEY) return
    let alive = true
    setMapStatus('loading')
    setErr('')
    loadTMap()
      .then(async (TMap) => {
        if (!alive || !containerRef.current) return
        // 默认中心：深圳南山（后续可跟随浏览器定位）
        const center = new TMap.LatLng(22.533, 113.93)
        const map = new TMap.Map(containerRef.current, {
          center,
          zoom: 12,
          viewMode: '2D',
        })
        mapRef.current = map
        markerRef.current = new TMap.MultiMarker({
          map,
          styles: {
            picked: new TMap.MarkerStyle({
              width: 28,
              height: 36,
              anchor: { x: 14, y: 36 },
              src: PIN_SVG,
            }),
          },
          geometries: [],
        })
        // 点击地图拾取坐标
        map.on('click', async (e) => {
          if (!e.latLng) return
          const lat = e.latLng.lat
          const lng = e.latLng.lng
          setLocated({ lat, lng })
          const addr = await reverseGeocode(lat, lng)
          setAddress(addr || '')
          markerRef.current?.setGeometries([
            { id: 'pick', styleId: 'picked', position: new TMap.LatLng(lat, lng) },
          ])
        })
        setMapStatus('ready')
      })
      .catch((e) => {
        if (alive) {
          setMapStatus('fail')
          setErr(e.message || '地图加载失败，已回退定位')
        }
      })
    return () => {
      alive = false
      // 清理地图实例
      if (mapRef.current) {
        mapRef.current = null
      }
      if (markerRef.current) {
        markerRef.current = null
      }
    }
  }, [open])

  if (!open) return null

  const pick = (loc) => {
    setErr('')
    setLocated(null)
    onConfirm({ lat: loc.lat, lng: loc.lng, address: loc.name || '' })
  }

  // 浏览器定位后：移动地图中心 + 标记 + 逆地理编码
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
      if (mapRef.current) {
        mapRef.current.setCenter(new window.TMap.LatLng(loc.lat, loc.lng))
        markerRef.current?.setGeometries([
          { id: 'pick', styleId: 'picked', position: new window.TMap.LatLng(loc.lat, loc.lng) },
        ])
      }
    } catch (e) {
      setErr(e.message || '定位失败，请选择下方区域')
    } finally {
      setLocating(false)
    }
  }

  const confirmLocated = () => {
    if (!located) return
    onConfirm({ lat: located.lat, lng: located.lng, address: address || '我的位置' })
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
        <p className="mt-1 text-[11px] text-sub">点击地图选点确定配送位置，花店按此计算配送距离</p>

        {/* 地图画布（配置了 key 时显示） */}
        {MAP_KEY && (
          <div className="relative mt-4 overflow-hidden rounded-[4px] border border-line">
            <div
              ref={containerRef}
              style={{ height: '220px', width: '100%' }}
              className="bg-[#E9E5DC]"
            />
            {mapStatus === 'loading' && (
              <p className="absolute inset-0 flex items-center justify-center bg-white/70 text-[12px] text-sub">
                地图加载中…
              </p>
            )}
            {mapStatus === 'fail' && (
              <p className="absolute inset-0 flex items-center justify-center bg-white/80 px-6 text-center text-[11px] text-burgundy">
                地图加载失败，请使用下方定位
              </p>
            )}
          </div>
        )}

        <button
          onClick={locate}
          disabled={locating}
          className="press mt-4 flex h-[46px] w-full items-center justify-center gap-2 rounded-[2px] bg-gold text-[14px] font-medium tracking-wide text-[#FAF8F5] disabled:opacity-60"
        >
          {locating ? (
            '定位中…'
          ) : (
            <>
              <IconPin width={16} height={16} />
              {MAP_KEY ? '定位到我的位置' : '使用我的位置'}
            </>
          )}
        </button>

        {/* 定位/选点结果展示 + 确认 */}
        {located && (
          <div className="mt-3 rounded-[2px] border border-line bg-bg px-4 py-3">
            <p className="text-[12px] font-medium text-ink">
              已选：{address || `${located.lat.toFixed(4)}, ${located.lng.toFixed(4)}`}
            </p>
            <p className="mt-0.5 text-[10px] text-sub/70">坐标：{located.lat.toFixed(4)}, {located.lng.toFixed(4)}</p>
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