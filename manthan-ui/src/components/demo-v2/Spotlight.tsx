// Spotlight - dimmed overlay with a cutout around a target DOM element +
// floating tooltip card positioned next to it. The user can still see and
// click the target (the cutout is interactive); everything else is
// dimmed and visually de-emphasised.
//
// Used by the demo-v2 wizard to point at real UI elements (the
// "Policies" sidebar link, the "New rule" button, fields inside the
// create-rule modal, etc) while leaving the user in control of the
// actual interactions. The wizard never clicks anything for them.

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

interface SpotlightProps {
  /**
   * CSS selector for the element to highlight. When null (or no element
   * matches), the overlay becomes a plain dim with the tooltip floated
   * top-right.
   */
  target: string | null;
  /** Content of the tooltip card. Keep tight - 1-2 sentences plus action. */
  tooltip: ReactNode;
  /** Extra px of breathing room around the target inside the cutout. */
  padding?: number;
  /**
   * When true, scroll the target into view as soon as we find it.
   * Defaults to true. Disable for elements like the inbox nav row that
   * we know are always in view.
   */
  scrollIntoView?: boolean;
}

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export function Spotlight({
  target,
  tooltip,
  padding = 8,
  scrollIntoView = true,
}: SpotlightProps) {
  const [rect, setRect] = useState<Rect | null>(null);

  // Re-measure the target's bbox on a tight loop. Cheap (single
  // getBoundingClientRect) and resilient to layout changes from
  // sibling animations, scrolls, modal mounts, etc.
  useEffect(() => {
    if (!target) {
      setRect(null);
      return;
    }
    let scrolled = false;
    const tick = () => {
      const el = document.querySelector(target) as HTMLElement | null;
      if (!el) {
        setRect((prev) => (prev === null ? prev : null));
        return;
      }
      if (scrollIntoView && !scrolled) {
        const r = el.getBoundingClientRect();
        if (r.top < 60 || r.bottom > window.innerHeight - 60) {
          el.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        scrolled = true;
      }
      const b = el.getBoundingClientRect();
      setRect((prev) => {
        if (
          prev &&
          Math.abs(prev.top - b.top) < 0.5 &&
          Math.abs(prev.left - b.left) < 0.5 &&
          Math.abs(prev.width - b.width) < 0.5 &&
          Math.abs(prev.height - b.height) < 0.5
        ) {
          return prev; // dedupe; React would re-render otherwise
        }
        return { top: b.top, left: b.left, width: b.width, height: b.height };
      });
    };
    tick();
    const id = window.setInterval(tick, 200);
    const onResize = () => tick();
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onResize, true);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onResize, true);
    };
  }, [target, scrollIntoView]);

  // Render via portal so we escape any transformed/animated ancestor.
  const overlay = (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 8500,
        pointerEvents: "none",
      }}
    >
      {rect ? (
        <SpotlightWithTarget rect={rect} padding={padding} tooltip={tooltip} />
      ) : (
        <SpotlightWithoutTarget tooltip={tooltip} />
      )}
    </div>
  );

  return createPortal(overlay, document.body);
}

// ──────────────────────────────────────────────────────────────────────
// Render branches
// ──────────────────────────────────────────────────────────────────────

