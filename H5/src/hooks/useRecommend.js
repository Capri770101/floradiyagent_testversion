import { useCallback, useEffect, useRef, useState } from 'react'

// 推荐位通用加载（模块三）：loading/ok/empty/error 四态 + 防竞态，三处推荐位复用。
// fetcher 需返回推荐列表；enabled=false 时不请求（如 DIY 详情在方案数据就绪前）。
export function useRecommend(fetcher, { enabled = true, deps = [] } = {}) {
  const [items, setItems] = useState([])
  const [state, setState] = useState('idle')
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const aliveRef = useRef(true)

  const load = useCallback(async () => {
    if (!enabled) {
      setItems([])
      setState('empty')
      return
    }
    setState('loading')
    try {
      const list = await fetcherRef.current()
      if (!aliveRef.current) return
      setItems(list || [])
      setState((list || []).length ? 'ok' : 'empty')
    } catch (e) {
      if (!aliveRef.current) return
      console.error('推荐加载失败', e)
      setItems([])
      setState('error')
    }
  }, [enabled])

  useEffect(() => {
    aliveRef.current = true
    load()
    return () => {
      aliveRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled])

  return { items, state, reload: load }
}
