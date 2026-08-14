/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // 来自 DESIGN_SPEC_H5.md §1.1 设计令牌
        bg: '#F8F6F2',
        ink: '#333333',
        sub: '#999999',
        pink: '#E88AA1',
        'pink-2': '#F6DDE3',
        green: '#A7C5AE',
        cream: '#F7C99C',
        line: '#E8E2DC',
        dark: '#343434',
      },
      borderRadius: {
        btn: '21px',
        pill: '15px',
        card: '14px',
        'card-lg': '18px',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
      boxShadow: {
        card: '0 6px 24px rgba(52, 52, 52, 0.06)',
        frame: '0 24px 80px rgba(52, 52, 52, 0.18)',
      },
      maxWidth: {
        h5: '375px',
      },
    },
  },
  plugins: [],
}
