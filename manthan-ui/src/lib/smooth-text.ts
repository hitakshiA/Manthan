/**
 * Smooth-streaming text engine.
 *
 * The frontend receives AI-generated text in bursty chunks — whole
 * narrative events arrive at once, SSE tokens clump into multi-char
 * delta frames, markdown re-parses on every update. Dumping each
 * chunk straight into the DOM produces a visual stutter that makes
 * the system feel slower than it is, even when TTFT is fast.
 *
 * This module decouples ingestion from presentation with a jitter
 * buffer. Call ``useSmoothText(fullText, { streamKey, isStreaming })``
 * with the complete accumulated text on every render. The engine
 * holds a single cursor into that text and advances it at an adaptive
 * cadence (72 cps baseline, up to 420 cps when catching up) on each
 * animation frame. The hook returns the currently-visible prefix.
 *
 * Pattern credit: coder/coder's ``SmoothText`` (jitter-buffer, budget
 * gated reveal, grapheme safety) and get-convex/agent's ``useSmoothText``
 * (simple hook API, persistent refs). Blended here into one tunable
 * primitive we can reuse across every AI-text surface.
 *
 * Why not batch-on-interval / debounce: those still produce bursty
 * jumps whenever a chunk lands between tick boundaries, and they
 * couple DOM update frequency to chunk arrival. A rAF loop with
 * fractional-char budget accumulation is frame-rate invariant (60Hz
 * and 240Hz displays reveal the same amount over wall-clock time) and
 * the cadence stays smooth regardless of how the upstream sends data.
 */

import { useEffect, useRef, useState } from "react";

export const SMOOTH_STREAM = {
  /** Baseline reveal speed. Matches a fast-human-reading pace. */
  BASE_CPS: 72,
  /** Ceiling — caps how fast we will catch up on a huge backlog. */
  MAX_CPS: 420,
  /** Backlog (chars) at which we run at MAX_CPS. Linear below. */
  CATCHUP_BACKLOG: 180,
  /** If the visible cursor lags by more than this, snap forward. */
  MAX_VISUAL_LAG: 120,
  /** Max chars revealed in a single animation frame (prevents a
   *  240Hz display from burning through the buffer in a tick). */
  MAX_FRAME_CHARS: 48,
} as const;

const _segmenter: Intl.Segmenter | null = (() => {
  try {
    return new Intl.Segmenter("en", { granularity: "grapheme" });
  } catch {
    return null;
  }
})();

/** Slice ``text[0..end]`` at the nearest grapheme-cluster boundary
 *  ≤ end. Prevents emoji / combining marks from splitting mid-animation
 *  (which would render replacement glyphs for one frame). */
function graphemeSafeSlice(text: string, end: number): string {
  if (end <= 0) return "";
  if (end >= text.length) return text;
  if (!_segmenter) return text.slice(0, end);
  let lastBoundary = 0;
  for (const seg of _segmenter.segment(text)) {
    if (seg.index > end) break;
    lastBoundary = seg.index;
  }
  return text.slice(0, lastBoundary);
}

interface SmoothTextOptions {
  /** Identity of this stream. When it changes, the engine resets
   *  (cursor back to 0, visible text cleared). Use the block id,
   *  message id, or anything that uniquely identifies the stream. */
  streamKey?: string | number;
  /** Whether upstream is still producing tokens. When false, the
   *  remaining buffer flushes to the DOM immediately — no trailing
   *  typewriter animation after the stream closes. */
  isStreaming?: boolean;
  /** Skip smoothing and render ``text`` as-is. Useful for short
   *  labels or when the user disables motion. */
  bypass?: boolean;
}

interface SmoothTextResult {
  visibleText: string;
  isAnimating: boolean;
}

interface EngineState {
  cursor: number;
  budget: number;
  lastTick: number;
  streamKey: string | number | undefined;
}

export function useSmoothText(
  text: string,
  options: SmoothTextOptions = {},
): SmoothTextResult {
  const { streamKey, isStreaming = true, bypass = false } = options;

  // Bypass path — render text as-is, no animation, no rAF loop. We
  // still use state so the public return shape stays stable across
  // modes (no conditional hook counts).
  const [visible, setVisible] = useState<string>(bypass ? text : "");

  const stateRef = useRef<EngineState>({
    cursor: 0,
    budget: 0,
    lastTick: 0,
    streamKey,
  });

  // Stream-key change → hard reset. Doing this in an effect keeps the
  // reducer-like reset atomic with the next paint.
  useEffect(() => {
    if (stateRef.current.streamKey !== streamKey) {
      stateRef.current = {
        cursor: 0,
        budget: 0,
        lastTick: 0,
        streamKey,
      };
      setVisible(bypass ? text : "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamKey]);

  useEffect(() => {
    if (bypass) {
      // If we flip into bypass mid-stream, snap to full text.
      stateRef.current.cursor = text.length;
      setVisible(text);
      return;
    }

    // If text shrank (new turn / reset), reset cursor.
    if (stateRef.current.cursor > text.length) {
      stateRef.current.cursor = 0;
      stateRef.current.budget = 0;
      setVisible("");
    }

    let rafId = 0;
    stateRef.current.lastTick = performance.now();

    const tick = (now: number) => {
      const s = stateRef.current;
      const elapsed = Math.max(0, now - s.lastTick);
      s.lastTick = now;

      const backlog = text.length - s.cursor;

      if (backlog <= 0) {
        // Nothing to reveal. If upstream is done, stop the loop.
        // Otherwise keep ticking cheaply so we're ready when new
        // text lands.
        if (!isStreaming) return;
        rafId = requestAnimationFrame(tick);
        return;
      }

      // Stream closed and buffer is small — flush instantly so the
      // user isn't left watching a tail animation after the agent
      // is clearly done.
      if (!isStreaming && backlog <= SMOOTH_STREAM.MAX_FRAME_CHARS) {
        s.cursor = text.length;
        s.budget = 0;
        setVisible(text);
        return;
      }

      // Gap too wide — snap forward to cap visual lag.
      if (backlog > SMOOTH_STREAM.MAX_VISUAL_LAG) {
        s.cursor = Math.max(
          s.cursor,
          text.length - SMOOTH_STREAM.MAX_VISUAL_LAG,
        );
      }

      // Adaptive CPS — linear between base and max based on backlog.
      const pressure = Math.min(
        1,
        (text.length - s.cursor) / SMOOTH_STREAM.CATCHUP_BACKLOG,
      );
      const cps =
        SMOOTH_STREAM.BASE_CPS +
        (SMOOTH_STREAM.MAX_CPS - SMOOTH_STREAM.BASE_CPS) * pressure;
      const cpms = cps / 1000;

      s.budget += elapsed * cpms;
      const wholeChars = Math.floor(s.budget);
      if (wholeChars > 0) {
        const reveal = Math.min(
          wholeChars,
          SMOOTH_STREAM.MAX_FRAME_CHARS,
          text.length - s.cursor,
        );
        s.budget -= reveal;
        s.cursor += reveal;
        setVisible(graphemeSafeSlice(text, s.cursor));
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [text, isStreaming, bypass]);

  return {
    visibleText: visible,
    isAnimating: stateRef.current.cursor < text.length,
  };
}
