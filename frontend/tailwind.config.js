/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0e0f11",
        panel: "#141619",
        raised: "#1b1e22",
        line: "#25282d",
        ink: "#e6e8eb",
        mute: "#8b919a",
        accent: "#7f8cf5",
        good: "#41b883",
        warn: "#e0a43c",
        bad: "#e5645a",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};