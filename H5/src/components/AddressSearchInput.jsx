import React, { useState, useRef, useEffect } from 'react'

// 地址搜索输入框：输入时用腾讯地图 TMap.service.Suggestion 返回地点建议，
// 选中后 onPick({title, address, lat, lng}) 回调（用于收货地址/配送位置搜索）。
// 未配置 VITE_TENCENT_MAP_KEY 时退化为普通输入框。
const MAP_KEY = import.meta.env.VITE_TENCENT_MAP_KEY || ''

// 加载腾讯地图 GL JS + service 附加库（挂载到 window.TMap）
function loadTMap() {
  return new Promise((resolve, reject) => {
    if (window.TMap?.service?.Suggestion) {
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

export default function AddressSearchInput({
  value,
  onChange,
  onPick,
  placeholder = '收货地址',
  className = '',
  region = '深圳',
}) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const timerRef = useRef(null)
  const TMapRef = useRef(null)

  // 懒加载 TMap（配置了 key 才加载）
  useEffect(() => {
    if (!MAP_KEY) return
    let alive = true
    loadTMap()
      .then((T) => { if (alive) TMapRef.current = T })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const search = async (kw) => {
    if (!kw.trim()) return
    // TMap 未就绪时先加载
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
      const res = await suggest.getSuggestions({
        keyword: kw.trim(),
        region,
      })
      const list = (res?.data || [])
        .filter((it) => it.title && it.location)
        .map((it) => ({
          title: it.title,
          address: it.address || '',
          lat: it.location.lat,
          lng: it.location.lng,
        }))
      setSuggestions(list)
      setOpen(list.length > 0)
    } catch {
      setSuggestions([])
      setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  const handleChange = (v) => {
    onChange(v)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => search(v), 300)
    if (!v.trim()) {
      setSuggestions([])
      setOpen(false)
    }
  }

  const pick = (it) => {
    onChange(it.title + (it.address ? `（${it.address}）` : ''))
    setOpen(false)
    setSuggestions([])
    if (onPick) onPick(it)
  }

  return (
    <div className="relative">
      <input
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        className={className || 'maison-field'}
      />
      {open && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 z-20 mt-1 overflow-hidden rounded-[2px] border border-line bg-white shadow-lg">
          {suggestions.map((it, i) => (
            <button
              key={`${it.lng}-${it.lat}-${i}`}
              type="button"
              onClick={() => pick(it)}
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
  )
}