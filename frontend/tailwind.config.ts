import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#040706",
        abyss: "#07100d",
        carbon: "#0d1613",
        moss: "#12211c",
        line: "rgba(190,255,230,0.09)",
        mist: "#8fa39b",
        bone: "#e9f2ee",
        signal: "#3dffc5",
        cyan: "#38d9ff",
        amber: "#ffb547",
        violet: "#a78bfa",
        danger: "#ff6370",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      keyframes: {
        pulseRing: {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        sweep: { "0%": { transform: "rotate(0deg)" }, "100%": { transform: "rotate(360deg)" } },
        rise: { "0%": { transform: "translateY(12px)", opacity: "0" }, "100%": { transform: "none", opacity: "1" } },
        flicker: { "0%,100%": { opacity: "0.35" }, "50%": { opacity: "1" } },
      },
      animation: {
        pulseRing: "pulseRing 2.8s cubic-bezier(0.2,0.6,0.3,1) infinite",
        sweep: "sweep 2.2s linear infinite",
        rise: "rise 0.6s cubic-bezier(0.2,0.7,0.2,1) both",
        flicker: "flicker 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