function SpotlightWithTarget({
  rect,
  padding,
  tooltip,
}: {
  rect: Rect;
  padding: number;
  tooltip: ReactNode;
}) {
  const hole = {
    top: rect.top - padding,
    left: rect.left - padding,
    width: rect.width + padding * 2,
    height: rect.height + padding * 2,
  };
  const placement = pickPlacement(hole);
  return (
    <>
      {/* SVG mask: dark full-screen overlay with rect-rounded hole.
          pointerEvents:none so the cutout area passes clicks through
          to the spotlighted element underneath. */}
      <svg
        width="100%"
        height="100%"
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
        }}
      >
        <defs>
          <mask id="manthan-spotlight-mask">
            <rect width="100%" height="100%" fill="white" />
            <rect
              x={hole.left}
              y={hole.top}
              width={hole.width}
              height={hole.height}
              rx={6}
              ry={6}
              fill="black"
            />
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="rgba(8,10,8,0.74)"
          mask="url(#manthan-spotlight-mask)"
        />
        {/* Glow ring */}
        <rect
          x={hole.left}
          y={hole.top}
          width={hole.width}
          height={hole.height}
          rx={6}
          ry={6}
          fill="none"
          stroke="#16d05e"
          strokeWidth={2}
          style={{
            filter: "drop-shadow(0 0 8px rgba(22,208,94,0.55))",
            animation: "manthan-spot-pulse 2s ease-in-out infinite",
          }}
        />
      </svg>

      {/* Pulse keyframes */}
      <style>{`
        @keyframes manthan-spot-pulse {
          0%, 100% { opacity: 0.95; }
          50% { opacity: 0.55; }
        }
        @keyframes manthan-tip-in {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <TooltipCard placement={placement}>{tooltip}</TooltipCard>
    </>
  );
}

function SpotlightWithoutTarget({ tooltip }: { tooltip: ReactNode }) {
  // Element not on the page yet (or selector is null). Dim everything,
  // float the tooltip top-right, and wait.
  return (
    <>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(8,10,8,0.74)",
          backdropFilter: "blur(2px)",
          WebkitBackdropFilter: "blur(2px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 24,
          right: 24,
          pointerEvents: "auto",
          animation: "manthan-tip-in 220ms ease",
        }}
      >
        <div
          style={{
            ...TIP_CARD_STYLE,
            maxWidth: 360,
          }}
        >
          {tooltip}
        </div>
      </div>
      <style>{`
        @keyframes manthan-tip-in {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Tooltip placement
// ──────────────────────────────────────────────────────────────────────

type Placement = {
  side: "right" | "left" | "bottom" | "top";
  top: number;
  left: number;
};

const TIP_CARD_WIDTH = 320;
const TIP_GAP = 16;

function pickPlacement(hole: Rect): Placement {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const TIP_H_ESTIMATE = 180; // rough; tooltip is dynamic but bounded

  // Prefer right
  if (hole.left + hole.width + TIP_GAP + TIP_CARD_WIDTH < vw - 16) {
    return {
      side: "right",
      top: clamp(
        hole.top + hole.height / 2 - TIP_H_ESTIMATE / 2,
        16,
        vh - TIP_H_ESTIMATE - 16,
      ),
      left: hole.left + hole.width + TIP_GAP,
    };
  }
  // Else left
  if (hole.left - TIP_GAP - TIP_CARD_WIDTH > 16) {
    return {
      side: "left",
      top: clamp(
        hole.top + hole.height / 2 - TIP_H_ESTIMATE / 2,
        16,
        vh - TIP_H_ESTIMATE - 16,
      ),
      left: hole.left - TIP_GAP - TIP_CARD_WIDTH,
    };
  }
  // Else bottom
  if (hole.top + hole.height + TIP_GAP + TIP_H_ESTIMATE < vh - 16) {
    return {
      side: "bottom",
      top: hole.top + hole.height + TIP_GAP,
      left: clamp(
        hole.left + hole.width / 2 - TIP_CARD_WIDTH / 2,
        16,
        vw - TIP_CARD_WIDTH - 16,
      ),
    };
  }
  // Else top
  return {
    side: "top",
    top: Math.max(16, hole.top - TIP_GAP - TIP_H_ESTIMATE),
    left: clamp(
      hole.left + hole.width / 2 - TIP_CARD_WIDTH / 2,
      16,
      vw - TIP_CARD_WIDTH - 16,
    ),
  };
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function TooltipCard({
  placement,
  children,
}: {
  placement: Placement;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        position: "absolute",
        top: placement.top,
        left: placement.left,
        width: TIP_CARD_WIDTH,
        pointerEvents: "auto",
        animation: "manthan-tip-in 220ms ease",
      }}
    >
      <div style={TIP_CARD_STYLE}>{children}</div>
    </div>
  );
}

const TIP_CARD_STYLE: React.CSSProperties = {
  background: "#15171a",
  border: "1px solid rgba(255,255,255,0.10)",
  borderRadius: 12,
  padding: "16px 16px 14px",
  color: "#efece4",
  fontFamily:
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  boxShadow: "0 20px 50px rgba(0,0,0,0.45)",
};
