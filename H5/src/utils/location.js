// 定位工具：用户选择/浏览器的当前位置，持久化到 localStorage。
// 首页/分类/店铺列表按此定位排序与展示距离；对话也会带上定位（search_shops 用）。
// 定位未选择时各功能回退到静态 distance_km，不影响演示。

// 预设城市区域（演示用；真实上线可接地图选点 SDK）
export const LOCATIONS = [
  { name: '盐田区', lat: 22.565, lng: 114.238 },
  { name: '福田区', lat: 22.541, lng: 114.055 },
  { name: '南山区', lat: 22.533, lng: 113.93 },
  { name: '罗湖区', lat: 22.548, lng: 114.131 },
  { name: '宝安区', lat: 22.555, lng: 113.884 },
  { name: '龙岗区', lat: 22.721, lng: 114.247 },
]

const KEY = 'floradiy_location'

export function getLocation() {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setLocation(loc) {
  localStorage.setItem(KEY, JSON.stringify(loc))
}

export function clearLocation() {
  localStorage.removeItem(KEY)
}

export function locationName() {
  const loc = getLocation()
  return loc ? loc.name || '我的位置' : ''
}

// 浏览器 Geolocation 定位（localhost 可用；失败时由调用方回退到预设）
export function locateNow() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('当前浏览器不支持定位'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          name: '我的位置',
          lat: Number(pos.coords.latitude.toFixed(4)),
          lng: Number(pos.coords.longitude.toFixed(4)),
        }),
      (err) => reject(new Error(`定位失败：${err.message}`)),
      { timeout: 8000, maximumAge: 300000 },
    )
  })
}
