import { cn } from "@/lib/utils";

interface Props {
  size?: number;
  animate?: boolean;
  className?: string;
}

export function ManthanLogo({ size = 28, animate = false, className }: Props) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      fill="none"
      width={size}
      height={size}
      className={cn(className)}
      aria-hidden="true"
    >
      {/* Rotating group — the churning arcs */}
      <g className={animate ? "animate-churn" : ""} style={{ transformOrigin: "16px 16px" }}>
        {/* Outer arc */}
        <path
          d="M16 4C9.373 4 4 9.373 4 16"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          opacity="0.25"
        />
        {/* Middle arc */}
        <path
          d="M16 8C11.582 8 8 11.582 8 16"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          opacity="0.55"
        />
        {/* Inner arc */}
        <path
          d="M16 12C13.791 12 12 13.791 12 16"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          opacity="0.85"
        />
      </g>

      {/* Center point — the insight */}
      <circle
        cx="16"
        cy="16"
        r="2.5"
        fill="currentColor"
        className={animate ? "animate-pulse-dot" : ""}
      />

      {/* Outward rays — knowledge extracted */}
      <g className={animate ? "animate-rays" : ""} opacity={animate ? 1 : 0.6}>
        <path d="M20 16h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.7" />
        <path d="M16 20v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <path d="M19.5 19.5l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.35" />
      </g>
    </svg>
  );
}
