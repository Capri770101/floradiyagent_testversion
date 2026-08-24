/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// H5 通过 /api 代理到本地后端，避免浏览器跨域（无需改动后端 CORS）。
// 后端端口以你 uvicorn 启动时 --port 为准，默认 8080。
const BACKEND = process.env.VITE_PROXY_TARGET || 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        // 独立管理后台入口（与移动端 H5 同仓但独立产物/路由，admin 逻辑不进移动端 bundle）
        admin: 'admin.html',
        // 独立商家工作台入口（三端独立域名架构：商家端独立产物与令牌 floradiy_merchant_token）
        merchant: 'merchant.html',
      },
    },
  },
  server: {
    host: true,
    // 临时放开 host 检查以支持 ngrok / localhost.run 等公网隧道演示；
    // ⚠️ 上线前改为具体域名白名单（如 allowedHosts: ['.your-domain.com']），勿长期全开。
    allowedHosts: true,
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
      // 生成图（后端 data/generated 静态托管，/generated/plan_*.png）
      '/generated': {
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
      '/generated': {
        target: BACKEND,
        changeOrigin: true,
      },
    },
  },
})
