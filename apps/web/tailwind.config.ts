import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "var(--color-bg)",
          surface: "var(--color-surface)",
          surfaceSoft: "var(--color-surface-soft)",
          surfaceStrong: "var(--color-surface-strong)",
          border: "var(--color-border)",
          text: "var(--color-text)",
          muted: "var(--color-muted)",
          cyan: "var(--color-cyan)",
          cyanStrong: "var(--color-cyan-strong)",
          gold: "var(--color-gold)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
      },
      boxShadow: {
        glow: "0 0 42px rgba(15, 216, 255, 0.18)",
        card: "0 18px 80px rgba(6, 12, 18, 0.46)",
      },
      backgroundImage: {
        "hero-grid":
          "linear-gradient(rgba(118, 228, 255, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(118, 228, 255, 0.05) 1px, transparent 1px)",
      },
      animation: {
        "float-slow": "floatSlow 8s ease-in-out infinite",
        "pulse-soft": "pulseSoft 5s ease-in-out infinite",
      },
      keyframes: {
        floatSlow: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.5", transform: "scale(1)" },
          "50%": { opacity: "0.85", transform: "scale(1.06)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
