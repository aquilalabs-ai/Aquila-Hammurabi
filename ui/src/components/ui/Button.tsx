import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "./cn";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "secondary", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-400 disabled:pointer-events-none disabled:opacity-50",
          {
            "bg-gold-500 text-slate-900 hover:bg-gold-400": variant === "primary",
            "bg-slate-700 text-slate-100 hover:bg-slate-600 border border-slate-600":
              variant === "secondary",
            "text-slate-300 hover:text-slate-100 hover:bg-slate-700/60": variant === "ghost",
            "bg-red-600 text-white hover:bg-red-500": variant === "danger",
          },
          {
            "h-7 px-2.5 text-xs": size === "sm",
            "h-9 px-3.5 text-sm": size === "md",
            "h-11 px-5 text-base": size === "lg",
          },
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
