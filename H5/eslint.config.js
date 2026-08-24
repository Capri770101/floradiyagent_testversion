import js from '@eslint/js'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'

// 跳舞兰 H5 前端 ESLint 扁平配置（ESLint 9）
export default [
  { ignores: ['dist/**', 'node_modules/**', 'public/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    plugins: { react, 'react-hooks': reactHooks },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        navigator: 'readonly',
        fetch: 'readonly',
        alert: 'readonly',
        console: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        performance: 'readonly',
        IntersectionObserver: 'readonly',
        ResizeObserver: 'readonly',
        AbortController: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        URLSearchParams: 'readonly',
        FormData: 'readonly',
        TextDecoder: 'readonly',
        TextEncoder: 'readonly',
        File: 'readonly',
        Blob: 'readonly',
        process: 'readonly',
        Set: 'readonly',
        Date: 'readonly',
        Math: 'readonly',
        JSON: 'readonly',
        Number: 'readonly',
        String: 'readonly',
        Array: 'readonly',
        Object: 'readonly',
        Boolean: 'readonly',
        undefined: 'readonly',
      },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // React 17+ 无需显式 import React；本项目为旧式但可放宽
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // 宽松的未使用变量（下划线前缀忽略；历史代码未整理，先不阻塞）
      'no-unused-vars': 'off',
      'no-undef': 'error',
    },
  },
]
