import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        app: {
          background: "var(--color-background)",
          backgroundMuted: "var(--color-background-muted)",
          bg: "var(--color-bg)",
          surface: "var(--color-surface)",
          surfaceElevated: "var(--color-surface-elevated)",
          surfaceSoft: "var(--color-surface-soft)",
          surfaceStrong: "var(--color-surface-strong)",
          border: "var(--color-border)",
          borderStrong: "var(--color-border-strong)",
          text: "var(--color-text)",
          textPrimary: "var(--color-text-primary)",
          textSecondary: "var(--color-text-secondary)",
          muted: "var(--color-muted)",
          brandPrimary: "var(--color-brand-primary)",
          brandPrimarySoft: "var(--color-brand-primary-soft)",
          cyan: "var(--color-cyan)",
          cyanStrong: "var(--color-cyan-strong)",
          premiumAccent: "var(--color-premium-accent)",
          premiumAccentSoft: "var(--color-premium-accent-soft)",
          gold: "var(--color-gold)",
          success: "var(--color-success)",
          warning: "var(--color-warning)",
          error: "var(--color-error)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
      },
      boxShadow: {
        glow: "var(--button-primary-shadow)",
        "glow-soft": "var(--nav-indicator-shadow)",
        premium: "var(--nav-premium-chip-shadow)",
        card: "var(--glass-panel-shadow)",
      },
      backgroundImage: {
        "hero-grid":
          "linear-gradient(var(--color-brand-primary-soft) 1px, transparent 1px), linear-gradient(90deg, var(--color-brand-primary-soft) 1px, transparent 1px)",
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
