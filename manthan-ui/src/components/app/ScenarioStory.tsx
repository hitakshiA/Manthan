/**
 * ScenarioStory - full-screen takeover overlay that walks the operator
 * through a guided narrative before firing a demo scenario.
 *
 * Behavior per the user's spec:
 *  • Full-screen (no sidebar, no inbox chrome behind it)
 *  • Manual advance: arrow-right / ▶ to next, arrow-left / ◀ to prev
 *  • NO skip - operator must reach the final slide before the CTA appears
 *  • Final slide shows the "Begin investigation" CTA which fires the
 *    scenario via the same onFire callback the ScenarioCard uses today
 *  • Esc closes the overlay (cancels - does NOT fire)
 *  • Image-left + caption-right two-column layout; caption is in the
 *    editorial-memo voice (Spectral italic), image takes ~55% of the
 *    viewport width
 */

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, ArrowRight, Loader2, X } from "lucide-react";

import { type ScenarioStory as Story } from "@/lib/scenarioStory";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { getSource } from "@/lib/sources";

interface Props {
  story: Story;
  /** Scenario id for analytics + the close handler. */
  scenarioId: string;
  /** Called when the operator clicks the final-slide CTA. */
  onFire: () => void;
  /** Called when the operator presses Esc / clicks the X close. */
  onClose: () => void;
  /** Pass-through: true while the case is being seeded. */
  firing?: boolean;
  /** The operator's own login email. When provided, the last slide
   *  surfaces a heads-up that the customer email will land here once
   *  the operator approves - replacing the env-level demo override. */
  userEmail?: string | null;
}

