import { cn } from "@/lib/utils";

interface Props {
  size?: number;
  animate?: boolean;
  className?: string;
}

/**
 * Manthan mark — a stylized "M" where the center dip becomes
 * an upward peak. Data goes in, insight comes out.
 *
 * Animation: when `animate` is true, the stroke cycles through
 * a dash-offset loop, creating a "drawing" motion that suggests
 * the system is actively working/churning.
 */
export function ManthanLogo({ size = 24, animate = false, className }: Props) {
  // Total path length of "M6 24V10l10 8 10-8v14" ≈ 54
  const pathLength = 54;

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
      {animate && (
        <style>{`
          @keyframes manthan-draw {
            0% { stroke-dashoffset: ${pathLength}; }
            50% { stroke-dashoffset: 0; }
            100% { stroke-dashoffset: -${pathLength}; }
          }
          .manthan-path-animated {
            stroke-dasharray: ${pathLength};
            animation: manthan-draw 2.4s cubic-bezier(0.4, 0, 0.2, 1) infinite;
          }
        `}</style>
      )}
      <path
        d="M6 24V10l10 8 10-8v14"
        stroke="currentColor"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={animate ? "manthan-path-animated" : ""}
      />
    </svg>
  );
}
