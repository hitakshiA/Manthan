/**
 * HowItWorksScenes - three animations invented specifically for Manthan.
 *
 *   01 · Watch       - a live pulse waveform scrolls left across the frame.
 *                       4 source channels sit below; each spike fires from
 *                       its channel and a brief event-capture chip surfaces
 *                       above. Live monitoring made visual.
 *
 *   02 · Investigate - 4 evidence cards live in the corners with a source
 *                       icon + one-line finding. On cycle, they fly inward,
 *                       rotating subtly, and stack at center as a single
 *                       BRIEF with [1][2][3][4] citations.
 *
 *   03 · Act         - a row of 4 toggles, each labeled with its destination.
 *                       After an "approve" trigger they flip ON one by one,
 *                       glow emerald, and a 0/4 → 4/4 counter completes.
 *                       Auto-execute under thresholds, made literal.
 *
 * Pure GSAP. Each scene cleans up its timelines on unmount.
 */

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { motion, AnimatePresence } from "motion/react";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { Check } from "lucide-react";

const ACCENT = "oklch(0.62 0.15 150)";
const ACCENT_SOFT = "oklch(0.62 0.15 150 / 0.20)";
const ACCENT_LINE = "oklch(0.62 0.15 150 / 0.55)";
const INK = "oklch(0.96 0.004 75)";
const INK_FAINT = "oklch(0.55 0.006 75)";

/* ─── Shared frame ────────────────────────────────────────────────────── */