export function ScenarioStory({
  story,
  scenarioId: _scenarioId,
  onFire,
  onClose,
  firing,
  userEmail,
}: Props) {
  const [idx, setIdx] = useState(0);
  const slides = story.slides;
  const slide = slides[idx];
  const isLast = idx === slides.length - 1;
  const isFirst = idx === 0;

  const advance = useCallback(() => {
    if (firing) return;
    setIdx((i) => Math.min(i + 1, slides.length - 1));
  }, [firing, slides.length]);

  const back = useCallback(() => {
    if (firing) return;
    setIdx((i) => Math.max(i - 1, 0));
  }, [firing]);

  // Keyboard nav.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (firing) return;
      if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        advance();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        back();
      } else if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [advance, back, onClose, firing]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
      className="fixed inset-0 flex flex-col"
      style={{
        zIndex: 100,
        background: "var(--color-bg)",
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Scenario story walkthrough"
    >
      {/* TOP BAR - slide indicator + close. No "Skip" affordance per
          spec: the operator must walk the whole story. */}
      <header
        className="shrink-0 flex items-center px-9 py-5"
        style={{ borderBottom: "1px solid var(--color-rule-soft)" }}
      >
        <span
          className="text-[11px] uppercase"
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            color: "var(--color-ink-faint)",
            letterSpacing: "0.20em",
          }}
        >
          Story · {idx + 1} of {slides.length}
        </span>

        <div className="ml-6 inline-flex items-center gap-1.5">
          {slides.map((_, i) => (
            <span
              key={i}
              aria-hidden
              style={{
                width: i === idx ? 18 : 6,
                height: 4,
                borderRadius: 2,
                background:
                  i < idx
                    ? "var(--color-accent)"
                    : i === idx
                      ? "var(--color-accent)"
                      : "var(--color-rule)",
                transition: "width 200ms ease, background 200ms ease",
              }}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Cancel and close"
          className="ml-auto inline-flex items-center gap-2 text-[12px] uppercase outline-none transition-opacity hover:opacity-80"
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            color: "var(--color-ink-muted)",
            letterSpacing: "0.20em",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: "4px 6px",
          }}
        >
          <X size={14} strokeWidth={2} />
          Cancel
        </button>
      </header>

      {/* BODY - two-column image + caption. The image swaps with a
          cross-fade keyed on the slide index. */}
      <div
        className="flex-1 min-h-0 grid"
        style={{
          gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
        }}
      >
        {/* LEFT - image. We deliberately do NOT use AnimatePresence
            mode="wait" here because back-to-back clicks of NEXT made
            the exit animation block and the slide content would freeze
            at index 1 while the indicator advanced. Plain <img> with
            a key swap is enough - the browser caches the WebP so the
            second-half-of-story slides flip instantly. */}
        <div
          className="relative overflow-hidden flex items-center justify-center"
          style={{ background: "var(--color-surface)" }}
        >
          <motion.img
            key={slide.image}
            src={slide.image}
            alt={slide.heading}
            width={1376}
            height={768}
            decoding="async"
            loading="eager"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
            className="absolute inset-0 w-full h-full object-cover"
            draggable={false}
          />
        </div>

        {/* RIGHT - caption. Scrolls internally on the data-heavy
            slides (the source-breakdown one) so nothing gets clipped. */}
        <div className="overflow-y-auto">
          <div className="flex flex-col justify-center min-h-full px-16 py-14 max-w-[760px]">
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.28,
                ease: [0.22, 0.61, 0.36, 1],
              }}
            >
                {slide.eyebrow && (
                  <div
                    className="text-[12px] uppercase"
                    style={{
                      fontFamily: "Geist Mono, ui-monospace, monospace",
                      color: "var(--color-ink-faint)",
                      letterSpacing: "0.24em",
                    }}
                  >
                    {slide.eyebrow}
                  </div>
                )}

                <h2
                  className="mt-5 leading-[1.05]"
                  style={{
                    fontFamily: "Spectral, serif",
                    fontStyle: "italic",
                    fontSize: "clamp(40px, 4.2vw, 56px)",
                    color: "var(--color-ink-strong)",
                    letterSpacing: "-0.014em",
                    fontWeight: 400,
                  }}
                >
                  {slide.heading}
                </h2>

                <BodyText body={slide.body} />

                {slide.sources && slide.sources.length > 0 && (
                  <SourceList beats={slide.sources} />
                )}

                {slide.footer && (
                  <div
                    className="mt-7 text-[12.5px] tabular-nums"
                    style={{
                      fontFamily: "Geist Mono, ui-monospace, monospace",
                      color: "var(--color-ink-faint)",
                      letterSpacing: "0.04em",
                      lineHeight: 1.6,
                    }}
                  >
                    {slide.footer}
                  </div>
                )}
            </motion.div>
          </div>
        </div>
      </div>

      {/* BOTTOM BAR - nav arrows + (on last slide) the fire CTA. */}
      <footer
        className="shrink-0 flex items-center px-9 py-5 gap-6"
        style={{ borderTop: "1px solid var(--color-rule-soft)" }}
      >
        <NavButton
          dir="back"
          onClick={back}
          disabled={isFirst || firing}
          label="Back"
        />
        <NavButton
          dir="next"
          onClick={advance}
          disabled={isLast || firing}
          label="Next"
        />

        <div className="ml-auto inline-flex items-center gap-5">
          {isLast && userEmail && (
            <span
              className="inline-flex items-baseline gap-1.5 text-[12.5px]"
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                color: "var(--color-ink-muted)",
                letterSpacing: "-0.003em",
                maxWidth: "48ch",
              }}
            >
              Any customer email Manthan drafts will be sent to
              <span
                className="not-italic font-mono"
                style={{
                  fontSize: 12,
                  color: "var(--color-ink)",
                  letterSpacing: "-0.005em",
                  fontStyle: "normal",
                }}
              >
                {userEmail}
              </span>
              for this demo.
            </span>
          )}
          {isLast && (
            <button
              type="button"
              onClick={onFire}
              disabled={firing}
              className="inline-flex items-center gap-2.5 px-6 py-3 outline-none disabled:opacity-60"
              style={{
                background: "var(--color-accent)",
                color: "#0a0a0a",
                borderRadius: 5,
                fontFamily: "Geist, sans-serif",
                fontSize: 14,
                fontWeight: 500,
                letterSpacing: "-0.002em",
                border: "none",
                cursor: firing ? "default" : "pointer",
                transition: "transform 160ms ease, opacity 160ms ease",
                boxShadow: "0 10px 28px var(--color-accent-soft)",
              }}
            >
              {firing ? (
                <Loader2 size={14} strokeWidth={2.4} className="animate-spin" />
              ) : (
                <span aria-hidden style={{ fontSize: 16 }}>
                  ▶
                </span>
              )}
              {firing ? "Seeding the case…" : story.ctaLabel}
            </button>
          )}
        </div>
      </footer>
    </motion.div>
  );
}

