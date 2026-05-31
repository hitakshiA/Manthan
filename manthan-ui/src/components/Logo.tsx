import { cn } from "@/lib/cn";

interface LogoProps {
  size?: number;
  showWordmark?: boolean;
  className?: string;
  /** Compact mark used in tight nav spots */
  compact?: boolean;
}

/**
 * Manthan mark - three right-facing concentric arcs emitting from a solid
 * emerald core. Reads as a radar / sonar pulse, echoing the product
 * metaphor of an agent that listens, churns the signal, and emits insight.
 */
export function Logo({
  size = 28,
  showWordmark = true,
  className,
  compact = false,
}: LogoProps) {
  return (
    <div className={cn("inline-flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 32 32"
        width={size}
        height={size}
        fill="none"
        className="shrink-0"
        aria-hidden="true"
      >
        {/* outermost arc */}
        <path
          d="M 16 2 A 14 14 0 0 1 16 30"
          stroke="currentColor"
          strokeOpacity="0.32"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        {/* middle arc */}
        <path
          d="M 16 6 A 10 10 0 0 1 16 26"
          stroke="currentColor"
          strokeOpacity="0.68"
          strokeWidth="2"
          strokeLinecap="round"
        />
        {/* inner arc */}
        <path
          d="M 16 11 A 5 5 0 0 1 16 21"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        {/* emerald core */}
        <circle cx="16" cy="16" r="2.4" fill="oklch(0.62 0.15 150)" />
      </svg>
      {showWordmark && !compact && (
        <span className="text-[15px] font-semibold tracking-tight text-white">
          Manthan
        </span>
      )}
    </div>
  );
}
