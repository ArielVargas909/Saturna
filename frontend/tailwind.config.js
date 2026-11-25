/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 900: "#0B1445", 700: "#1B2A78" },
        cyan: { 500: "#1FB6F5", 600: "#0E96D0" },
        crimson: { 600: "#E11D48" },
        app: { bg: "#F5F7FB", surface: "#FFFFFF", border: "#E3E8F2", muted: "#5B6685" },
        navy: { 950: "#0B1445", 900: "#0B1445", 800: "#1B2A78", 700: "#1B2A78" },
        orbit: { DEFAULT: "#1FB6F5", dark: "#0E96D0", soft: "#DDF3FD" },
        flare: { DEFAULT: "#E11D48", dark: "#B3153A", soft: "#FFE1E7" },
        paper: "#F5F7FB",
        ink: "#0B1445",
      },
      fontFamily: {
        sans: ['"Avenir Next"', '"Segoe UI"', "system-ui", "-apple-system", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