function SceneFrame({
  children,
  innerRef,
}: {
  children: React.ReactNode;
  innerRef?: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={innerRef}
      className="relative w-full overflow-hidden rounded-xl"
      style={{
        aspectRatio: "3 / 2",
        background:
          "radial-gradient(120% 90% at 50% 50%, oklch(0.10 0.005 75) 0%, oklch(0.05 0.005 75) 65%, #000 100%)",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {children}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   01 · WATCH - live pulse waveform with source channels
   ═══════════════════════════════════════════════════════════════════════ */

const WATCH_CHANNELS: { id: string; label: string }[] = [
  { id: "stripe",     label: "Stripe" },
  { id: "salesforce", label: "Salesforce" },
  { id: "zendesk",    label: "Zendesk" },
  { id: "slack",      label: "Slack" },
];

const WATCH_EVENTS: { srcIdx: number; text: string }[] = [
  { srcIdx: 0, text: "ch_3MqXfL · $1,200" },
  { srcIdx: 1, text: "TechCorp · NPS 9" },
  { srcIdx: 2, text: "#8412 · CSAT 5/5" },
  { srcIdx: 3, text: "#billing-ops · ping" },
  { srcIdx: 0, text: "ch_8mFqZ · refund.req" },
  { srcIdx: 1, text: "StartupY · ARR $48K" },
  { srcIdx: 2, text: "#8425 · open" },
  { srcIdx: 3, text: "alert · failed payment" },
];

type WatchCallout = { key: number; srcIdx: number; text: string };

export function WatchScene() {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavePathRef = useRef<SVGPathElement>(null);
  const waveGlowRef = useRef<SVGPathElement>(null);
  const sweepRef = useRef<SVGLineElement>(null);
  const channelDotsRef = useRef<(HTMLDivElement | null)[]>([]);
  const channelRingsRef = useRef<(SVGCircleElement | null)[][]>([[], [], [], []]);
  const [current, setCurrent] = useState<WatchCallout | null>(null);
  const calloutId = useRef(0);

  useEffect(() => {
    const wave = wavePathRef.current;
    const glow = waveGlowRef.current;
    const sweep = sweepRef.current;
    if (!wave || !glow || !sweep) return;

    const POINTS = 160; // dense sampling so spike peaks are perfect curves
    const W = 600;
    const H = 200;
    const baselineY = H / 2;

    type Spike = { center: number; amp: number; born: number };
    const spikes: Spike[] = [];
    const SPIKE_LIFE = 3000;  // longer life so consecutive events overlap
    const SPIKE_WIDTH = 10;   // wider σ → broader, more graceful bell shape

    /** Catmull-Rom → cubic bezier, smooth path through points. */
    const smoothPath = (pts: { x: number; y: number }[]) => {
      if (pts.length < 2) return "";
      const segs: string[] = [`M ${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`];
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] ?? pts[i];
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const p3 = pts[i + 2] ?? p2;
        const cp1x = p1.x + (p2.x - p0.x) / 6;
        const cp1y = p1.y + (p2.y - p0.y) / 6;
        const cp2x = p2.x - (p3.x - p1.x) / 6;
        const cp2y = p2.y - (p3.y - p1.y) / 6;
        segs.push(
          `C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`,
        );
      }
      return segs.join(" ");
    };

    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const elapsed = t - t0;
      const pts: { x: number; y: number }[] = [];
      // Very gentle baseline breath so the line is never perfectly dead
      // (max ~1.4px movement). Real curvature comes from event spikes.
      const breathAmp = 1.4;
      for (let i = 0; i < POINTS; i++) {
        const x = (i / (POINTS - 1)) * W;
        const breath =
          Math.sin(i * 0.18 + elapsed * 0.0009) * 0.7 * breathAmp +
          Math.sin(i * 0.42 + elapsed * 0.0014) * 0.3 * breathAmp;
        let extra = 0;
        for (const s of spikes) {
          const age = t - s.born;
          if (age > SPIKE_LIFE) continue;
          // ease-out decay so spikes linger then fade
          const k = age / SPIKE_LIFE;
          const decay = (1 - k) * (1 - k);
          const dx = i - s.center;
          if (Math.abs(dx) > SPIKE_WIDTH * 4) continue;
          extra -= s.amp * decay * Math.exp(-(dx * dx) / (2 * SPIKE_WIDTH * SPIKE_WIDTH));
        }
        pts.push({ x, y: baselineY + breath + extra });
      }
      const d = smoothPath(pts);
      wave.setAttribute("d", d);
      glow.setAttribute("d", d);

      // Sweeping playhead - continuously travels left → right then resets.
      const sweepX = ((elapsed / 4200) % 1) * W;
      sweep.setAttribute("x1", String(sweepX));
      sweep.setAttribute("x2", String(sweepX));

      // Drop expired spikes.
      for (let i = spikes.length - 1; i >= 0; i--) {
        if (t - spikes[i].born > SPIKE_LIFE) spikes.splice(i, 1);
      }

      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const fire = () => {
      const evt = WATCH_EVENTS[Math.floor(Math.random() * WATCH_EVENTS.length)];
      spikes.push({
        center: 20 + Math.floor(Math.random() * (POINTS - 40)),
        amp: 56 + Math.random() * 26, // more dramatic peaks
        born: performance.now(),
      });

      // Channel ripple - 3 concentric circles expanding outward like water
      // dropped in a lake. The ring SVG is intentionally oversized + parent
      // is overflow-visible, so the ripples can spread beyond the icon box.
      const rings = channelRingsRef.current[evt.srcIdx];
      const dot = channelDotsRef.current[evt.srcIdx];
      rings.forEach((ring, ringIdx) => {
        if (!ring) return;
        gsap.fromTo(
          ring,
          { attr: { r: 18 }, opacity: 0.7, strokeWidth: 1.6 },
          {
            attr: { r: 78 },
            opacity: 0,
            strokeWidth: 0.4,
            duration: 1.4,
            delay: ringIdx * 0.22,
            ease: "sine.out",
            overwrite: true,
          },
        );
      });
      if (dot) {
        // brief snap to fully emerald, then ease back
        gsap.fromTo(
          dot,
          { backgroundColor: "oklch(0.08 0.005 75)", borderColor: "rgba(255,255,255,0.08)" },
          {
            backgroundColor: "oklch(0.62 0.15 150 / 0.18)",
            borderColor: ACCENT_LINE,
            duration: 0.18,
            ease: "power2.out",
            overwrite: true,
            onComplete: () => {
              gsap.to(dot, {
                backgroundColor: "oklch(0.08 0.005 75)",
                borderColor: "rgba(255,255,255,0.08)",
                duration: 0.6,
                ease: "power2.out",
              });
            },
          },
        );
      }

      // Single-chip display - replace whatever's there. AnimatePresence
      // crossfades it in/out smoothly with no layout shifts.
      const key = ++calloutId.current;
      setCurrent({ key, srcIdx: evt.srcIdx, text: evt.text });
    };
    const fireInterval = window.setInterval(fire, 2000);
    fire();

    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(fireInterval);
    };
  }, []);


  return (
    <SceneFrame innerRef={containerRef}>
      {/* Tiny "live" indicator dot, top-left - no text */}
      <div
        className="absolute"
        style={{
          top: 16,
          left: 18,
          width: 6,
          height: 6,
          borderRadius: 999,
          background: ACCENT,
          boxShadow: `0 0 8px ${ACCENT}, 0 0 18px ${ACCENT_SOFT}`,
          animation: "pulse-dot 1.8s ease-in-out infinite",
        }}
      />

      {/* Single event chip - slow fade in / dwell / slow fade out.
          No queue, no layout shifts, no bumping. */}
      <div
        className="absolute"
        style={{
          left: 0,
          right: 0,
          top: 52,
          height: 36,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          pointerEvents: "none",
        }}
      >
        <AnimatePresence mode="wait">
          {current && (
            <motion.div
              key={current.key}
              initial={{ opacity: 0, y: 6, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.96 }}
              transition={{
                opacity: { duration: 0.8, ease: [0.25, 1, 0.5, 1] },
                y:       { duration: 0.8, ease: [0.25, 1, 0.5, 1] },
                scale:   { duration: 0.8, ease: [0.25, 1, 0.5, 1] },
              }}
              style={{
                background: "oklch(0.10 0.005 75 / 0.92)",
                border: `1px solid ${ACCENT_LINE}`,
                borderRadius: 999,
                padding: "6px 16px",
                display: "inline-flex",
                alignItems: "center",
                gap: 10,
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 11.5,
                color: INK,
                boxShadow: `0 10px 28px rgba(0,0,0,0.50), 0 0 22px oklch(0.62 0.15 150 / 0.28)`,
                backdropFilter: "blur(8px)",
              }}
            >
              <SourceIcon id={WATCH_CHANNELS[current.srcIdx].id} size={15} tinted />
              <span style={{ color: INK_FAINT }}>·</span>
              {current.text}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Waveform layer */}
      <div
        className="absolute"
        style={{
          left: 0,
          right: 0,
          top: "42%",
          bottom: "32%",
        }}
      >
        <svg
          viewBox="0 0 600 200"
          preserveAspectRatio="none"
          className="w-full h-full"
        >
          <defs>
            <linearGradient id="watch-wave-stroke" x1="0%" x2="100%">
              <stop offset="0%" stopColor="oklch(0.62 0.15 150 / 0.08)" />
              <stop offset="18%" stopColor={ACCENT} />
              <stop offset="100%" stopColor="oklch(0.72 0.15 150)" />
            </linearGradient>
            <linearGradient id="watch-sweep" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor={ACCENT} stopOpacity="0" />
              <stop offset="50%" stopColor={ACCENT} stopOpacity="0.85" />
              <stop offset="100%" stopColor={ACCENT} stopOpacity="0" />
            </linearGradient>
            <filter id="watch-wave-blur" x="-10%" y="-50%" width="120%" height="200%">
              <feGaussianBlur stdDeviation="4" />
            </filter>
          </defs>

          {/* Faint vertical "time" grid */}
          {Array.from({ length: 12 }, (_, i) => (
            <line
              key={i}
              x1={(i / 12) * 600}
              x2={(i / 12) * 600}
              y1="0"
              y2="200"
              stroke="rgba(255,255,255,0.025)"
              strokeWidth="0.5"
            />
          ))}
          {/* Faint horizontal baseline */}
          <line x1="0" x2="600" y1="100" y2="100" stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" strokeDasharray="2 4" />

          {/* Soft outer glow of the wave (blurred copy) */}
          <path
            ref={waveGlowRef}
            stroke={ACCENT}
            strokeWidth="3.5"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.45"
            filter="url(#watch-wave-blur)"
          />

          {/* Crisp wave on top */}
          <path
            ref={wavePathRef}
            stroke="url(#watch-wave-stroke)"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ filter: `drop-shadow(0 0 6px ${ACCENT_SOFT})` }}
          />

          {/* Sweeping playhead */}
          <line
            ref={sweepRef}
            x1="0"
            x2="0"
            y1="20"
            y2="180"
            stroke="url(#watch-sweep)"
            strokeWidth="1.2"
            opacity="0.6"
          />
        </svg>
      </div>

      {/* Channel row at the bottom */}
      <div
        className="absolute"
        style={{
          left: 0,
          right: 0,
          bottom: 18,
          display: "flex",
          justifyContent: "center",
          gap: 32,
        }}
      >
        {WATCH_CHANNELS.map((c, i) => (
          <div
            key={c.id}
            className="flex flex-col items-center gap-1.5 relative"
            style={{ width: 44, overflow: "visible" }}
          >
            {/* Lake-ripple - 3 concentric rings expanding outward.
                Oversized SVG with overflow:visible so the rings spread
                far beyond the icon container, like water on a pond. */}
            <svg
              className="absolute pointer-events-none"
              style={{
                top: -80,
                left: -80,
                width: 200,
                height: 200,
                overflow: "visible",
              }}
              viewBox="0 0 200 200"
            >
              {[0, 1, 2].map((ringIdx) => (
                <circle
                  key={ringIdx}
                  ref={(node) => {
                    channelRingsRef.current[i][ringIdx] = node;
                  }}
                  cx="100"
                  cy="100"
                  r="18"
                  fill="none"
                  stroke={ACCENT}
                  strokeWidth="1.6"
                  opacity="0"
                />
              ))}
            </svg>
            <div
              ref={(node) => {
                channelDotsRef.current[i] = node;
              }}
              className="inline-flex items-center justify-center relative"
              style={{
                width: 38,
                height: 38,
                borderRadius: 999,
                background: "oklch(0.08 0.005 75)",
                border: "1px solid rgba(255,255,255,0.08)",
                transition: "transform 0.18s",
                zIndex: 2,
              }}
            >
              <SourceIcon id={c.id} size={22} tinted />
            </div>
            <span
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 9.5,
                color: INK_FAINT,
                letterSpacing: "0.06em",
              }}
            >
              {c.label.toUpperCase()}
            </span>
          </div>
        ))}
      </div>
    </SceneFrame>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   02 · INVESTIGATE - evidence cards collate at center as a brief
   ═══════════════════════════════════════════════════════════════════════ */

