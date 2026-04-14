import { ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", type = "button", ...props }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold tracking-[0.01em] transition duration-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-cyan/60 focus-visible:ring-offset-2 focus-visible:ring-offset-app-bg",
          "disabled:cursor-not-allowed disabled:opacity-60",
          variant === "primary" &&
            "bg-[linear-gradient(135deg,rgba(118,228,255,1)_0%,rgba(15,216,255,0.92)_100%)] text-slate-950 shadow-glow hover:-translate-y-0.5 hover:shadow-[0_0_50px_rgba(15,216,255,0.26)]",
          variant === "secondary" &&
            "border text-app-text [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)] hover:border-app-cyan/30 hover:text-app-cyan hover:[background:var(--button-secondary-bg-hover)]",
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
