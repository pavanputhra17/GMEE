/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // GMEE red-immersion palette — poster-grade monochrome crimson.
        hermes: {
          red: '#A50E1D',          // primary brand crimson (structure, CTAs, data highlights)
          'red-bright': '#E11D2E', // signal red — halos, live indicators, down-states
          'red-deep': '#6E0713',   // deep crimson — pressed panels, negative emphasis
          paper: '#E7C9C4',        // rose-paper canvas (landing)
          blush: '#F5E2DC',        // raised card surface (landing)
          bone: '#FFF7F2',         // type & keylines on red
          ink: '#1A0608',          // near-black with red undertone
          panel: '#2B1015',        // raised panel on ink (command center)
          'panel-deep': '#200A0E'  // recessed well on ink
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