const INVESTIGATE_CARDS: {
  id: string;
  corner: "tl" | "tr" | "bl" | "br";
  cite: number;
  label: string;
  finding: string;
  // Resting position in viewBox 600x320 coords. Cards are 150px wide so
  // half-width 75 + ~8px margin = position ≥ 88 from each edge.
  origin: { x: number; y: number };
}[] = [
  { id: "salesforce", corner: "tl", cite: 1, label: "Salesforce", finding: "TechCorp · ARR $240K",  origin: { x: 120, y: 70 } },
  { id: "stripe",     corner: "tr", cite: 2, label: "Stripe",     finding: "0 disputes in 14mo",     origin: { x: 480, y: 70 } },
  { id: "zendesk",    corner: "bl", cite: 3, label: "Zendesk",    finding: "#8412 · closed 14d",     origin: { x: 120, y: 250 } },
  { id: "notion",     corner: "br", cite: 4, label: "Notion",     finding: "refunds.yaml · > $500",  origin: { x: 480, y: 250 } },
];

export function InvestigateScene() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const briefRef = useRef<HTMLDivElement>(null);
  const checkRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cards = cardRefs.current.filter(Boolean) as HTMLDivElement[];
    const brief = briefRef.current;
    const check = checkRef.current;
    if (cards.length === 0 || !brief || !check) return;

    const tl = gsap.timeline({ repeat: -1, repeatDelay: 1.2 });

    // Initial state: cards at their corner origins, brief hidden.
    INVESTIGATE_CARDS.forEach((c, i) => {
      const el = cards[i];
      gsap.set(el, {
        xPercent: -50,
        yPercent: -50,
        left: `${(c.origin.x / 600) * 100}%`,
        top: `${(c.origin.y / 320) * 100}%`,
        rotation: 0,
        scale: 1,
        opacity: 1,
      });
    });
    gsap.set(brief, { opacity: 0, scale: 0.94 });
    gsap.set(check, { opacity: 0, scale: 0.5, rotation: -8 });

    // Each card flies to center while shrinking + fading - it "dissolves
    // into" the brief instead of stacking visibly behind it.
    cards.forEach((el, i) => {
      tl.to(
        el,
        {
          left: "50%",
          top: "50%",
          scale: 0.35,
          opacity: 0,
          rotation: 0,
          duration: 0.7,
          ease: "power2.in",
        },
        0.22 * i + 0.3,
      );
    });

    // Brief panel materialises as the cards converge.
    tl.to(
      brief,
      { opacity: 1, scale: 1, duration: 0.55, ease: "power2.out" },
      0.8,
    );
    tl.to(
      check,
      { opacity: 1, scale: 1, rotation: 0, duration: 0.45, ease: "power2.out" },
      1.3,
    );

    // Hold the assembled brief.
    tl.to({}, { duration: 1.4 });

    // Brief fades; cards reappear at their corner origins.
    tl.to([brief, check], { opacity: 0, duration: 0.35, ease: "power2.in" });
    cards.forEach((el, i) => {
      tl.to(
        el,
        {
          left: `${(INVESTIGATE_CARDS[i].origin.x / 600) * 100}%`,
          top: `${(INVESTIGATE_CARDS[i].origin.y / 320) * 100}%`,
          rotation: 0,
          scale: 1,
          opacity: 1,
          duration: 0.45,
          ease: "power2.out",
        },
        "<+0.05",
      );
    });

    return () => {
      tl.kill();
    };
  }, []);

  return (
    <SceneFrame innerRef={containerRef}>
      {/* Evidence cards - start at corners, dissolve into the brief at center.
          Narrower on mobile so they don't clip against the scene frame edges. */}
      <style>{`
        .investigate-card { width: 108px; padding: 6px 8px; }
        @media (min-width: 768px) {
          .investigate-card { width: 150px; padding: 8px 10px; }
        }
      `}</style>
      {INVESTIGATE_CARDS.map((c, i) => (
        <div
          key={c.id}
          ref={(node) => {
            cardRefs.current[i] = node;
          }}
          className="absolute investigate-card"
          style={{
            background: "oklch(0.10 0.005 75 / 0.95)",
            border: `1px solid rgba(255,255,255,0.10)`,
            borderRadius: 8,
            boxShadow: "0 12px 24px rgba(0,0,0,0.5)",
            backdropFilter: "blur(4px)",
            willChange: "transform, left, top, opacity",
          }}
        >
          <div className="flex items-center gap-1.5 mb-1">
            {/* Notion's brand colour is black; force white tint so it's visible on dark cards. */}
            <SourceIcon id={c.id} size={14} tinted={c.id !== "notion"} />
            <span
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 9,
                color: INK_FAINT,
                letterSpacing: "0.08em",
              }}
            >
              {c.label.toUpperCase()}
            </span>
            <span
              className="ml-auto"
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 9.5,
                color: ACCENT,
                fontWeight: 600,
              }}
            >
              [{c.cite}]
            </span>
          </div>
          <div
            style={{
              fontSize: 10.5,
              color: INK,
              fontFamily: "Geist, sans-serif",
              lineHeight: 1.3,
            }}
          >
            {c.finding}
          </div>
        </div>
      ))}

      {/* Centered "brief assembled" panel on top */}
      <div
        ref={briefRef}
        className="absolute"
        style={{
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: 200,
          padding: "10px 14px",
          background: "oklch(0.62 0.15 150 / 0.10)",
          border: `1px solid ${ACCENT_LINE}`,
          borderRadius: 8,
          boxShadow: `0 0 32px oklch(0.62 0.15 150 / 0.30)`,
          zIndex: 50,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: 9.5,
            color: ACCENT,
            letterSpacing: "0.16em",
            marginBottom: 4,
          }}
        >
          BRIEF · CASE-4821
        </div>
        <div className="flex items-baseline gap-1" style={{ fontSize: 11, color: INK }}>
          <span className="font-mono" style={{ color: ACCENT, fontWeight: 600 }}>[1][2][3][4]</span>
          <span style={{ marginLeft: 6 }}>4 sources joined</span>
        </div>
      </div>

      {/* Success check - pops in after assembly */}
      <div
        ref={checkRef}
        className="absolute inline-flex items-center justify-center"
        style={{
          left: "calc(50% + 86px)",
          top: "calc(50% - 22px)",
          transform: "translate(-50%, -50%)",
          width: 24,
          height: 24,
          borderRadius: 999,
          background: ACCENT,
          color: "oklch(0.08 0.005 75)",
          boxShadow: `0 0 0 3px oklch(0.08 0.005 75)`,
          zIndex: 60,
        }}
      >
        <Check className="h-3.5 w-3.5" strokeWidth={3.5} />
      </div>
    </SceneFrame>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   03 · ACT - row of toggles flipping ON in cascade
   ═══════════════════════════════════════════════════════════════════════ */

