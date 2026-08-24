import React, { useState, useEffect, useRef } from 'react'
import { IconPin } from './icons'

// 收货/配送位置一体选择器：搜索框（TMap Suggestion 匹配）+ 地图联动。
// - 输入搜索 → 弹地点建议 → 选中后地图定位到该点 + 打点 + 回填地址
// - 点击地图 → 逆地理编码填地址
// - 受控：value={address}, onChange(address), onConfirm({lat,lng,address})
// 未配置 VITE_TENCENT_MAP_KEY 时退化为普通搜索/文本输入。
const MAP_KEY = import.meta.env.VITE_TENCENT_MAP_KEY || ''

const PIN_SVG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">' +
  '<path d="M14 0C6.3 0 0 6.3 0 14c0 10.5 14 22 14 22s14-11.5 14-22C28 6.3 21.7 0 14 0z" fill="#C39B6A"/>' +
  '<circle cx="14" cy="14" r="6" fill="#ffffff"/></svg>'
)

function loadTMap() {
  return new Promise((resolve, reject) => {
    if (window.TMap?.service?.Geocoder && window.TMap?.service?.Suggestion) {
      resolve(window.TMap)
      return
    }
    const script = document.createElement('script')
    script.src = `https://map.qq.com/api/gljs?v=1.exp&key=${MAP_KEY}&libraries=service`
    script.onload = () => (window.TMap ? resolve(window.TMap) : reject(new Error('TMap 未就绪')))
    script.onerror = () => reject(new Error('地图脚本加载失败'))
    document.head.appendChild(script)
  })
}

async function reverseGeocode(lat, lng, TMap) {
  if (TMap?.service?.Geocoder) {
    try {
      const geocoder = new TMap.service.Geocoder()
      const res = await geocoder.getAddress({ location: new TMap.LatLng(lat, lng) })
      const addr = res?.result?.address
      if (addr) return addr
    } catch {
      // 回退后端代理
    }
  }
  try {
    const res = await fetch(`/api/geocode?lat=${lat}&lng=${lng}`)
    const data = await res.json()
    return data.address || null
  } catch {
    return null
  }
}

