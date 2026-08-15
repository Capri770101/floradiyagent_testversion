/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // ===== Maison Flora 轻奢色板（maison-flora-design-prompt.md）=====
        // 类名沿用旧名，值整体替换，实现全站一键换肤
        bg: '#FAF8F5',        // 象牙白页面底
        ink: '#1A1A1A',       // 墨黑文字
        sub: '#6B6B6B',       // 石板灰辅助文字
        pink: '#B5985A',      // 香槟金（主色：按钮/价格/强调）
        'pink-2': '#F0EBE3',  // 砂色柔和底
        cream: '#C9A96A',     // 浅金（星标/角标）
        green: '#A0947C',     // 暖灰褐（状态色）
        line: '#D4CFC6',      // 石色极细描边
        dark: '#1A1A1A',      // 墨黑（主按钮/吸底栏）
        // 新增语义色
        gold: '#B5985A',
        'gold-dark': '#6B5630',
        burgundy: '#722F37',
        sand: '#F0EBE3',
        stone: '#8B8680',
      },
      borderRadius: {
        // 近直角：2px / 4px，拒绝圆润
        btn: '2px',
        pill: '2px',
        card: '4px',
        'card-lg': '4px',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
      boxShadow: {
        // 无投影（flat）：层次靠留白与描边
        card: 'none',
        frame: 'none',
        xl: 'none',
      },
      letterSpacing: {
        eyebrow: '0.3em',
      },
      maxWidth: {
        h5: '390px',
      },
    },
  },
  plugins: [],
}