const ACT_TOGGLES: { id: string; action: string }[] = [
  { id: "stripe", action: "Refund" },
  { id: "gmail",  action: "Email" },
  { id: "linear", action: "Ticket" },
  { id: "slack",  action: "Brief" },
];

export function ActScene() {
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRefs = useRef<(HTMLDivElement | null)[]>([]);
  const knobRefs = useRef<(HTMLDivElement | null)[]>([]);
  const lineRefs = useRef<(SVGLineElement | null)[]>([]);
  const signalRefs = useRef<(SVGCircleElement | null)[]>([]);
  const iconWrapRefs = useRef<(HTMLDivElement | null)[]>([]);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const tracks = trackRefs.current.filter(Boolean) as HTMLDivElement[];
    const knobs = knobRefs.current.filter(Boolean) as HTMLDivElement[];
    const lines = lineRefs.current.filter(Boolean) as SVGLineElement[];
    const signals = signalRefs.current.filter(Boolean) as SVGCircleElement[];
    const iconWraps = iconWrapRefs.current.filter(Boolean) as HTMLDivElement[];
    const rows = rowRefs.current.filter(Boolean) as HTMLDivElement[];
    if (tracks.length === 0 || iconWraps.length === 0) return;

    const reset = () => {
      tracks.forEach((t) => {
        gsap.set(t, {
          backgroundColor: "rgba(255,255,255,0.08)",
          borderColor: "rgba(255,255,255,0.10)",
          boxShadow: "none",
        });
      });
      knobs.forEach((k) => {
        gsap.set(k, { x: 0, backgroundColor: "rgba(255,255,255,0.60)" });
      });
      lines.forEach((l) => {
        gsap.set(l, { opacity: 0.35, stroke: "rgba(255,255,255,0.18)" });
      });
      signals.forEach((s) => {
        gsap.set(s, { attr: { cx: 0 }, opacity: 0 });
      });
      iconWraps.forEach((w) => {
        gsap.set(w, {
          backgroundColor: "oklch(0.10 0.005 75)",
          borderColor: "rgba(255,255,255,0.10)",
          boxShadow: "none",
          scale: 1,
        });
      });
      rows.forEach((r) => {
        gsap.set(r, { opacity: 0.6 });
      });
    };

    const tl = gsap.timeline({ repeat: -1, repeatDelay: 1.6 });

    tl.add(reset);
    tl.to({}, { duration: 0.7 }); // idle hold

    ACT_TOGGLES.forEach((_, i) => {
      const start = i * 0.55 + 1;

      // 1. Toggle flips ON
      tl.to(
        tracks[i],
        {
          backgroundColor: "oklch(0.62 0.15 150 / 0.55)",
          borderColor: ACCENT_LINE,
          boxShadow: `0 0 16px oklch(0.62 0.15 150 / 0.45)`,
          duration: 0.22,
          ease: "power2.out",
        },
        start,
      );
      tl.to(
        knobs[i],
        {
          x: 18,
          backgroundColor: "#fff",
          duration: 0.28,
          ease: "power3.out",
        },
        "<",
      );
      tl.to(rows[i], { opacity: 1, duration: 0.2 }, "<");

      // 2. Line lights up emerald
      tl.to(
        lines[i],
        {
          opacity: 1,
          stroke: ACCENT_LINE,
          duration: 0.18,
        },
        "<+0.05",
      );

      // 3. Signal travels from toggle → icon
      tl.fromTo(
        signals[i],
        { attr: { cx: 0 }, opacity: 0 },
        {
          attr: { cx: 100 },
          opacity: 1,
          duration: 0.42,
          ease: "power2.inOut",
        },
        "<",
      );

      // 4. Signal arrives - icon lights up
      tl.to(
        iconWraps[i],
        {
          backgroundColor: "oklch(0.62 0.15 150 / 0.18)",
          borderColor: ACCENT_LINE,
          boxShadow: `0 0 22px oklch(0.62 0.15 150 / 0.45)`,
          scale: 1.08,
          duration: 0.3,
          ease: "power2.out",
        },
        "<+0.32",
      );
      tl.to(
        signals[i],
        { opacity: 0, duration: 0.18 },
        "<",
      );
    });

    tl.to({}, { duration: 1.4 });

    return () => {
      tl.kill();
    };
  }, []);

  return (
    <SceneFrame innerRef={containerRef}>
      <div
        className="absolute act-rows"
        style={{
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 14,
        }}
      >
        <style>{`
          .act-rows { padding: 20px 18px; }
          .act-icon-wrap { width: 40px; height: 40px; }
          @media (min-width: 768px) {
            .act-rows { padding: 32px 32px; gap: 18px; }
            .act-icon-wrap { width: 48px; height: 48px; }
          }
        `}</style>
        {ACT_TOGGLES.map((t, i) => (
          <div
            key={t.id}
            ref={(node) => {
              rowRefs.current[i] = node;
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
            }}
          >
            {/* Toggle */}
            <div
              ref={(node) => {
                trackRefs.current[i] = node;
              }}
              style={{
                position: "relative",
                width: 44,
                height: 26,
                borderRadius: 999,
                background: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.10)",
                flexShrink: 0,
                transition: "background-color 0.18s",
              }}
            >
              <div
                ref={(node) => {
                  knobRefs.current[i] = node;
                }}
                style={{
                  position: "absolute",
                  left: 3,
                  top: 3,
                  width: 18,
                  height: 18,
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.60)",
                  willChange: "transform, background-color",
                }}
              />
            </div>

            {/* Action label */}
            <span
              style={{
                fontFamily: "Geist, sans-serif",
                fontSize: 14,
                color: INK,
                fontWeight: 500,
                minWidth: 64,
                flexShrink: 0,
              }}
            >
              {t.action}
            </span>

            {/* Signal line (fills remaining space) */}
            <div style={{ flex: 1, position: "relative", height: 12 }}>
              <svg
                width="100%"
                height="12"
                viewBox="0 0 100 12"
                preserveAspectRatio="none"
                style={{ display: "block", overflow: "visible" }}
              >
                <line
                  ref={(node) => {
                    lineRefs.current[i] = node;
                  }}
                  x1="0"
                  y1="6"
                  x2="100"
                  y2="6"
                  stroke="rgba(255,255,255,0.18)"
                  strokeWidth="0.6"
                  strokeDasharray="2 2.5"
                  opacity="0.35"
                />
                <circle
                  ref={(node) => {
                    signalRefs.current[i] = node;
                  }}
                  cx="0"
                  cy="6"
                  r="2"
                  fill={ACCENT}
                  opacity="0"
                  style={{ filter: `drop-shadow(0 0 4px ${ACCENT})` }}
                />
              </svg>
            </div>

            {/* Destination icon - larger, glows when signal arrives */}
            <div
              ref={(node) => {
                iconWrapRefs.current[i] = node;
              }}
              className="act-icon-wrap"
              style={{
                flexShrink: 0,
                borderRadius: 999,
                background: "oklch(0.10 0.005 75)",
                border: "1px solid rgba(255,255,255,0.10)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                transition: "background-color 0.2s, border-color 0.2s",
                willChange: "transform, box-shadow",
              }}
            >
              <SourceIcon id={t.id} size={22} tinted={t.id !== "notion"} />
            </div>
          </div>
        ))}
      </div>
    </SceneFrame>
  );
}
