/**
 * Button - editorial pill, not a candy gum.
 *
 * Radius is restrained (3px / --radius-xs). No glow shadow on the accent
 * variant - solid colour, hairline border, that's it. Ghost is text-only.
 */

import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "accent" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const variantStyles: Record<Variant, string> = {
  // The print "press here" colour - high-contrast neutral. Lives at the top
  // of the hierarchy: one per surface, ideally.
  primary:
    "text-[var(--color-bg)] hover:opacity-90 " +
    "[background:var(--color-ink-strong)]",
  // Default - hairline neutral.
  secondary:
    "text-[var(--color-ink)] hover:text-[var(--color-ink-strong)] " +
    "border border-[var(--color-rule)] hover:border-[var(--color-rule-strong)] " +
    "bg-transparent hover:bg-[var(--color-surface-2)]",
  // No frame; reads as a link.
  ghost:
    "text-[var(--color-ink-muted)] hover:text-[var(--color-ink-strong)] " +
    "bg-transparent border border-transparent hover:bg-[var(--color-surface)]",
  // The verb of intent - confirm, ship, fire.
  accent:
    "text-[var(--color-accent-ink)] hover:opacity-90 " +
    "[background:var(--color-accent)]",
  // Destructive paths.
  danger:
    "text-white hover:opacity-90 [background:var(--color-danger)]",
};

const sizeStyles: Record<Size, string> = {
  sm: "h-7 px-2.5 text-[12px]",
  md: "h-9 px-3.5 text-[13px]",
  lg: "h-11 px-5 text-[14px]",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      className,
      children,
      leftIcon,
      rightIcon,
      ...rest
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 font-medium leading-none",
          "rounded-[3px]",
          "transition-colors duration-150",
          "disabled:opacity-40 disabled:pointer-events-none",
          variantStyles[variant],
          sizeStyles[size],
          className,
        )}
        {...rest}
      >
        {leftIcon && <span className="-ml-0.5 flex shrink-0">{leftIcon}</span>}
        <span className="truncate">{children}</span>
        {rightIcon && <span className="-mr-0.5 flex shrink-0">{rightIcon}</span>}
      </button>
    );
  },
);
