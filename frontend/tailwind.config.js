/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f5f7fa",
          100: "#e4e7eb",
          200: "#cbd2d9",
          300: "#9aa5b1",
          400: "#7b8794",
          500: "#616e7c",
          600: "#52606d",
          700: "#3e4c59",
          800: "#2d3748",
          900: "#1a202c",
          950: "#0f1419",
        },
      },
    },
  },
  plugins: [],
};
