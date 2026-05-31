/**
 * Auth controls - faithful port of Aurora Onboard's SocialButton +
 * InputGroup. brand-gray = #1A1A1A; rounded-xl; ring on focus.
 */

import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

const BRAND_GRAY = "#1A1A1A";

export function InputGroup({
  label,
  hint,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
}) {
  const isPwd = rest.type === "password";
  const [show, setShow] = useState(false);
  return (
    <label className="block">
      <div className="text-sm font-medium text-white mb-1.5">{label}</div>
      <div className="relative">
        <input
          {...rest}
          type={isPwd && show ? "text" : rest.type}
          className="w-full h-11 px-4 rounded-xl border-none text-white placeholder:text-white/20 focus:ring-2 focus:ring-white/20 focus:outline-none transition-all"
          style={{ backgroundColor: BRAND_GRAY }}
        />
        {isPwd && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white"
            aria-label={show ? "Hide password" : "Show password"}
          >
            {show ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </button>
        )}
      </div>
      {hint && (
        <div className="text-[11.5px] text-white/40 mt-1.5">{hint}</div>
      )}
    </label>
  );
}

export function SocialButton({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      type="button"
      className="h-11 w-full inline-flex items-center justify-center gap-2 rounded-xl bg-black border border-white/10 hover:bg-white/5 transition-colors text-sm font-medium text-white"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

export function Divider({ children = "or" }: { children?: ReactNode }) {
  // Two equal flex-1 rules flanking the label - mathematically symmetric,
  // so the label is always pixel-centered regardless of label width.
  // (Old "absolute line under a centered span with bg-black" technique
  // could look off when the bg-black mask didn't exactly cover the line.)
  return (
    <div className="flex items-center gap-3 select-none">
      <div className="flex-1 h-px bg-white/10" aria-hidden="true" />
      <span
        className="shrink-0 text-[10.5px] font-medium uppercase tracking-[0.18em]"
        style={{ color: "rgba(255,255,255,0.42)" }}
      >
        {children}
      </span>
      <div className="flex-1 h-px bg-white/10" aria-hidden="true" />
    </div>
  );
}
