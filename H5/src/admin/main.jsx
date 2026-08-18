// 管理后台独立入口：只挂载 admin 应用，不引入移动端 bundle。
import React from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import { AdminApp } from './App'

createRoot(document.getElementById('root')).render(<AdminApp />)
