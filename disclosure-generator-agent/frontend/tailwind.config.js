/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        arabic: ["Noto Naskh Arabic", "serif"],
        urdu: ["Noto Nastaliq Urdu", "serif"],
      },
    },
  },
  plugins: [],
};
