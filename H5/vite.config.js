import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// H5 通过 /api 代理到本地后端，避免浏览器跨域（无需改动后端 CORS）。
// 后端端口以你 uvicorn 启动时 --port 为准，默认 8080。
const BACKEND = process.env.VITE_PROXY_TARGET || 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      // 商家上传图片（后端 data/uploads 静态托管）
      '/uploads': {
        target: BACKEND,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/uploads': {
        target: BACKEND,
        changeOrigin: true,
      },
    },
  },
})
