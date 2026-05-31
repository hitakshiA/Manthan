import { cn } from "@/lib/cn";
import { getSource } from "@/lib/sources";

interface SourceIconProps {
  id: string;
  size?: number;
  className?: string;
  /** Use the brand's hex color (default mono via currentColor / ink). */
  tinted?: boolean;
}

/**
 * Brand IDs whose canonical logo colour reads poorly on the current
 * theme's background.
 *
 * Two failure modes, same fix:
 *   - **Pure-black brands** (Notion, GitHub, Vercel, etc.) disappear
 *     on dark mode.
 *   - **Pure-white brands** (Resend ships #FDFDFD) disappear on light
 *     mode.
 *
 * For both, we swap the brand hex for `var(--color-ink-strong)`, which
 * is the warm near-white on dark and the warm near-black on light -
 * legible everywhere. Brands whose canonical colour is in the readable
 * mid-range (Stripe purple, HubSpot orange, Intercom blue) are left
 * alone and rendered in their brand hex.
 */
const USE_INK_INSTEAD = new Set([
  "notion",
  "posthog",
  "github",
  "vercel",
  "next",
  "openai",
  "anthropic",
  "x",
  "tiktok",
  // Pure-white brands - same override, opposite-side problem.
  "resend",
]);

export function SourceIcon({
  id,
  size = 18,
  className,
  tinted = false,
}: SourceIconProps) {
  const meta = getSource(id);
  if (!meta?.simpleIcon) {
    const initials = meta?.name?.slice(0, 2) ?? id.slice(0, 2);
    return (
      <span
        className={cn(
          "inline-flex items-center justify-center text-[10px] font-semibold",
          className,
        )}
        style={{
          width: size,
          height: size,
          background: "var(--color-surface-2)",
          color: "var(--color-ink-muted)",
          borderRadius: "var(--radius-xs)",
        }}
      >
        {initials.toUpperCase()}
      </span>
    );
  }

  // Three cases for the SVG fill:
  //   1. tinted + brand-readable        → brand hex
  //   2. tinted + extreme brand color   → ink token (adapts to theme)
  //   3. not tinted                     → currentColor (whatever the parent text colour is)
  let fill: string;
  if (tinted) {
    fill = USE_INK_INSTEAD.has(id)
      ? "var(--color-ink-strong)"
      : `#${meta.simpleIcon.hex}`;
  } else {
    fill = "currentColor";
  }

  // Most icons come from simple-icons with a 24x24 viewBox; brand kits
  // shipped from the vendor (Resend's 1800x1800) declare their own.
  // Honor whatever the icon registry advertised.
  const viewBox = meta.simpleIcon.viewBox ?? "0 0 24 24";

  return (
    <svg
      role="img"
      viewBox={viewBox}
      width={size}
      height={size}
      className={className}
      fill={fill}
      aria-label={meta.name}
    >
      <path d={meta.simpleIcon.path} />
    </svg>
  );
}
