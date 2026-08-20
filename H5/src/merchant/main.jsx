// 商家端独立入口：只挂载商家工作台，不引入移动端 bundle。
import React from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import { MerchantApp } from './App'

createRoot(document.getElementById('root')).render(<MerchantApp />)