export default function AddressLocationPicker({
  value,
  onChange,
  onConfirm,
  placeholder = '输入地址或在地图选点',
  region = '深圳',
}) {
  const [suggestions, setSuggestions] = useState([])
  const [sugOpen, setSugOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [mapStatus, setMapStatus] = useState('idle')
  const [err, setErr] = useState('')
  const timerRef = useRef(null)
  const TMapRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const containerRef = useRef(null)

  // 初始化地图
  useEffect(() => {
    if (!MAP_KEY) return
    let alive = true
    loadTMap()
      .then(async (TMap) => {
        TMapRef.current = TMap
        if (!alive || !containerRef.current) return
        setMapStatus('loading')
        const map = new TMap.Map(containerRef.current, {
          center: new TMap.LatLng(22.533, 113.93),
          zoom: 12,
          viewMode: '2D',
        })
        mapRef.current = map
        markerRef.current = new TMap.MultiMarker({
          map,
          styles: {
            picked: new TMap.MarkerStyle({ width: 28, height: 36, anchor: { x: 14, y: 36 }, src: PIN_SVG }),
          },
          geometries: [],
        })
        map.on('click', async (e) => {
          if (!e.latLng) return
          const lat = e.latLng.lat
          const lng = e.latLng.lng
          const addr = await reverseGeocode(lat, lng, TMap)
          if (onChange) onChange(addr || '')
          if (onConfirm) onConfirm({ lat, lng, address: addr || '' })
          setMarker(TMap, lat, lng)
        })
        setMapStatus('ready')
      })
      .catch((e) => {
        if (alive) {
          setMapStatus('fail')
          setErr(e.message || '地图加载失败')
        }
      })
    return () => {
      alive = false
      mapRef.current = null
      markerRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const setMarker = (TMap, lat, lng) => {
    if (!markerRef.current) return
    markerRef.current.setGeometries([
      { id: 'pick', styleId: 'picked', position: new TMap.LatLng(lat, lng) },
    ])
  }

  const search = async (kw) => {
    if (!kw.trim()) {
      setSuggestions([])
      setSugOpen(false)
      return
    }
    let T = TMapRef.current
    if (!T?.service?.Suggestion) {
      try {
        T = await loadTMap()
        TMapRef.current = T
      } catch {
        return
      }
    }
    setBusy(true)
    try {
      const suggest = new T.service.Suggestion({ pageSize: 8 })
      const res = await suggest.getSuggestions({ keyword: kw.trim(), region })
      const list = (res?.data || [])
        .filter((it) => it.title && it.location)
        .map((it) => ({
          title: it.title,
          address: it.address || '',
          lat: it.location.lat,
          lng: it.location.lng,
        }))
      setSuggestions(list)
      setSugOpen(list.length > 0)
    } catch {
      setSuggestions([])
      setSugOpen(false)
    } finally {
      setBusy(false)
    }
  }

  const handleChange = (v) => {
    if (onChange) onChange(v)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => search(v), 300)
    if (!v.trim()) {
      setSuggestions([])
      setSugOpen(false)
    }
  }

  // 选中搜索建议：回填地址 + 地图定位
  const pickSuggestion = (it) => {
    if (onChange) onChange(it.title)
    if (onConfirm) onConfirm({ lat: it.lat, lng: it.lng, address: it.title })
    setSugOpen(false)
    setSuggestions([])
    const T = TMapRef.current
    if (T && mapRef.current) {
      mapRef.current.setCenter(new T.LatLng(it.lat, it.lng))
      setMarker(T, it.lat, it.lng)
    }
  }

  return (
    <div className="space-y-2">
      {/* 搜索框 */}
      <div className="relative">
        <input
          value={value || ''}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          className="maison-field"
        />
        {sugOpen && suggestions.length > 0 && (
          <div className="absolute left-0 right-0 z-30 mt-1 max-h-56 overflow-y-auto rounded-[2px] border border-line bg-white shadow-lg">
            {suggestions.map((it, i) => (
              <button
                key={`${it.lng}-${it.lat}-${i}`}
                type="button"
                onClick={() => pickSuggestion(it)}
                className="block w-full border-b border-line/60 px-3 py-2 text-left last:border-b-0 hover:bg-bg"
              >
                <p className="truncate text-[12px] text-ink">{it.title}</p>
                {it.address && <p className="truncate text-[10px] text-sub">{it.address}</p>}
              </button>
            ))}
          </div>
        )}
        {busy && (
          <p className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-sub/60">搜索中…</p>
        )}
      </div>

      {/* 地图 */}
      {MAP_KEY && (
        <div className="relative z-0 overflow-hidden rounded-[4px] border border-line">
          <div ref={containerRef} style={{ height: '200px', width: '100%' }} className="bg-[#E9E5DC]" />
          {mapStatus === 'loading' && (
            <p className="absolute inset-0 flex items-center justify-center bg-white/70 text-[12px] text-sub">地图加载中…</p>
          )}
          {mapStatus === 'fail' && (
            <p className="absolute inset-0 flex items-center justify-center bg-white/80 px-6 text-center text-[11px] text-burgundy">
              地图加载失败，请直接输入地址
            </p>
          )}
        </div>
      )}
      {err && <p className="text-[11px] text-burgundy">{err}</p>}
      <p className="text-[10px] text-sub/70">输入地址搜索匹配，选中后地图自动定位；也可直接点击地图选点</p>
      {MAP_KEY && (
        <button
          type="button"
          onClick={() => {
            if (!mapRef.current) return
            // 默认定位到当前地图中心并逆地理编码
            const c = mapRef.current.getCenter()
            reverseGeocode(c.lat, c.lng, TMapRef.current).then((addr) => {
              if (onChange) onChange(addr || '')
              if (onConfirm) onConfirm({ lat: c.lat, lng: c.lng, address: addr || '' })
            })
            setMarker(TMapRef.current, c.lat, c.lng)
          }}
          className="press flex w-full items-center justify-center gap-1.5 rounded-[2px] border border-gold/40 py-2 text-[12px] tracking-[1px] text-gold"
        >
          <IconPin width={13} height={13} />
          使用地图中心点
        </button>
      )}
    </div>
  )
}