/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        hermes: {
          red: '#C1121F',
          yellow: '#edff45',
          paper: '#f5f5f5',
          ink: '#0a0a14'
        }
      },
      fontFamily: {
        display: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"Courier Prime"', 'ui-monospace', 'SFMono-Regular', 'monospace']
      }
    },
  },
  plugins: [],
}
