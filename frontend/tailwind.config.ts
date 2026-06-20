import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: '#0f1117',
        card:    '#1a1f2e',
        border:  '#2a3044',
      },
    },
  },
  plugins: [],
}
export default config