/**
 * BodyText - render the slide body, which may be a single string or
 * an array of paragraphs. Spectral serif at a substantial size - this
 * is the meat of the story, not a side caption.
 */
function BodyText({ body }: { body: string | string[] }) {
  const paragraphs = Array.isArray(body) ? body : [body];
  return (
    <div className="mt-7 space-y-5">
      {paragraphs.map((p, i) => (
        <p
          key={i}
          className="leading-[1.55]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: 20,
            color: "var(--color-ink)",
            letterSpacing: "-0.003em",
            maxWidth: "62ch",
          }}
        >
          {p}
        </p>
      ))}
    </div>
  );
}

/**
 * SourceList - the structured "what each source contributes" block.
 * Used on the slide that breaks down why the agent has to query
 * eight different systems. Each row: brand icon + brand-colored
 * source name + one-line explanation in editorial prose.
 */
function SourceList({ beats }: { beats: { src: string; what: string }[] }) {
  return (
    <ol
      className="mt-7 space-y-3"
      style={{ borderTop: "1px solid var(--color-rule-soft)", paddingTop: 18 }}
    >
      {beats.map((beat) => (
        <li
          key={beat.src}
          className="grid items-baseline"
          style={{
            gridTemplateColumns: "150px minmax(0, 1fr)",
            columnGap: 18,
            paddingBottom: 12,
            borderBottom: "1px solid var(--color-rule-soft)",
          }}
        >
          <div className="inline-flex items-baseline gap-2">
            <span
              aria-hidden
              style={{ display: "inline-flex", transform: "translateY(2px)" }}
            >
              <SourceIcon id={beat.src} size={14} tinted />
            </span>
            <span
              className="text-[14px]"
              style={{
                color: brandHexFor(beat.src),
                fontFamily: "Spectral, serif",
                fontWeight: 500,
                letterSpacing: "-0.003em",
              }}
            >
              {prettyName(beat.src)}
            </span>
          </div>
          <p
            className="text-[15px] leading-[1.5]"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-muted)",
              letterSpacing: "-0.002em",
            }}
          >
            {beat.what}
          </p>
        </li>
      ))}
    </ol>
  );
}

function brandHexFor(slug: string): string {
  const meta = getSource(slug);
  const hex = meta?.simpleIcon?.hex;
  if (!hex) return "var(--color-ink-strong)";
  const EXTREME = new Set(["000000", "FFFFFF", "FDFDFD", "FEFEFE"]);
  if (EXTREME.has(hex.toUpperCase())) return "var(--color-ink-strong)";
  return `#${hex}`;
}

function prettyName(slug: string): string {
  const overrides: Record<string, string> = {
    hubspot: "HubSpot",
    pagerduty: "PagerDuty",
    posthog: "PostHog",
    github: "GitHub",
  };
  return overrides[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

function NavButton({
  dir,
  onClick,
  disabled,
  label,
}: {
  dir: "back" | "next";
  onClick: () => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="inline-flex items-center gap-2 px-4 py-2 outline-none disabled:opacity-30 transition-opacity"
      style={{
        background: "transparent",
        border: "1px solid var(--color-rule)",
        borderRadius: 4,
        color: "var(--color-ink)",
        cursor: disabled ? "default" : "pointer",
        fontFamily: "Geist Mono, ui-monospace, monospace",
        fontSize: 11,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
      }}
    >
      {dir === "back" ? (
        <>
          <ArrowLeft size={13} strokeWidth={2.2} />
          {label}
        </>
      ) : (
        <>
          {label}
          <ArrowRight size={13} strokeWidth={2.2} />
        </>
      )}
    </button>
  );
}
