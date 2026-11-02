/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        apex: {
          bg: 'var(--bg)',
          panel: 'var(--panel)',
          text: 'var(--text)',
          accent: 'var(--lime)',
        },
      },
      fontFamily: {
        display: ['Manrope', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
