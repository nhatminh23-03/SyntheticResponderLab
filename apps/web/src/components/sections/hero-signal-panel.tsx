"use client";

import { motion } from "framer-motion";

import { GlassPanel } from "@/components/ui/glass-panel";

export function HeroSignalPanel() {
  return (
    <GlassPanel className="mx-auto w-full max-w-[38rem] p-4 sm:p-5">
      <div
        className="relative isolate overflow-hidden rounded-[1.35rem] border px-4 py-4 sm:rounded-[1.45rem] sm:px-6 sm:py-6"
        style={{
          background: "var(--hero-signal-panel-bg)",
          borderColor: "var(--hero-signal-panel-border)",
        }}
      >
        <div className="section-grid absolute inset-0 opacity-60" />
        <div
          className="absolute left-1/2 top-1/2 h-[13.5rem] w-[13.5rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl sm:h-[17rem] sm:w-[17rem]"
          style={{ background: "var(--hero-center-glow)" }}
        />
        <div
          className="absolute right-[12%] top-[18%] h-12 w-12 rounded-full blur-2xl sm:h-16 sm:w-16"
          style={{ background: "var(--hero-premium-glow)" }}
        />

        <div className="relative z-10 flex min-h-[13.5rem] items-center justify-center sm:min-h-[18.5rem]">
          <motion.div
            className="absolute h-[12.75rem] w-[12.75rem] rounded-full border border-app-cyan/12 sm:h-[16rem] sm:w-[16rem]"
            animate={{ rotate: 360 }}
            transition={{
              duration: 36,
              repeat: Number.POSITIVE_INFINITY,
              ease: "linear",
            }}
          />
          <motion.div
            className="absolute h-[9.25rem] w-[9.25rem] rounded-full border sm:h-[12rem] sm:w-[12rem]"
            style={{ borderColor: "var(--hero-orbit-border-muted)" }}
            animate={{ rotate: -360 }}
            transition={{
              duration: 24,
              repeat: Number.POSITIVE_INFINITY,
              ease: "linear",
            }}
          />
          <motion.div
            className="absolute h-[7rem] w-[7rem] rounded-[1.1rem] border border-app-cyan/20 sm:h-[9rem] sm:w-[9rem] sm:rounded-[1.5rem]"
            style={{
              background: "var(--hero-orbit-core-bg)",
              boxShadow: "var(--hero-orbit-core-shadow)",
            }}
            animate={{ y: [0, -6, 0] }}
            transition={{
              duration: 5.6,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
            }}
          />
          <motion.div
            className="absolute h-20 w-20 rounded-[1rem] backdrop-blur-xl sm:h-28 sm:w-28 sm:rounded-[1.35rem]"
            style={{
              background: "var(--hero-core-gradient)",
              boxShadow: "var(--hero-core-shadow)",
            }}
            animate={{ scale: [1, 1.03, 1] }}
            transition={{
              duration: 4.5,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
            }}
          >
            <div className="flex h-full items-center justify-center">
              <div
                className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-app-cyan/25 sm:h-10 sm:w-10 sm:rounded-xl"
                style={{ background: "var(--hero-signal-node-bg)" }}
              >
                <div className="absolute h-4 w-4 rounded-full bg-app-cyan/65 blur-sm sm:h-5 sm:w-5" />
                <div className="relative h-3.5 w-3.5 rounded-full bg-app-cyan sm:h-4 sm:w-4" />
              </div>
            </div>
          </motion.div>
          <div
            className="absolute left-[16%] top-[17%] h-2.5 w-2.5 rounded-full bg-app-gold"
            style={{ boxShadow: "var(--hero-dot-gold-shadow)" }}
          />
          <div
            className="absolute right-[18%] top-[34%] h-2 w-2 rounded-full bg-app-cyan"
            style={{ boxShadow: "var(--hero-dot-cyan-shadow)" }}
          />
          <div
            className="absolute bottom-[18%] left-[22%] h-2 w-2 rounded-full bg-white/70"
            style={{ boxShadow: "var(--hero-dot-neutral-shadow)" }}
          />
        </div>

        <div className="relative z-10 mt-3 grid gap-3 sm:grid-cols-2">
          <div
            className="rounded-[1.2rem] border px-4 py-3.5 sm:rounded-[1.35rem] sm:px-5 sm:py-4"
            style={{
              background: "var(--hero-signal-card-bg)",
              borderColor: "var(--hero-signal-card-border)",
              boxShadow: "var(--hero-signal-card-shadow)",
            }}
          >
            <div className="text-[0.64rem] uppercase tracking-[0.24em] text-app-muted/90">
              What We Model
            </div>
            <div className="mt-2 text-[0.92rem] font-semibold leading-6 text-app-text sm:text-[0.98rem] sm:leading-7">
              Audience, budget, location, product details, and market context.
            </div>
          </div>
          <div
            className="rounded-[1.2rem] border px-4 py-3.5 sm:rounded-[1.35rem] sm:px-5 sm:py-4"
            style={{
              background: "var(--hero-signal-card-bg)",
              borderColor: "var(--hero-signal-card-border)",
              boxShadow: "var(--hero-signal-card-shadow)",
            }}
          >
            <div className="text-[0.64rem] uppercase tracking-[0.24em] text-app-muted/90">
              Quality Checks
            </div>
            <div className="mt-2 text-[0.92rem] font-semibold leading-6 text-app-text sm:text-[0.98rem] sm:leading-7">
              Consistency, realism, and transparency checks before insights.
            </div>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}
