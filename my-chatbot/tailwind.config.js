/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        colors: {
          'primary': {
            50: '#FDFFFC',   // Baby powder - main background
            100: '#F8FAF7',  // Lighter variant
            200: '#F0F4EF',  // Even lighter
            900: '#012622',  // Dark green - primary text
          },
          'secondary': {
            500: '#775B59',  // Liver - secondary elements
            600: '#6A4E4C',  // Darker variant
            700: '#5D4340',  // Even darker
          },
          'accent': {
            500: '#A6A15E',  // Moss green - accent elements
            600: '#95904F',  // Darker variant
            700: '#848040',  // Even darker
          },
          'dark': {
            500: '#32161F',  // Dark purple - borders and dark accents
            600: '#2A1219',  // Darker variant
            700: '#220E13',  // Even darker
          }
        }
      },
    },
    plugins: [],
  }
  