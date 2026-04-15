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
          "focus-visible:outline-none focus-visible:[box-shadow:var(--focus-ring-shadow)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
          variant === "primary" &&
            "[background:var(--button-primary-bg)] [color:var(--button-primary-text)] shadow-[var(--button-primary-shadow)] hover:-translate-y-0.5 hover:[box-shadow:var(--button-primary-shadow-hover)]",
          variant === "secondary" &&
            "border text-app-text [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)] hover:border-app-borderStrong hover:text-app-cyan hover:[background:var(--button-secondary-bg-hover)]",
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
