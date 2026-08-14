// 轻量 toast：替代原生 alert()，不阻塞交互、移动端友好。
// 无 context 依赖，任意模块直接 import { toast } 调用即可。

let host = null

function ensureHost() {
  if (host && document.body.contains(host)) return host
  host = document.createElement('div')
  host.style.cssText =
    'position:fixed;left:50%;bottom:92px;transform:translateX(-50%);z-index:9999;' +
    'display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;'
  document.body.appendChild(host)
  return host
}

/**
 * 弹出一条轻提示。
 * @param {string} message 文案
 * @param {'info'|'error'} [type='info'] error 用红色背景
 */
export function toast(message, type = 'info') {
  if (typeof document === 'undefined') return
  const el = document.createElement('div')
  const bg = type === 'error' ? 'rgba(180,60,60,0.92)' : 'rgba(51,51,51,0.92)'
  el.textContent = message
  el.style.cssText =
    `max-width:80vw;padding:10px 16px;border-radius:12px;color:#fff;font-size:13px;` +
    `background:${bg};box-shadow:0 6px 20px rgba(0,0,0,0.18);opacity:0;` +
    `transform:translateY(8px);transition:opacity .22s ease,transform .22s ease;`
  ensureHost().appendChild(el)
  requestAnimationFrame(() => {
    el.style.opacity = '1'
    el.style.transform = 'translateY(0)'
  })
  setTimeout(() => {
    el.style.opacity = '0'
    el.style.transform = 'translateY(8px)'
    setTimeout(() => el.remove(), 240)
  }, 2400)
}
