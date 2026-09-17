/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        steel: {
          950: "#0b1118",
          900: "#121a24",
          800: "#1b2736",
          700: "#243447",
          500: "#7d93ab",
          300: "#c5d4e3",
        },
        ember: "#e8b86d",
      },
    },
  },
  plugins: [],
};
