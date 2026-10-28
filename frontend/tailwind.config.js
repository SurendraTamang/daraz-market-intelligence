/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B0E14",
        panel: "#141922",
        panel2: "#1B222D",
        line: "#28303B",
        fg: "#E7EBF2",
        muted: "#8A93A3",
        accent: "#F2A93B",
        good: "#3FB984",
        warn: "#E0A83E",
        bad: "#E06A5E",
      },
      fontFamily: {
        mono: ["ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
