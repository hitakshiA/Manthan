/**
 * Manthan landing page.
 *
 * Copy patterns lifted from Linear / Vercel / Metabase / Warp:
 *   - noun-phrase hero, verb-led section heads
 *   - short → long with comma → short rhythm
 *   - dual CTA (cloud + OSS) per Metabase
 *   - jargon nuked: leverage / empower / streamline / seamless / unified
 *
 * Visuals follow the Neuralyn structure but with the hero text + dashboard
 * laid out as non-overlapping bands inside the viewport, not stacked.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AnimatePresence,
  motion,
  useScroll,
  useTransform,
  useMotionTemplate,
} from "motion/react";
import {
  ArrowRight,
  Check,
  Play,
  Quote,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Show } from "@clerk/react";
import { Logo } from "@/components/Logo";
import { useLockedTheme } from "@/lib/theme";
import { LandingHeroDemo } from "@/components/landing/LandingHeroDemo";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { HeroShowcase } from "@/components/marketing/HeroShowcase";
import {
  WatchScene,
  InvestigateScene,
  ActScene,
} from "@/components/marketing/HowItWorksScenes";
import { BILLING_OPS_STACK, getSource } from "@/lib/sources";
import gsap from "gsap";

const HERO_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260307_083826_e938b29f-a43a-41ec-a153-3d4730578ab8.mp4";

const FOOTER_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260330_145725_08886141-ed95-4a8e-8d6d-b75eaadce638.mp4";

export default function Landing() {
  // Marketing page is composed around dark - every gradient, every hairline,
  // every text colour assumes the warm-near-black bg. If the operator has
  // toggled the workspace to light, we lock landing back to dark while
  // they're here. Stored preference for /app is preserved.
  useLockedTheme("dark");

  return (
    <div
      className="min-h-screen"
      style={{
        background: "#000",
        color: "oklch(0.95 0.004 75)",
      }}
    >
      <Section1Hero />
      <Section2Manifesto />
      <StackStrip />
      <HowItWorks />
      <CaseAnatomy />
      <Pricing />
      <Footer />
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   SECTION 1 - HERO
   Video as section background. Hero copy in upper band.
   Dashboard peeks from below, no overlap with text.
   ═════════════════════════════════════════════════════════════════════ */

function Section1Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });

  const heroY = useTransform(scrollYProgress, [0, 1], [0, -120]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0]);

  return (
    <section
      ref={sectionRef}
      className="relative overflow-hidden"
      style={{ background: "#000" }}
    >
      {/* NAVBAR - minimal: brand left, auth right ─────────────────────── */}
      <nav className="relative z-30 px-6 md:px-12 lg:px-20 py-5 flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-2.5 hover:opacity-90 transition-opacity"
        >
          <Logo size={26} showWordmark={false} className="text-white" />
          <span className="text-lg font-semibold tracking-tight text-white">
            Manthan
          </span>
        </Link>
        <div className="flex items-center gap-3">
          {/* Landing is marketing-first: always pitch sign-in / sign-up
              regardless of auth state. Signed-in users who actually
              want their workspace navigate there from the app itself
              (sidebar), not from the marketing page. */}
          <Link
            to="/login"
            className="text-sm hover:opacity-90 transition-opacity"
            style={{ color: "rgba(255,255,255,0.72)" }}
          >
            Sign in
          </Link>
          <Link to="/signup">
            <button
              className="rounded-lg text-sm font-semibold px-4 py-2 hover:opacity-90 transition-opacity"
              style={{ background: "#fff", color: "#000" }}
            >
              Sign up
            </button>
          </Link>
        </div>
      </nav>

      {/* HERO COPY ─ upper band, doesn't collide with dashboard ──────────── */}
      <motion.div
        style={{ y: heroY, opacity: heroOpacity }}
        className="relative z-20 px-6 mt-10 md:mt-14 flex flex-col items-center text-center"
      >
        {/* Announcement pill - now points at the latest essay. Becomes
            a Link so the whole pill is clickable; subtle hover lift +
            border highlight signals it's tappable without screaming. */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0 }}
          className="mb-6"
        >
          <Link
            to="/blog/tokens-are-the-new-salary"
            className="liquid-glass inline-flex items-center gap-2 px-3 py-2 rounded-lg transition-all duration-200 hover:-translate-y-[1px]"
            style={{
              textDecoration: "none",
              color: "inherit",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow =
                "0 0 0 1px rgba(255,255,255,0.18) inset, 0 8px 22px rgba(0,0,0,0.18)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = "";
            }}
          >
            <span
              className="rounded-md text-sm font-medium px-2 py-0.5"
              style={{ background: "#fff", color: "#000" }}
            >
              Blog
            </span>
            <span
              className="text-sm font-medium"
              style={{ color: "rgba(255,255,255,0.78)" }}
            >
              Tokens are the new salary
            </span>
            <span
              className="text-sm"
              style={{ color: "rgba(255,255,255,0.55)" }}
              aria-hidden
            >
              →
            </span>
          </Link>
        </motion.div>

        {/* Headline - operations framing, italic wedge accent */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-5xl md:text-7xl tracking-[-0.03em] font-medium leading-[1.02] md:leading-[1.04] mb-5 max-w-3xl"
        >
          The operations layer for
          <br />
          <em className="font-serif italic font-normal">revenue disputes.</em>
        </motion.h1>

        {/* Subtitle - outcome-first, then proof */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-base md:text-lg leading-snug mb-8 max-w-xl"
          style={{ color: "oklch(0.80 0.005 75)" }}
        >
          Settles chargebacks, failed payments, and refund requests in minutes,
          not days. Reads payments, CRM, support, and policy in one
          investigation. <span className="text-white">Cites every claim.</span>
        </motion.p>

        {/* Single primary CTA - iridescent gradient (pink → lavender → cyan → mint) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <HeroDemoCTA />
        </motion.div>

      </motion.div>

      {/* SHOWCASE - full-bleed 16/9 frame with video bg + luminosity blend.
          IMPORTANT: no transforms on any ancestor of the blend element, or
          mix-blend-mode loses access to the video underneath. */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.4 }}
        className="relative w-screen mt-2 md:mt-4"
        style={{ marginLeft: "calc(-50vw + 50%)" }}
      >
        <div className="relative w-full overflow-hidden" style={{ aspectRatio: "16 / 9" }}>
          {/* Background video - fills the 16/9 frame */}
          <video
            src={HERO_VIDEO}
            autoPlay
            muted
            loop
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          />

          {/* The animated workflow showcase - replaces the old (outdated)
              TechCorp dashboard preview. Loops through investigating →
              review → approving → closed every ~50 seconds, so visitors
              see the whole product story without scrolling. Pauses
              automatically when scrolled out of view.

              Desktop-only (the demo is fixed-aspect-ratio and would
              compress badly on phones). Mobile keeps the hero video +
              copy without the showcase, which is the right hierarchy
              for thumb-driven discovery anyway. */}
          <div className="absolute inset-0 hidden md:flex items-start justify-center pt-[2%] md:pt-[3%]">
            <div className="max-w-4xl w-[72%]">
              <LandingHeroDemo />
            </div>
          </div>

          {/* Bottom gradient fade - black → warm-dark so the next section blends in */}
          <div
            className="absolute bottom-0 left-0 right-0 h-48 z-30 pointer-events-none"
            style={{
              background:
                "linear-gradient(180deg, transparent 0%, #000 100%)",
            }}
          />
        </div>
      </motion.div>
    </section>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   SECTION 2 - MANIFESTO (scroll-driven word reveal)
   Product principle, no founder, no fabricated team.
   ═════════════════════════════════════════════════════════════════════ */

function Section2Manifesto() {
  const containerRef = useRef<HTMLDivElement>(null);
  // Reveal completes when the section center hits viewport center -
  // i.e. by the time the user is reading the manifesto, every word is lit.
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start 0.85", "center center"],
  });

  const line =
    "Stripe alone never tells the whole story. Manthan joins payments with your CRM, your tickets, your policy doc, and your product usage. It drafts the reply, fires the action, and cites every claim.";
  const words = line.split(" ");

  return (
    <section
      ref={containerRef}
      className="relative flex items-center pt-40 md:pt-56 pb-56 md:pb-72 px-6 md:px-20"
      style={{ background: "#000" }}
    >
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-120px" }}
        transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1] }}
        className="max-w-4xl mx-auto w-full flex flex-col items-start gap-8"
      >
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-120px" }}
          transition={{ duration: 0.5, ease: [0.25, 1, 0.5, 1], delay: 0.05 }}
          className="flex items-center gap-3"
        >
          <Quote
            className="w-9 h-9"
            strokeWidth={1.6}
            style={{ color: "oklch(0.62 0.15 150)" }}
          />
          <span
            className="text-[11px] uppercase"
            style={{
              color: "oklch(0.55 0.006 75)",
              letterSpacing: "0.18em",
              fontWeight: 600,
            }}
          >
            How Manthan works
          </span>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-120px" }}
          transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1], delay: 0.12 }}
          className="text-3xl md:text-5xl font-medium leading-[1.18] tracking-[-0.02em] flex flex-wrap"
          style={{ color: "oklch(0.95 0.004 75)" }}
        >
          {words.map((word, i) => (
            <Word
              key={i}
              word={word}
              progress={scrollYProgress}
              range={[i / words.length, (i + 1) / words.length]}
            />
          ))}
        </motion.div>

      </motion.div>
    </section>
  );
}

function Word({
  word,
  progress,
  range,
}: {
  word: string;
  progress: ReturnType<typeof useScroll>["scrollYProgress"];
  range: [number, number];
}) {
  const opacity = useTransform(progress, range, [0.18, 1]);
  const colorMix = useTransform(progress, range, [0, 1]);
  const color = useMotionTemplate`hsl(0 0% ${useTransform(
    colorMix,
    [0, 1],
    [32, 100],
  )}%)`;
  return (
    <motion.span style={{ opacity, color }} className="mr-[0.3em]">
      {word}
    </motion.span>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   STACK STRIP - eyebrow + infinite marquee of source icons.
   No labels. No sub-headline. No footnote. Just the icons moving.
   ═════════════════════════════════════════════════════════════════════ */

/** Brand colors that disappear on dark backgrounds - render icon white. */
const WHITE_ICON_OVERRIDE: Record<string, true> = {
  notion: true,
};

/* ─── HLS video helper ────────────────────────────────────────────────────
   Chrome/Firefox can't play m3u8 natively - load hls.js dynamically.
   Safari has native HLS support, so we skip the polyfill there.
   ─────────────────────────────────────────────────────────────────────── */
function HlsVideo({
  src,
  className,
  style,
}: {
  src: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    // Safari + iOS - native HLS
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      return;
    }
    let destroyed = false;
    let hls: { destroy: () => void } | null = null;
    import("hls.js").then(({ default: Hls }) => {
      if (destroyed) return;
      if (Hls.isSupported()) {
        const instance = new Hls({ enableWorker: true });
        instance.loadSource(src);
        instance.attachMedia(video);
        hls = instance;
      } else {
        video.src = src;
      }
    });
    return () => {
      destroyed = true;
      if (hls) hls.destroy();
    };
  }, [src]);

  return (
    <video
      ref={videoRef}
      className={className}
      style={style}
      autoPlay
      loop
      muted
      playsInline
      preload="auto"
    />
  );
}

const STACK_VIDEO =
  "https://stream.mux.com/tLkHO1qZoaaQOUeVWo8hEBeGQfySP02EPS02BmnNFyXys.m3u8";

function StackStrip() {
  // Duplicate the list so the marquee loop is seamless at translateX(-50%).
  // We use per-item padding (no gap on parent) so -50% lands EXACTLY at the
  // start of the second copy - no visible seam at the wrap point.
  const loop = [...BILLING_OPS_STACK, ...BILLING_OPS_STACK];

  // ─── macOS-dock magnification on hover ─────────────────────────────────
  // Pauses the marquee while the cursor is inside, then scales each icon
  // and pushes neighbors aside based on cursor proximity (cos/sin falloff).
  // Resumes the marquee on mouseleave.
  const marqueeRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const inner = innerRef.current;
    const outer = marqueeRef.current;
    if (!inner || !outer) return;

    const icons = Array.from(
      inner.querySelectorAll<HTMLDivElement>("[data-dock-icon]"),
    );
    if (icons.length === 0) return;

    // Tuning matches the Blake Bowen codepen (proportionally scaled to our
    // icon size). min = resting slot, max = peak scaled slot.
    const ICON_W = 124;
    const min = ICON_W + 14; // resting slot width (icon + gap)
    const max = min * 1.32;  // peak scale ~32%
    const bound = min * Math.PI;

    const onMove = (event: MouseEvent) => {
      const firstRect = icons[0].getBoundingClientRect();
      const pointer = event.clientX - firstRect.left;
      for (let i = 0; i < icons.length; i++) {
        const center = i * min + min / 2;
        const distance = center - pointer;
        let x = 0;
        let scale = 1;
        if (-bound < distance && distance < bound) {
          const rad = (distance / min) * 0.5;
          scale = 1 + (max / min - 1) * Math.cos(rad);
          x = 2 * (max - min) * Math.sin(rad);
        } else {
          x = (-bound < distance ? 2 : -2) * (max - min);
        }
        gsap.to(icons[i], { duration: 0.3, x, scale, ease: "power2.out" });
      }
    };

    const onEnter = () => {
      inner.style.animationPlayState = "paused";
    };
    const onLeave = () => {
      gsap.to(icons, { duration: 0.3, x: 0, scale: 1, ease: "power2.out" });
      inner.style.animationPlayState = "running";
    };

    outer.addEventListener("mouseenter", onEnter);
    outer.addEventListener("mousemove", onMove);
    outer.addEventListener("mouseleave", onLeave);
    return () => {
      outer.removeEventListener("mouseenter", onEnter);
      outer.removeEventListener("mousemove", onMove);
      outer.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return (
    <section className="relative px-6 py-24 md:py-32">
      {/* ── Hero card ────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
        className="relative mx-auto overflow-hidden flex flex-col"
        style={{
          maxWidth: 1400,
          // Mobile gets a shorter card; desktop keeps the dramatic 560 height.
          minHeight: 360,
          height: "clamp(360px, 65vw, 560px)",
          borderRadius: 28,
          background: "#0a0a0a",
          border: "1px solid rgba(255,255,255,0.06)",
          boxShadow: "0 40px 100px -20px rgba(0, 0, 0, 0.6)",
        }}
      >
        {/* Background video - HLS stream */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden select-none" style={{ zIndex: 0 }}>
          <HlsVideo
            src={STACK_VIDEO}
            className="w-full h-full object-cover"
            style={{ transform: "scale(1.05)", transition: "transform 1s" }}
          />
          {/* Soft dark vignette so text stays legible */}
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.25) 45%, rgba(0,0,0,0.85) 100%)",
            }}
          />
        </div>

        {/* Hero text - left-aligned */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1], delay: 0.1 }}
          className="relative flex-1 px-6 md:px-16 pt-10 md:pt-16 pb-10 md:pb-16 flex flex-col items-start"
          style={{ zIndex: 20 }}
        >
          <h2
            className="tracking-[-0.025em] leading-[1.05]"
            style={{
              fontSize: "clamp(2.25rem, 1.8rem + 2.4vw, 3.5rem)",
              fontWeight: 500,
              color: "oklch(0.98 0.003 75)",
              maxWidth: 560,
            }}
          >
            Plug into the stack
            <br />
            <span className="display-italic" style={{ fontWeight: 400 }}>
              your team already runs.
            </span>
          </h2>

          <p
            className="mt-6"
            style={{
              fontSize: "clamp(1.05rem, 1rem + 0.3vw, 1.25rem)",
              lineHeight: 1.6,
              color: "rgba(255,255,255,0.92)",
              maxWidth: 560,
              fontWeight: 400,
              textShadow: "0 1px 2px rgba(0,0,0,0.35)",
            }}
          >
            Stripe, Salesforce, Zendesk, Notion, Slack, Gmail, and your
            product analytics. Manthan reads them all in one investigation,
            and cites every record it touches.
          </p>
        </motion.div>
      </motion.div>

      {/* ── Marquee row - round logo cards, macOS-dock magnify on hover ── */}
      <motion.div
        ref={marqueeRef}
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1], delay: 0.25 }}
        className="relative mx-auto mt-10 overflow-hidden"
        style={{
          maxWidth: 1400,
          maskImage:
            "linear-gradient(90deg, transparent 0%, black 8%, black 92%, transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(90deg, transparent 0%, black 8%, black 92%, transparent 100%)",
          // Icons scale from their bottom edge, so they grow upward. Pad
          // the top of the masked container so the scaled-up icons stay
          // within the masked region instead of clipping at the top edge.
          paddingTop: 40,
          paddingBottom: 12,
        }}
      >
        <div
          ref={innerRef}
          className="animate-marquee flex items-end w-max"
          style={{ gap: 14 }}
        >
          {loop.map((id, i) => {
            const meta = getSource(id);
            const useWhite = WHITE_ICON_OVERRIDE[id] === true;
            return (
              <div
                key={`${id}-${i}`}
                data-dock-icon
                className="shrink-0 inline-flex items-center justify-center"
                style={{
                  height: 84,
                  width: 124,
                  borderRadius: 999,
                  background: "#0a0a0a",
                  border: "1px solid rgba(255,255,255,0.08)",
                  boxShadow: "0 2px 12px rgba(0,0,0,0.35)",
                  transformOrigin: "50% 100%",
                  willChange: "transform",
                }}
                aria-label={meta?.name}
              >
                <SourceIcon id={id} size={36} tinted={!useWhite} />
              </div>
            );
          })}
        </div>
      </motion.div>
    </section>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   HOW IT WORKS - verb-led step headers
   ═════════════════════════════════════════════════════════════════════ */

function HowItWorks() {
  const steps = [
    {
      num: "01",
      verb: "Watch.",
      copy:
        "Connect your billing stack, CRM, support tool, and Slack in a few clicks. Manthan listens for chargebacks, failed payments, refund requests, and dunning escalations, the moment they happen.",
      icons: ["stripe", "salesforce", "zendesk", "slack"],
    },
    {
      num: "02",
      verb: "Investigate.",
      copy:
        "Every case fires a cross-source investigation. Payment timeline, account context, support history, your policy doc, joined in seconds. Every claim cites its source.",
      icons: ["stripe", "salesforce", "zendesk", "notion"],
    },
    {
      num: "03",
      verb: "Act, within your gates.",
      copy:
        "Drafts the refund, the customer email, the CSM ticket, the Slack brief. Auto-executes under your thresholds. Escalates the rest to your approval queue.",
      icons: ["stripe", "gmail", "linear", "slack"],
    },
  ];

  return (
    <section id="how" className="pt-40 md:pt-56 pb-40 md:pb-56 px-6">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
          className="max-w-3xl mb-20"
        >
          <h2 className="text-4xl md:text-5xl tracking-[-0.03em] font-medium leading-[1.05]">
            From signal to a{" "}
            <em className="font-serif italic font-normal">resolved case.</em>
          </h2>
          <p
            className="mt-5 text-lg max-w-2xl"
            style={{ color: "oklch(0.70 0.006 75)" }}
          >
            Three steps. No prompt engineering. No multi-month integration
            project.
          </p>
        </motion.div>

        {/* Editorial step list - rules, not card boxes */}
        <div>
          {steps.map((s, i) => (
            <motion.div
              key={s.num}
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{
                duration: 0.6,
                ease: [0.25, 1, 0.5, 1],
                delay: i * 0.12,
              }}
              className="group relative grid items-start gap-x-10 gap-y-6 py-10 md:py-14 grid-cols-1 md:[grid-template-columns:minmax(0,auto)_minmax(0,1fr)_480px]"
              style={{
                borderTop: "1px solid var(--color-rule-soft)",
                borderBottom: i === steps.length - 1 ? "1px solid var(--color-rule-soft)" : "none",
              }}
            >
              {/* Step number - big italic serif, editorial */}
              <div
                className="display-italic select-none"
                style={{
                  color: "oklch(0.40 0.005 75)",
                  fontSize: "clamp(2.5rem, 5vw, 4rem)",
                  lineHeight: 1,
                  fontWeight: 400,
                  letterSpacing: "-0.02em",
                  minWidth: 72,
                }}
              >
                {s.num}
              </div>

              {/* Verb + body */}
              <div className="min-w-0 max-w-2xl">
                <h3
                  className="text-2xl md:text-3xl font-medium tracking-[-0.02em]"
                  style={{ color: "oklch(0.96 0.004 75)" }}
                >
                  {s.verb}
                </h3>
                <p
                  className="mt-3 text-base md:text-[17px] leading-relaxed"
                  style={{ color: "oklch(0.70 0.006 75)" }}
                >
                  {s.copy}
                </p>
              </div>

              {/* Animated workflow visual - directorially distinct per step */}
              <motion.div
                initial={{ opacity: 0, x: 16 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{
                  duration: 0.6,
                  ease: [0.25, 1, 0.5, 1],
                  delay: i * 0.12 + 0.18,
                }}
                className="self-center w-full"
              >
                {i === 0 && <WatchScene />}
                {i === 1 && <InvestigateScene />}
                {i === 2 && <ActScene />}
              </motion.div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}


/* ═════════════════════════════════════════════════════════════════════
   CASE ANATOMY - 6 product principle cards
   ═════════════════════════════════════════════════════════════════════ */

function CaseAnatomy() {
  return (
    <section
      id="anatomy"
      className="pt-40 md:pt-56 pb-40 md:pb-56 px-6"
      style={{
        background: "#000",
      }}
    >
      <div className="max-w-7xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
          className="max-w-3xl mb-16"
        >
          <h2 className="text-4xl md:text-5xl tracking-[-0.03em] font-medium leading-[1.05]">
            Every brief shows its work.
            <br />
            <em className="font-serif italic font-normal">
              Every action keeps a trail.
            </em>
          </h2>
        </motion.div>

        {/* Responsive bento - stacks to 1 column on mobile, 3 on md+.
            Fixed 540px row height only on md+ so mobile cards size to content. */}
        <div className="grid gap-5 grid-cols-1 md:grid-cols-3 md:[grid-auto-rows:540px]">
          <BentoCard
            delay={0}
            title="Cross-source by default"
            body="Stripe shows the chargeback. Salesforce shows the account is healthy. Zendesk shows no open tickets. Your refund policy lives in Notion. Manthan reads all four in one investigation, and every claim in the brief cites the exact record it came from."
            visual={<CrossSourceVisual />}
          />
          <BentoCard
            delay={0.08}
            title="HITL gates you control"
            body="You decide what Manthan can do alone and where it pauses for a human. Auto-resolve tiny refunds. Require one-click approval in the middle band. Demand two approvers above your threshold. Move the gates without writing a line of code."
            visual={<GatesVisual />}
          />
          <BentoCard
            delay={0.16}
            title="Briefs your CFO will sign"
            body="Every case lands as a plain-English memo, not a model dump. The TL;DR, the drafted actions, and the footnotes are all on one page. Each claim ends in a numbered citation linking straight to the source record. The kind of brief you forward without a second meeting."
            visual={<BriefVisual />}
          />
          <BentoCard
            delay={0.24}
            title="Rules you can read"
            body="Thresholds, escalation paths, retention plays. Every policy is a visual rule. Flip a switch, drag a slider, watch the projected impact on the next 30 days. No YAML to learn, no commit to review. A senior operator can shape the worker themselves."
            visual={<PolicyVisual />}
          />
          <BentoCard
            delay={0.32}
            title="Compounds with your team"
            body="Every approval, every edit, every override sharpens your dispute playbook. The policy graph learns which patterns your team trusts, which it overrides, and which it escalates. Drafts get faster, citations get tighter, and your team's judgement is what bends the curve. You hire Manthan once. It compounds."
            visual={<CompoundVisual />}
          />
          <BentoCard
            delay={0.4}
            title="Audit log on every action"
            body="Every model call, every drafted action, every human approver: timestamped, signed, and streamed to your SIEM in real time. The activity feed reads like prose, not a terminal log. SOC 2 evidence stops being a separate project."
            visual={<AuditVisual />}
          />
        </div>
      </div>
    </section>
  );
}

function BentoCard({
  delay,
  title,
  body,
  visual,
}: {
  delay: number;
  title: string;
  body: string;
  visual: React.ReactNode;
}) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.55, ease: [0.25, 1, 0.5, 1], delay }}
      className="relative rounded-2xl border overflow-hidden grid"
      style={{
        background: "oklch(0.175 0.006 75)",
        borderColor: "rgba(255,255,255,0.08)",
        gridTemplateRows: "300px 1px 1fr",
      }}
    >
      {/* Visual - fixed 300px so every card matches */}
      <div className="relative overflow-hidden">
        {visual}
      </div>

      {/* Divider */}
      <div style={{ background: "rgba(255,255,255,0.06)" }} />

      {/* Copy - fills the remaining ~239px uniformly, room for 4-5 lines */}
      <div className="px-6 py-5 flex flex-col justify-start">
        <h3
          className="text-[17px] tracking-[-0.01em]"
          style={{ color: "oklch(0.96 0.004 75)", fontWeight: 500 }}
        >
          {title}
        </h3>
        <p
          className="mt-2 text-[13px] leading-[1.6]"
          style={{ color: "oklch(0.68 0.006 75)" }}
        >
          {body}
        </p>
      </div>
    </motion.article>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   ANATOMY VISUALS - denser mini-product surfaces, not sparse diagrams.
   Each visual fills its card and shows a layered product moment.
   ═════════════════════════════════════════════════════════════════════ */

/* ─── 1. CROSS-SOURCE: source feed → joined brief ─────────────────── */

function CrossSourceVisual() {
  type N = 1 | 2 | 3 | 4;
  const lineage: Record<N, { srcId: string; label: string; record: string; finding: string }> = {
    1: {
      srcId: "salesforce",
      label: "Salesforce",
      record: "Account · TechCorp Industries",
      finding:
        "Growth Annual plan at $240K ARR. Last NPS scored 9/10. Health flagged “good” by the CSM four months ago, no escalations on file.",
    },
    2: {
      srcId: "stripe",
      label: "Stripe",
      record: "Customer · cus_8mFqZ",
      finding:
        "38 successful payments over 14 months and zero disputes prior to today. This is the first chargeback ever raised on this customer.",
    },
    3: {
      srcId: "zendesk",
      label: "Zendesk",
      record: "Last ticket · #8412",
      finding:
        "Billing inquiry closed 14 days ago in six minutes with CSAT 5/5. No open tickets, last six all resolved positive.",
    },
    4: {
      srcId: "notion",
      label: "Notion",
      record: "Policy · refunds.yaml",
      finding:
        "Refunds above $500 require a human nod when the customer is healthy. This $1,200 crosses the gate by $700. Needs your sign-off.",
    },
  };
  const [hovered, setHovered] = useState<N | null>(null);

  const Cite = ({ n }: { n: N }) => {
    const active = hovered === n;
    return (
      <button
        type="button"
        onMouseEnter={() => setHovered(n)}
        onMouseLeave={() => setHovered(null)}
        onFocus={() => setHovered(n)}
        onBlur={() => setHovered(null)}
        className="font-mono inline-flex"
        style={{
          fontSize: "0.72em",
          verticalAlign: "super",
          lineHeight: 0,
          padding: "0 0.15em",
          color: active ? "oklch(0.78 0.13 75)" : "oklch(0.62 0.15 150)",
          fontWeight: 600,
          cursor: "pointer",
          background: "transparent",
        }}
        aria-label={`Cite ${n}: ${lineage[n].label}`}
      >
        [{n}]
      </button>
    );
  };

  return (
    <div className="absolute inset-0 p-6 flex flex-col">
      {/* Eyebrow */}
      <div className="eyebrow flex items-baseline gap-2 mb-4">
        Brief · CASE-4821
        <span
          className="ml-auto normal-case tracking-normal text-[10px]"
          style={{ color: "oklch(0.50 0.006 75)" }}
        >
          {hovered ? `Source [${hovered}]` : "Hover [n] to trace"}
        </span>
      </div>

      {/* Header line - TechCorp / charge id */}
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-[13px]" style={{ color: "oklch(0.96 0.004 75)", fontWeight: 600 }}>
          TechCorp
        </span>
        <span className="tabular-nums font-mono text-[11px]" style={{ color: "oklch(0.55 0.006 75)" }}>
          ch_3MqXfL · $1,200
        </span>
      </div>

      {/* The body - brief sentence crossfades with lineage on hover */}
      <div className="relative flex-1 min-h-[68px]">
        <AnimatePresence mode="wait">
          {hovered === null ? (
            <motion.p
              key="brief"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.25, 1, 0.5, 1] }}
              className="absolute inset-0 text-[12.5px]"
              style={{ color: "oklch(0.80 0.006 75)", lineHeight: 1.7 }}
            >
              TechCorp Industries is a healthy, paying account<Cite n={1} /> with no prior chargebacks in 14 months<Cite n={2} />.
              Their last support thread closed cleanly two weeks ago<Cite n={3} />; the $1,200 amount crosses your manual-review gate<Cite n={4} />.
            </motion.p>
          ) : (
            <motion.div
              key={`lineage-${hovered}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22, ease: [0.25, 1, 0.5, 1] }}
              onMouseEnter={() => setHovered(hovered)}
              onMouseLeave={() => setHovered(null)}
              className="absolute inset-0 flex items-start gap-3"
            >
              <SourceMark id={lineage[hovered].srcId} iconSize={22} />
              <div className="min-w-0 flex-1">
                <div
                  className="text-[11px] font-mono flex items-baseline gap-1.5"
                  style={{ color: "oklch(0.58 0.006 75)" }}
                >
                  <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>[{hovered}]</span>
                  <span style={{ color: "oklch(0.88 0.005 75)" }}>{lineage[hovered].label}</span>
                  <span>·</span>
                  <span className="truncate">{lineage[hovered].record}</span>
                </div>
                <div
                  className="mt-1.5 text-[12.5px]"
                  style={{ color: "oklch(0.85 0.005 75)", lineHeight: 1.5 }}
                >
                  {lineage[hovered].finding}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer - recommendation always shown */}
      <div
        className="mt-3 pt-3 flex items-baseline gap-1.5 text-[11.5px]"
        style={{ borderTop: "1px solid oklch(0.22 0.005 75)" }}
      >
        <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>→</span>
        <span style={{ color: "oklch(0.85 0.005 75)" }}>
          refund · apology · CSM follow-up
        </span>
      </div>
    </div>
  );
}

function SourceMark({ id, iconSize = 16 }: { id: string; size?: number; iconSize?: number }) {
  const useWhite = WHITE_ICON_OVERRIDE[id] === true;
  return (
    <span className="inline-flex items-center justify-center shrink-0">
      <SourceIcon id={id} size={iconSize} tinted={!useWhite} />
    </span>
  );
}

/* ─── 2. GATES: decision tree with active path ──────────────────── */

function GatesVisual() {
  const [active, setActive] = useState(0);
  const branches = [
    { label: "< $50",   rate: "62%", action: "Auto-approve" },
    { label: "$50–500", rate: "28%", action: "One-click"     },
    { label: "> $500",  rate: "10%", action: "Two-person"    },
  ];
  const toneColor = (i: number) =>
    i === 0 ? "oklch(0.62 0.15 150)" : i === 1 ? "oklch(0.78 0.13 75)" : "oklch(0.70 0.006 75)";

  // ─── Refs for measuring actual box positions
  const containerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLDivElement | null>(null);
  const outputRefs = useRef<(HTMLButtonElement | null)[]>([null, null, null]);

  type CurveEnd = { sx: number; sy: number; ex: number; ey: number; d: string };
  const [curves, setCurves] = useState<CurveEnd[]>([]);
  const [box, setBox] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    const measure = () => {
      const container = containerRef.current;
      const input = inputRef.current;
      if (!container || !input) return;
      const cRect = container.getBoundingClientRect();
      const iRect = input.getBoundingClientRect();
      const sx = iRect.right - cRect.left;
      const sy = iRect.top - cRect.top + iRect.height / 2;
      const next: CurveEnd[] = [];
      outputRefs.current.forEach((o) => {
        if (!o) return;
        const oRect = o.getBoundingClientRect();
        const ex = oRect.left - cRect.left;
        const ey = oRect.top - cRect.top + oRect.height / 2;
        // Cubic bezier with horizontal tangents at both ends → smooth S-curve.
        const cp = Math.max(28, Math.abs(ex - sx) * 0.55);
        const d = `M ${sx.toFixed(2)} ${sy.toFixed(2)} C ${(sx + cp).toFixed(2)} ${sy.toFixed(2)}, ${(ex - cp).toFixed(2)} ${ey.toFixed(2)}, ${ex.toFixed(2)} ${ey.toFixed(2)}`;
        next.push({ sx, sy, ex, ey, d });
      });
      setCurves(next);
      setBox({ w: cRect.width, h: cRect.height });
    };

    measure();
    const ro = new ResizeObserver(measure);
    if (containerRef.current) ro.observe(containerRef.current);
    if (inputRef.current) ro.observe(inputRef.current);
    outputRefs.current.forEach((o) => o && ro.observe(o));
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <div ref={containerRef} className="absolute inset-0 p-5">
      {/* SVG covers the WHOLE card. viewBox in pixel units so curves land exactly on the boxes. */}
      {box.w > 0 && box.h > 0 && (
        <svg
          className="absolute inset-0 pointer-events-none"
          width={box.w}
          height={box.h}
          viewBox={`0 0 ${box.w} ${box.h}`}
          style={{ overflow: "visible" }}
        >
          {curves.map((c, i) => {
            const isActive = active === i;
            const tone = toneColor(i);
            const baseTone = "oklch(0.32 0.005 75)";
            return (
              <g key={i}>
                {/* Resting curve */}
                <path
                  d={c.d}
                  stroke={isActive ? tone : baseTone}
                  strokeWidth={isActive ? 1.6 : 1}
                  fill="none"
                  strokeLinecap="round"
                />
                {/* Animated dot riding the active curve */}
                {isActive && (
                  <circle r="3" fill={tone}>
                    <animateMotion dur="1.4s" repeatCount="indefinite" path={c.d} rotate="auto" />
                    <animate attributeName="opacity" values="0;1;1;0" dur="1.4s" repeatCount="indefinite" />
                  </circle>
                )}
                {/* End cap dots (touch the boxes) */}
                <circle cx={c.sx} cy={c.sy} r="1.6" fill={isActive ? tone : "oklch(0.45 0.005 75)"} />
                <circle cx={c.ex} cy={c.ey} r={isActive ? "2.4" : "1.6"} fill={isActive ? tone : "oklch(0.45 0.005 75)"} />
              </g>
            );
          })}
        </svg>
      )}

      <div
        className="relative h-full grid items-center hitl-grid"
        style={{ gap: 0 }}
      >
        <style>{`
          .hitl-grid { grid-template-columns: 78px 1fr 152px; }
          .hitl-btn  { grid-template-columns: 44px 1fr; }
          @media (min-width: 480px) {
            .hitl-grid { grid-template-columns: 104px 1fr 200px; }
            .hitl-btn  { grid-template-columns: 60px 1fr; }
          }
        `}</style>
        {/* Left: input node */}
        <div
          ref={inputRef}
          className="rounded-lg p-3 text-center relative z-10"
          style={{
            background: "oklch(0.135 0.006 75)",
            border: "1px solid oklch(0.30 0.005 75)",
          }}
        >
          <div className="eyebrow" style={{ color: "oklch(0.55 0.006 75)" }}>
            Refund
          </div>
          <div className="text-[12px] mt-0.5" style={{ color: "oklch(0.96 0.004 75)" }}>
            request
          </div>
          <div
            className="text-[9.5px] mt-1 tabular-nums"
            style={{ color: "oklch(0.45 0.006 75)" }}
          >
            47 / mo
          </div>
        </div>

        {/* Middle: empty - the SVG curves cross this space */}
        <div />

        {/* Right: 3 uniform branch rows */}
        <div className="relative z-10 flex flex-col gap-2">
          {branches.map((b, i) => {
            const isActive = active === i;
            const tone = toneColor(i);
            return (
              <button
                key={i}
                ref={(el) => { outputRefs.current[i] = el; }}
                onMouseEnter={() => setActive(i)}
                className="rounded-md text-left px-3 py-2.5 transition-all grid items-center hitl-btn"
                style={{
                  gap: 8,
                  background: isActive ? "oklch(0.135 0.006 75)" : "oklch(0.165 0.006 75)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: isActive
                    ? i === 0
                      ? "oklch(0.62 0.15 150 / 0.45)"
                      : i === 1
                        ? "oklch(0.78 0.13 75 / 0.45)"
                        : "oklch(0.40 0.005 75)"
                    : "oklch(0.22 0.005 75)",
                  height: 46,
                }}
              >
                <span
                  className="text-[11px] tabular-nums font-mono whitespace-nowrap"
                  style={{ color: "oklch(0.88 0.005 75)" }}
                >
                  {b.label}
                </span>
                <span className="flex items-baseline justify-end gap-2 whitespace-nowrap">
                  {/* Rate column hidden on tight mobile so the action label has room */}
                  <span
                    className="tabular-nums font-mono text-[10px] hidden sm:inline"
                    style={{ color: "oklch(0.55 0.006 75)" }}
                  >
                    {b.rate}
                  </span>
                  <span
                    className="text-[9px] uppercase"
                    style={{
                      color: isActive ? tone : "oklch(0.50 0.006 75)",
                      letterSpacing: "0.10em",
                      fontWeight: 600,
                    }}
                  >
                    {b.action}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ─── 3. BRIEFS: a real mini brief document ──────────────────────── */

function BriefVisual() {
  return (
    <div className="absolute inset-0 p-4">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.5, ease: [0.25, 1, 0.5, 1] }}
        className="rounded-lg h-full p-4 flex flex-col"
        style={{
          background: "oklch(0.135 0.006 75)",
          border: "1px solid oklch(0.22 0.005 75)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-baseline justify-between pb-3 border-b"
          style={{ borderColor: "oklch(0.22 0.005 75)" }}
        >
          <div>
            <div
              className="text-[9px] uppercase"
              style={{ color: "oklch(0.50 0.006 75)", letterSpacing: "0.14em", fontWeight: 600 }}
            >
              Case Brief · 4821
            </div>
            <div className="text-[12px] mt-0.5" style={{ color: "oklch(0.96 0.004 75)", fontWeight: 600 }}>
              TechCorp <span style={{ color: "oklch(0.70 0.006 75)", fontWeight: 400 }}>· chargeback</span>
            </div>
          </div>
          <span
            className="text-[9px] uppercase px-1.5 py-0.5 rounded"
            style={{
              color: "oklch(0.62 0.15 150)",
              letterSpacing: "0.10em",
              fontWeight: 600,
              background: "oklch(0.62 0.15 150 / 0.10)",
            }}
          >
            Awaiting
          </span>
        </div>

        {/* TL;DR */}
        <div
          className="text-[10.5px] leading-snug py-3"
          style={{ color: "oklch(0.75 0.005 75)" }}
        >
          $1,200 dispute, reason 4853. Customer healthy
          <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>[1]</span>
          ; first dispute in 14mo
          <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>[2]</span>
          .
        </div>

        {/* Actions */}
        <div
          className="space-y-1.5 py-3 border-t"
          style={{ borderColor: "oklch(0.22 0.005 75)" }}
        >
          {[
            ["01", "Refund $1,200"],
            ["02", "Apology email"],
            ["03", "CSM ticket"],
          ].map(([n, t], i) => (
            <motion.div
              key={n}
              initial={{ opacity: 0, x: -4 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.3 + i * 0.1, duration: 0.3 }}
              className="flex items-baseline gap-2 text-[10.5px]"
            >
              <span className="tabular-nums" style={{ color: "oklch(0.45 0.006 75)" }}>{n}</span>
              <span style={{ color: "oklch(0.85 0.005 75)" }}>{t}</span>
              <span
                className="ml-auto text-[9px] uppercase"
                style={{
                  color: "oklch(0.62 0.15 150)",
                  letterSpacing: "0.10em",
                  fontWeight: 600,
                }}
              >
                drafted
              </span>
            </motion.div>
          ))}
        </div>

        {/* Footnotes */}
        <div
          className="py-3 border-t text-[9.5px] space-y-0.5"
          style={{ borderColor: "oklch(0.22 0.005 75)", color: "oklch(0.50 0.006 75)" }}
        >
          <div className="flex items-baseline gap-2">
            <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>[1]</span>
            <span>Salesforce · health = good</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>[2]</span>
            <span>Stripe · 0 disputes in 14mo</span>
          </div>
        </div>

        {/* Signature - pinned bottom */}
        <div
          className="mt-auto pt-2 border-t flex items-baseline justify-between text-[9px]"
          style={{ borderColor: "oklch(0.22 0.005 75)", color: "oklch(0.45 0.006 75)" }}
        >
          <span style={{ fontFamily: "Geist Mono" }}>#M-4821-3f7c</span>
          <span style={{ color: "oklch(0.62 0.15 150)" }}>✓ signed by Manthan</span>
        </div>
      </motion.div>
    </div>
  );
}

/* ─── 4. POLICY: rule builder card with impact ────────────────────── */

function PolicyVisual() {
  const [enabled, setEnabled] = useState(true);
  const [amount, setAmount] = useState(150);
  const [ageOn, setAgeOn] = useState(true);

  const impact = enabled ? Math.round(amount / 7) + (ageOn ? 0 : 3) : 0;

  // Shared row styles for visual rhythm
  const rowBase: React.CSSProperties = {
    background: "oklch(0.135 0.006 75)",
    border: "1px solid oklch(0.22 0.005 75)",
    height: 52,
    paddingLeft: 14,
    paddingRight: 14,
  };

  return (
    <div className="absolute inset-0 p-4 flex flex-col gap-2">
      <div className="flex items-baseline justify-between mb-1">
        <div className="eyebrow">Refund policy</div>
        <span
          className="text-[9.5px] tabular-nums"
          style={{
            color: "oklch(0.50 0.006 75)",
            fontFamily: "Geist Mono",
            letterSpacing: "0.04em",
          }}
        >
          edited 4m ago
        </span>
      </div>

      {/* Row 1 - toggle */}
      <div className="rounded-md flex items-center justify-between" style={rowBase}>
        <span className="text-[11.5px]" style={{ color: "oklch(0.96 0.004 75)" }}>
          Auto-approve refunds
        </span>
        <button
          onClick={() => setEnabled(!enabled)}
          className="relative h-4 w-7 rounded-full transition-colors"
          style={{ background: enabled ? "oklch(0.62 0.15 150)" : "oklch(0.30 0.005 75)" }}
        >
          <span
            className="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all"
            style={{ left: enabled ? "calc(100% - 14px)" : "2px" }}
          />
        </button>
      </div>

      {/* Row 2 - slider (same height, inline layout) */}
      <div
        className="rounded-md grid items-center gap-3"
        style={{
          ...rowBase,
          opacity: enabled ? 1 : 0.45,
          gridTemplateColumns: "110px 1fr 52px",
        }}
      >
        <span className="text-[11.5px]" style={{ color: "oklch(0.96 0.004 75)" }}>
          Max amount
        </span>
        <input
          type="range"
          min={25}
          max={500}
          step={25}
          value={amount}
          disabled={!enabled}
          onChange={(e) => setAmount(parseInt(e.target.value))}
          className="range-themed"
          style={{
            ["--fill" as string]: `${((amount - 25) / (500 - 25)) * 100}%`,
          }}
        />
        <span
          className="tabular-nums text-right text-[11.5px]"
          style={{ color: "oklch(0.96 0.004 75)", fontWeight: 600 }}
        >
          ${amount}
        </span>
      </div>

      {/* Row 3 - checkbox */}
      <button
        onClick={() => setAgeOn(!ageOn)}
        disabled={!enabled}
        className="rounded-md flex items-center justify-between text-left disabled:opacity-45 w-full"
        style={rowBase}
      >
        <span className="text-[11.5px]" style={{ color: "oklch(0.96 0.004 75)" }}>
          Customer 90+ days old
        </span>
        <div
          className="h-4 w-4 rounded-sm inline-flex items-center justify-center shrink-0"
          style={{
            background: ageOn ? "oklch(0.62 0.15 150)" : "transparent",
            border: `1.5px solid ${ageOn ? "oklch(0.62 0.15 150)" : "oklch(0.30 0.005 75)"}`,
          }}
        >
          {ageOn && (
            <Check
              className="h-2.5 w-2.5"
              style={{ color: "oklch(0.18 0.05 150)" }}
              strokeWidth={3}
            />
          )}
        </div>
      </button>

      {/* Impact pinned bottom */}
      <div
        className="mt-auto rounded-md flex items-center justify-between"
        style={{
          ...rowBase,
          background: "oklch(0.62 0.15 150 / 0.08)",
          border: "1px solid oklch(0.62 0.15 150 / 0.22)",
          height: 44,
        }}
      >
        <span className="text-[10.5px]" style={{ color: "oklch(0.55 0.006 75)" }}>
          Impact · last 30d
        </span>
        <motion.span
          key={impact}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="text-[11.5px] tabular-nums"
          style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}
        >
          {impact} / 47 auto-approve
        </motion.span>
      </div>
    </div>
  );
}

/* ─── 5. COMPOUNDS: multi-metric dashboard with sparklines ───────── */

function CompoundVisual() {
  // ─── Data: 12 weekly observations (hours saved), smooth-ish rise with gentle ripple.
  // x is mapped into [4, 96] so the latest dot never clips against the box edges.
  const N_WEEKS = 12;
  const X_LEFT = 4;
  const X_RIGHT = 96;
  const Y_TOP = 8;     // headroom for the pulsing dot
  const Y_BOTTOM = 56; // bottom margin for axis labels
  const HOUR_MIN = 53;
  const HOUR_MAX = 184;

  const points = useMemo(() => {
    const pts: { x: number; y: number; week: number; hours: number }[] = [];
    for (let i = 0; i < N_WEEKS; i++) {
      const t = i / (N_WEEKS - 1);
      // gentle s-curve trend with a small low-frequency ripple
      const trend = 0.07 + 0.93 * (0.5 - 0.5 * Math.cos(Math.PI * t));
      const ripple = Math.sin(t * Math.PI * 1.9) * 0.04;
      const norm = Math.max(0, Math.min(1, trend + ripple));
      const x = X_LEFT + t * (X_RIGHT - X_LEFT);
      const y = Y_BOTTOM - norm * (Y_BOTTOM - Y_TOP);
      const hours = Math.round(HOUR_MIN + norm * (HOUR_MAX - HOUR_MIN));
      pts.push({ x, y, week: i + 1, hours });
    }
    return pts;
  }, []);

  // Catmull-Rom → cubic bezier for a buttery curve.
  const smoothPath = useMemo(() => {
    if (points.length < 2) return "";
    const tension = 0.5; // 0.5 ≈ classic Catmull-Rom; lower = smoother
    const segs: string[] = [`M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`];
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i - 1] ?? points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] ?? p2;
      const cp1x = p1.x + ((p2.x - p0.x) / 6) * tension * 2;
      const cp1y = p1.y + ((p2.y - p0.y) / 6) * tension * 2;
      const cp2x = p2.x - ((p3.x - p1.x) / 6) * tension * 2;
      const cp2y = p2.y - ((p3.y - p1.y) / 6) * tension * 2;
      segs.push(
        `C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`,
      );
    }
    return segs.join(" ");
  }, [points]);

  const last = points[points.length - 1];

  // ─── Hover interaction
  const [hovered, setHovered] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const onSvgMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width; // 0..1
    // Map clientX → viewBox X (0..100), then snap to nearest data point.
    const vbX = ratio * 100;
    let nearest = 0;
    let best = Infinity;
    for (let i = 0; i < points.length; i++) {
      const d = Math.abs(points[i].x - vbX);
      if (d < best) { best = d; nearest = i; }
    }
    setHovered(nearest);
  };

  const active = hovered !== null ? points[hovered] : last;
  const displayedHours = hovered !== null ? points[hovered].hours : 184;
  const displayedDelta = hovered !== null
    ? `${Math.round(((points[hovered].hours - HOUR_MIN) / HOUR_MIN) * 100)}%`
    : "+247%";
  const displayedLabel = hovered !== null ? `vs week 1` : `vs week 1`;
  const displayedWeek = hovered !== null ? `wk ${points[hovered].week}` : `wk 12`;

  return (
    <div className="absolute inset-0 p-6 flex flex-col">
      {/* Header - metric + delta */}
      <div className="flex items-baseline justify-between">
        <div>
          <div className="eyebrow">Hours saved · weekly</div>
          <div className="flex items-baseline gap-2 mt-1.5">
            <motion.span
              key={displayedHours}
              initial={{ opacity: 0.4, y: -2 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
              className="tabular-nums"
              style={{ color: "oklch(0.96 0.004 75)", fontWeight: 600, fontSize: 30, letterSpacing: "-0.02em", lineHeight: 1 }}
            >
              {displayedHours}
            </motion.span>
            <span
              className="font-mono tabular-nums text-[11px]"
              style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}
            >
              {hovered !== null ? `+${displayedDelta}` : displayedDelta}
            </span>
            <span className="text-[10px] ml-1" style={{ color: "oklch(0.48 0.006 75)" }}>
              {displayedLabel}
            </span>
          </div>
        </div>
        <div className="text-right text-[10px] leading-tight" style={{ color: "oklch(0.50 0.006 75)" }}>
          <div>{displayedWeek} of 12</div>
          <div className="mt-0.5 inline-flex items-center gap-1" style={{ color: "oklch(0.62 0.15 150)" }}>
            <span className="h-1 w-1 rounded-full animate-pulse-dot" style={{ background: "oklch(0.62 0.15 150)" }} />
            still climbing
          </div>
        </div>
      </div>

      {/* The wave - hoverable */}
      <div className="relative flex-1 mt-4">
        <svg
          ref={svgRef}
          className="absolute inset-0 w-full h-full cursor-crosshair"
          viewBox="0 0 100 60"
          preserveAspectRatio="none"
          onMouseMove={onSvgMove}
          onMouseLeave={() => setHovered(null)}
        >
          <defs>
            <linearGradient id="wave-fill" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%"   stopColor="oklch(0.62 0.15 150)" stopOpacity="0.34" />
              <stop offset="55%"  stopColor="oklch(0.62 0.15 150)" stopOpacity="0.08" />
              <stop offset="100%" stopColor="oklch(0.62 0.15 150)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="wave-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%"   stopColor="oklch(0.55 0.10 150)" />
              <stop offset="60%"  stopColor="oklch(0.62 0.15 150)" />
              <stop offset="100%" stopColor="oklch(0.72 0.15 150)" />
            </linearGradient>
          </defs>

          {/* Faint horizontal rules */}
          {[18, 32, 46].map((y) => (
            <line
              key={y}
              x1="0" x2="100" y1={y} y2={y}
              stroke="oklch(0.24 0.005 75)"
              strokeWidth="0.25"
              strokeDasharray="0.6 1.6"
            />
          ))}

          {/* Filled area under the wave */}
          <motion.path
            d={`${smoothPath} L ${X_RIGHT} ${Y_BOTTOM} L ${X_LEFT} ${Y_BOTTOM} Z`}
            fill="url(#wave-fill)"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.4 }}
          />

          {/* The wave stroke - opacity fade-in (pathLength animation leaves a dasharray
              artifact in framer-motion that visually cuts the line). */}
          <motion.path
            d={smoothPath}
            stroke="url(#wave-stroke)"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.45, ease: [0.25, 1, 0.5, 1] }}
            style={{ strokeDasharray: "none" }}
            vectorEffect="non-scaling-stroke"
          />

          {/* Hover guideline */}
          {hovered !== null && (
            <g>
              <line
                x1={active.x} x2={active.x} y1={Y_TOP - 4} y2={Y_BOTTOM}
                stroke="oklch(0.62 0.15 150 / 0.55)"
                strokeWidth="0.4"
                strokeDasharray="1 1.5"
              />
            </g>
          )}

          {/* Latest point - pulsing emerald dot. Always visible when no hover, snaps to hovered point when active. */}
          <circle cx={active.x} cy={active.y} r="2.4" fill="oklch(0.62 0.15 150)" opacity="0.22">
            <animate attributeName="r" values="2.4;3.8;2.4" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.22;0.05;0.22" dur="2s" repeatCount="indefinite" />
          </circle>
          <circle cx={active.x} cy={active.y} r="1.4" fill="oklch(0.96 0.004 75)" stroke="oklch(0.62 0.15 150)" strokeWidth="0.5" />
        </svg>

        {/* Tooltip - pinned to the hover point */}
        {hovered !== null && (
          <div
            className="pointer-events-none absolute -translate-x-1/2"
            style={{
              left: `${(active.x / 100) * 100}%`,
              top: `${((active.y - 14) / 60) * 100}%`,
            }}
          >
            <div
              className="rounded px-1.5 py-1 text-[9.5px] whitespace-nowrap leading-none"
              style={{
                background: "oklch(0.20 0.006 75)",
                border: "1px solid oklch(0.62 0.15 150 / 0.35)",
                color: "oklch(0.92 0.004 75)",
              }}
            >
              <span className="font-mono tabular-nums" style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>
                wk {active.week}
              </span>
              <span className="mx-1" style={{ color: "oklch(0.45 0.006 75)" }}>·</span>
              <span className="tabular-nums" style={{ fontWeight: 600 }}>{active.hours}h</span>
            </div>
          </div>
        )}
      </div>

      {/* Axis labels */}
      <div className="flex items-baseline justify-between text-[10px] mt-2" style={{ color: "oklch(0.45 0.006 75)" }}>
        <span>wk 1 · 53h</span>
        <span style={{ color: "oklch(0.62 0.15 150)", fontWeight: 600 }}>wk 12 · 184h</span>
      </div>
    </div>
  );
}

/* ─── 6. AUDIT: search + filter + live log ───────────────────────── */

function AuditVisual() {
  type Event = {
    who: "you" | "manthan";
    verb: string;
    object: string;
    detail: string;
    minsAgo: number;
  };

  const allEvents = useMemo<Event[]>(
    () => [
      { who: "manthan", verb: "posted the daily brief in",      object: "#billing-ops",         detail: "Slack",             minsAgo: 1 },
      { who: "you",     verb: "tightened the refund policy to", object: "max $100",             detail: "policy · refunds",  minsAgo: 3 },
      { who: "manthan", verb: "opened a follow-up ticket",      object: "BIL-128",              detail: "Linear",            minsAgo: 5 },
      { who: "manthan", verb: "emailed an apology to",          object: "TechCorp",             detail: "Gmail",             minsAgo: 5 },
      { who: "manthan", verb: "refunded",                       object: "$1,200 to TechCorp",   detail: "Stripe",            minsAgo: 6 },
      { who: "you",     verb: "approved",                       object: "CASE-4821 · TechCorp", detail: "case workspace",    minsAgo: 6 },
      { who: "manthan", verb: "refunded",                       object: "$840 to StartupY",     detail: "Stripe",            minsAgo: 14 },
      { who: "you",     verb: "approved",                       object: "CASE-4815 · StartupY", detail: "case workspace",    minsAgo: 14 },
    ],
    [],
  );

  const [filter, setFilter] = useState<"all" | "you" | "manthan">("all");
  const filtered = useMemo(
    () => (filter === "all" ? allEvents : allEvents.filter((e) => e.who === filter)),
    [filter, allEvents],
  );

  const [cursor, setCursor] = useState(0);
  useEffect(() => {
    const t = setInterval(() => {
      setCursor((c) => (c + 1) % Math.max(1, filtered.length));
    }, 2800);
    return () => clearInterval(t);
  }, [filtered.length]);

  const visible = useMemo(() => {
    const list = filtered.length > 0 ? filtered : allEvents;
    const out: { e: Event; key: number }[] = [];
    const WINDOW = 5;
    for (let i = 0; i < WINDOW; i++) {
      const idx = (cursor + i) % list.length;
      out.push({ e: list[idx], key: cursor * 100 + i });
    }
    return out;
  }, [cursor, filtered, allEvents]);

  const fmtAgo = (m: number) =>
    m < 1 ? "just now" : m === 1 ? "1 min ago" : m < 60 ? `${m} min ago` : `${Math.floor(m / 60)}h ago`;

  const filterCounts = useMemo(
    () => ({
      all: allEvents.length,
      you: allEvents.filter((e) => e.who === "you").length,
      manthan: allEvents.filter((e) => e.who === "manthan").length,
    }),
    [allEvents],
  );

  return (
    <div className="absolute inset-0 p-4 flex flex-col gap-2.5">
      {/* Header - filter pills + live badge */}
      <div className="flex items-baseline gap-2">
        <div className="eyebrow">Activity</div>
        <div className="flex items-center gap-0.5 ml-auto">
          {(["all", "you", "manthan"] as const).map((f) => {
            const isActive = filter === f;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className="text-[9.5px] uppercase px-1.5 py-0.5 rounded"
                style={{
                  color: isActive ? "oklch(0.62 0.15 150)" : "oklch(0.55 0.006 75)",
                  letterSpacing: "0.10em",
                  fontWeight: 600,
                  background: isActive ? "oklch(0.62 0.15 150 / 0.10)" : "transparent",
                }}
              >
                {f}
                <span
                  className="ml-1 tabular-nums"
                  style={{
                    color: isActive ? "oklch(0.62 0.15 150)" : "oklch(0.42 0.006 75)",
                    fontWeight: 500,
                  }}
                >
                  {filterCounts[f]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Activity feed */}
      <div
        className="flex-1 rounded-md p-3 overflow-hidden flex flex-col gap-2"
        style={{
          background: "oklch(0.135 0.006 75)",
          border: "1px solid oklch(0.22 0.005 75)",
        }}
      >
        <AnimatePresence initial={false} mode="popLayout">
          {visible.map((v, i) => {
            const isNewest = i === 0;
            const isYou = v.e.who === "you";
            const opacity = isNewest ? 1 : Math.max(0.36, 0.92 - i * 0.16);
            return (
              <motion.div
                key={v.key}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                transition={{ duration: 0.4, ease: [0.25, 1, 0.5, 1] }}
                className="flex items-start gap-2.5"
              >
                {/* Avatar dot */}
                <span
                  className="shrink-0 mt-[5px] inline-flex items-center justify-center rounded-full"
                  style={{
                    height: 8,
                    width: 8,
                    background: isYou ? "oklch(0.78 0.13 75)" : "oklch(0.62 0.15 150)",
                    boxShadow: isNewest
                      ? `0 0 0 3px ${isYou ? "oklch(0.78 0.13 75 / 0.18)" : "oklch(0.62 0.15 150 / 0.18)"}`
                      : "none",
                  }}
                />
                <div className="min-w-0 flex-1 leading-snug">
                  <div className="text-[11px]" style={{ color: "oklch(0.86 0.005 75)" }}>
                    <span style={{ color: "oklch(0.96 0.004 75)", fontWeight: 600 }}>
                      {isYou ? "You" : "Manthan"}
                    </span>{" "}
                    <span style={{ color: "oklch(0.70 0.006 75)" }}>{v.e.verb}</span>{" "}
                    <span
                      className={v.e.object.startsWith("$") || v.e.object.startsWith("CASE") || v.e.object.startsWith("BIL") ? "font-mono tabular-nums" : ""}
                      style={{ color: "oklch(0.96 0.004 75)", fontWeight: 500 }}
                    >
                      {v.e.object}
                    </span>
                    <span style={{ color: "oklch(0.50 0.006 75)" }}> · </span>
                    <span style={{ color: "oklch(0.50 0.006 75)" }}>{fmtAgo(v.e.minsAgo)}</span>
                  </div>
                  <div className="text-[10px] mt-0.5" style={{ color: "oklch(0.45 0.006 75)" }}>
                    via {v.e.detail}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div
        className="flex items-baseline justify-between text-[9.5px]"
        style={{ color: "oklch(0.48 0.006 75)" }}
      >
        <span>every action signed & exportable to your SIEM</span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1 w-1 rounded-full animate-pulse-dot" style={{ background: "oklch(0.62 0.15 150)" }} />
          live
        </span>
      </div>
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   PRICING - outcome-based (YC RFS · service-as-software model)
   No seats. No queries. Pay when Manthan closes a case for you.
   ═════════════════════════════════════════════════════════════════════ */

const VOLUME_BANDS = [
  { range: "First 50",    pricing: "free",       note: "every month" },
  { range: "51 – 500",    pricing: "$3 / case",  note: "pay-as-you-go" },
  { range: "501 – 5,000", pricing: "$2 / case",  note: "volume discount" },
  { range: "5,000+",      pricing: "let's talk", note: "annual contract" },
];

const CLOSED_OUTCOMES = [
  "Chargeback resolved",
  "Failed payment recovered",
  "Refund decided",
  "Invoice dispute settled",
  "Renewal saved",
];

function Pricing() {
  return (
    <section
      id="pricing"
      className="py-16 md:py-40 px-6"
      style={{
        background: "#000",
      }}
    >
      <div className="max-w-4xl mx-auto text-center">
        {/* Eyebrow */}
        {/* Headline */}
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5, ease: [0.25, 1, 0.5, 1], delay: 0.05 }}
          className="mt-5 text-4xl md:text-5xl tracking-[-0.03em] font-medium leading-[1.05]"
        >
          You only pay when Manthan does the{" "}
          <em className="font-serif italic font-normal">job right.</em>
        </motion.h2>

        {/* The price - solo, centered, dominant */}
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.96 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1], delay: 0.15 }}
          className="mt-14 mb-8 inline-flex items-baseline gap-3 justify-center"
        >
          <span
            className="tabular-nums"
            style={{
              fontSize: "clamp(5rem, 12vw, 11rem)",
              fontWeight: 500,
              letterSpacing: "-0.05em",
              color: "oklch(0.96 0.004 75)",
              lineHeight: 1,
            }}
          >
            $3
          </span>
          <span
            className="display-italic"
            style={{
              fontSize: "clamp(1.75rem, 3.5vw, 2.75rem)",
              color: "oklch(0.70 0.006 75)",
              lineHeight: 1,
            }}
          >
            / closed case
          </span>
        </motion.div>

        {/* One-line sub */}
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="text-[15px]"
          style={{ color: "oklch(0.65 0.006 75)" }}
        >
          First 50 every month are on us. False positives are free.
        </motion.p>

        {/* CTAs - auth-aware:
              Signed OUT → Sign up (primary green accent) routes to
                /signup, where Clerk captures the email + the
                user.created webhook fires the MVP welcome.
              Signed IN  → Open the live demo (same primary button)
                routes straight to /app. */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="mt-8 flex items-center justify-center gap-4 flex-wrap"
        >
          <Show when="signed-out">
            <Link to="/signup">
              <Button
                variant="accent"
                size="lg"
                rightIcon={<ArrowRight className="h-4 w-4" />}
              >
                Try now for free
              </Button>
            </Link>
            <Link
              to="/login"
              className="text-sm hover:opacity-90 transition-opacity"
              style={{ color: "rgba(255,255,255,0.65)" }}
            >
              Already have an account? Sign in
            </Link>
          </Show>
          <Show when="signed-in">
            <Link to="/app">
              <Button
                variant="accent"
                size="lg"
                rightIcon={<ArrowRight className="h-4 w-4" />}
              >
                Try now for free
              </Button>
            </Link>
          </Show>
        </motion.div>

        {/* Outcomes - single horizontal sentence */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.55, delay: 0.45 }}
          className="mt-20 text-[13px] leading-relaxed"
          style={{ color: "oklch(0.60 0.006 75)" }}
        >
          <span className="eyebrow mr-2.5">Closed =</span>
          {CLOSED_OUTCOMES.map((o, i) => (
            <span key={o}>
              <span style={{ color: "oklch(0.92 0.005 75)" }}>{o}</span>
              {i < CLOSED_OUTCOMES.length - 1 && (
                <span style={{ color: "oklch(0.30 0.005 75)" }}>{" · "}</span>
              )}
            </span>
          ))}
        </motion.div>

        {/* Volume bands - single horizontal pill */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.55, delay: 0.55 }}
          className="mt-6 inline-flex items-baseline gap-x-4 gap-y-2 flex-wrap justify-center px-6 py-3 rounded-full border"
          style={{
            background: "oklch(0.175 0.006 75)",
            borderColor: "rgba(255,255,255,0.08)",
          }}
        >
          {VOLUME_BANDS.map((b, i) => (
            <span
              key={b.range}
              className="text-[12px] inline-flex items-baseline gap-1.5"
            >
              <span style={{ color: "oklch(0.55 0.006 75)" }}>{b.range}</span>
              <span
                className="tabular-nums"
                style={{ color: "oklch(0.96 0.004 75)", fontWeight: 500 }}
              >
                {b.pricing}
              </span>
              {i < VOLUME_BANDS.length - 1 && (
                <span
                  style={{ color: "oklch(0.30 0.005 75)", marginLeft: 4 }}
                >
                  ·
                </span>
              )}
            </span>
          ))}
        </motion.div>

        {/* Enterprise - single quiet line */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5, delay: 0.7 }}
          className="mt-8 text-[13px]"
          style={{ color: "oklch(0.55 0.006 75)" }}
        >
          Need an annual contract, SSO, or custom integrations?{" "}
          <a
            href="/contact"
            className="inline-flex items-baseline gap-1 hover:opacity-80 transition-opacity"
            style={{ color: "oklch(0.62 0.15 150)", fontWeight: 500 }}
          >
            Talk to us
            <ArrowRight className="h-3 w-3 self-center" />
          </a>
        </motion.div>
      </div>
    </section>
  );
}

/* ═════════════════════════════════════════════════════════════════════
   FOOTER - Kresna-style two-card layout with watermark
   ═════════════════════════════════════════════════════════════════════ */

function Footer() {
  const watermarkSvgRef = useRef<SVGSVGElement | null>(null);
  const watermarkTextRef = useRef<SVGTextElement | null>(null);

  useEffect(() => {
    const fit = () => {
      const svg = watermarkSvgRef.current;
      const text = watermarkTextRef.current;
      if (!svg || !text) return;
      try {
        const bbox = text.getBBox();
        // bbox.height includes font descender room. "Manthan" has no descenders,
        // so crop the bottom ~22% to make the glyph hug the SVG bottom edge.
        const tightHeight = bbox.height * 0.78;
        svg.setAttribute(
          "viewBox",
          `${bbox.x} ${bbox.y} ${bbox.width} ${tightHeight}`,
        );
      } catch {
        // ignore - fonts not loaded yet
      }
    };
    if (document.fonts && (document as Document & { fonts: { ready: Promise<unknown> } }).fonts.ready) {
      (document as Document & { fonts: { ready: Promise<unknown> } }).fonts.ready.then(fit);
    } else {
      window.addEventListener("load", fit);
    }
    window.addEventListener("resize", fit);
    fit();
    return () => window.removeEventListener("resize", fit);
  }, []);

  const navLinks: { label: string; href: string }[] = [
    { label: "How it works", href: "#how" },
    { label: "Anatomy of a case", href: "#anatomy" },
    { label: "Pricing", href: "#pricing" },
    { label: "Blog", href: "/blog" },
    { label: "Changelog", href: "/changelog" },
  ];
  const companyLinks: { label: string; href: string }[] = [
    { label: "Contact", href: "/contact" },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
    { label: "DPA", href: "/dpa" },
  ];

  return (
    <footer className="px-6 pt-8 md:pt-20 pb-0">
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1] }}
        className="mx-auto grid items-stretch grid-cols-1 md:[grid-template-columns:minmax(0,350px)_minmax(0,1fr)]"
        style={{
          maxWidth: 1150,
          gap: 16,
        }}
      >
        {/* ── LEFT card - video background, logo, tagline, social ─────────── */}
        <motion.div
          initial={{ opacity: 0, y: 28, scale: 0.985 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1], delay: 0.05 }}
          className="relative overflow-hidden flex flex-col"
          style={{
            minHeight: 340,
            borderRadius: 28,
            padding: 32,
            background: "#0a0a0a",
            boxShadow: "0 12px 40px rgba(0, 0, 0, 0.5)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <video
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
            className="absolute inset-0 w-full h-full object-cover pointer-events-none"
            style={{ zIndex: 0, opacity: 0.85, objectPosition: "75% center" }}
          >
            <source src={FOOTER_VIDEO} type="video/mp4" />
          </video>
          {/* subtle dark vignette so foreground stays readable */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              zIndex: 0,
              background:
                "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.30) 40%, rgba(0,0,0,0.70) 100%)",
            }}
          />

          {/* Logo */}
          <div className="relative flex items-center gap-2.5" style={{ zIndex: 1 }}>
            <Logo size={28} showWordmark={false} className="text-white" />
            <span
              className="text-white"
              style={{
                fontFamily: "Geist, sans-serif",
                fontSize: 22,
                fontWeight: 700,
                letterSpacing: "-0.02em",
              }}
            >
              Manthan
            </span>
          </div>

          {/* Tagline */}
          <div
            className="relative mt-auto"
            style={{ zIndex: 1, marginBottom: 28 }}
          >
            <p
              className="text-white"
              style={{
                fontSize: 19,
                fontWeight: 400,
                lineHeight: 1.45,
                fontFamily: "Geist, sans-serif",
              }}
            >
              Dispute &amp; refund ops for B2B SaaS,
              <br />
              <span
                className="display-italic"
                style={{ color: "rgba(255,255,255,0.65)", fontSize: 22 }}
              >
                calm and accountable.
              </span>
            </p>
          </div>

          {/* Social row */}
          <div
            className="relative flex items-center justify-between"
            style={{ zIndex: 1, gap: 12 }}
          >
            <span
              className="display-italic"
              style={{
                fontSize: 17,
                color: "rgba(255,255,255,0.9)",
                letterSpacing: "0.3px",
              }}
            >
              Stay in touch.
            </span>
            <div className="flex items-center" style={{ gap: 7 }}>
              {[
                {
                  name: "X",
                  href: "https://x.com/hitakshi_exe",
                  path: "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z",
                },
                {
                  name: "LinkedIn",
                  href: "https://www.linkedin.com/in/hitakshiaroraa/",
                  path: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.063 2.063 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
                },
                {
                  name: "GitHub",
                  href: "https://github.com/hitakshiA",
                  path: "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
                },
              ].map((s) => (
                <a
                  key={s.name}
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={s.name}
                  className="inline-flex items-center justify-center transition-all"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 9,
                    background: "#0e1014",
                    boxShadow:
                      "0 6px 18px rgba(0,0,0,0.35), 0 2px 6px rgba(0,0,0,0.2)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "#000";
                    e.currentTarget.style.transform = "translateY(-2px)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "#0e1014";
                    e.currentTarget.style.transform = "translateY(0)";
                  }}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width={15}
                    height={15}
                    fill="#fff"
                    aria-hidden
                  >
                    <path d={s.path} />
                  </svg>
                </a>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ── RIGHT card - nav, floating badge, subscribe.
            Hidden on mobile (keep only the left video card on small screens). */}
        <motion.div
          initial={{ opacity: 0, y: 28, scale: 0.985 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1], delay: 0.15 }}
          className="relative hidden md:flex flex-col justify-between"
          style={{
            background: "#0f0f11",
            borderRadius: 28,
            padding: 40,
            border: "1px solid rgba(255,255,255,0.06)",
            boxShadow: "0 4px 20px rgba(0,0,0,0.30)",
          }}
        >
          {/* Floating "Sign up · try the demo" badge - clickable, routes
              to /signup so every demo visitor lands as a known Clerk
              user. The green-gradient tile carries a Play glyph instead
              of the old "M" letter so the affordance reads as obvious
              one-tap action. */}
          <Link
            to="/signup"
            className="absolute flex flex-col items-start group cursor-pointer"
            style={{
              top: -36,
              right: 40,
              gap: 6,
              zIndex: 10,
              textDecoration: "none",
            }}
            aria-label="Sign up and try the demo"
          >
            <div
              className="flex items-center justify-center transition-transform"
              style={{
                width: 96,
                height: 96,
                borderRadius: 22,
                transform: "rotate(-10deg)",
                background:
                  "linear-gradient(135deg, oklch(0.78 0.15 150) 0%, oklch(0.55 0.16 150) 55%, oklch(0.38 0.14 150) 100%)",
                boxShadow:
                  "inset 3px 3px 8px rgba(255,255,255,0.20), inset -3px -3px 12px rgba(0,0,0,0.30), 8px 14px 28px rgba(40, 160, 100, 0.30)",
              }}
            >
              <Play
                size={40}
                strokeWidth={0}
                fill="#fff"
                style={{
                  transform: "rotate(10deg) translateX(3px)",
                  filter: "drop-shadow(0 3px 6px rgba(0,0,0,0.35))",
                }}
              />
            </div>
            <div
              className="flex items-center"
              style={{
                gap: 6,
                transform: "rotate(-4deg)",
                marginTop: 4,
              }}
            >
              <svg
                viewBox="0 0 24 24"
                width={22}
                height={22}
                xmlns="http://www.w3.org/2000/svg"
                style={{ color: "rgba(255,255,255,0.45)" }}
              >
                <path
                  d="M3 20 C 6 14, 10 9, 18 5"
                  stroke="currentColor"
                  fill="none"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M18 5 L 12 5"
                  stroke="currentColor"
                  fill="none"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M18 5 L 18 11"
                  stroke="currentColor"
                  fill="none"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span
                className="display-italic"
                style={{
                  fontSize: 20,
                  color: "rgba(255,255,255,0.55)",
                  whiteSpace: "nowrap",
                }}
              >
                Try now for free
              </span>
            </div>
          </Link>

          {/* Nav columns */}
          <div className="flex" style={{ gap: 72, paddingTop: 8 }}>
            <FooterCol title="Navigation" links={navLinks} />
            <FooterCol title="Company" links={companyLinks} />
          </div>

          {/* Bottom row - copyright + subscribe */}
          <div
            className="flex items-end justify-between flex-wrap gap-6"
            style={{ marginTop: 48 }}
          >
            <span
              style={{
                fontFamily: "Geist, sans-serif",
                fontSize: 12.5,
                fontWeight: 500,
                color: "rgba(255,255,255,0.40)",
              }}
            >
              © {new Date().getFullYear()} Manthan. All rights reserved.
            </span>

            <div className="flex flex-col" style={{ gap: 14 }}>
              <h4
                style={{
                  fontFamily: "Geist, sans-serif",
                  fontSize: 15,
                  fontWeight: 400,
                  color: "rgba(255,255,255,0.55)",
                  lineHeight: 1.45,
                }}
              >
                Notes from the queue.
                <br />
                <strong
                  style={{
                    display: "block",
                    fontSize: 19,
                    fontWeight: 700,
                    color: "#fff",
                  }}
                >
                  Once a month, no fluff.
                </strong>
              </h4>

              <div
                className="flex items-stretch"
                style={{
                  width: 310,
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.10)",
                  borderRadius: 12,
                  padding: 5,
                  boxShadow: "0 2px 10px rgba(0,0,0,0.20)",
                }}
              >
                <input
                  type="email"
                  placeholder="Enter your work email"
                  className="flex-1 bg-transparent outline-none"
                  style={{
                    padding: "11px 14px",
                    fontFamily: "Geist, sans-serif",
                    fontSize: 13.5,
                    color: "#fff",
                  }}
                />
                <button
                  type="button"
                  className="transition-all"
                  style={{
                    padding: "11px 22px",
                    background: "oklch(0.62 0.15 150)",
                    color: "oklch(0.18 0.05 150)",
                    fontFamily: "Geist, sans-serif",
                    fontSize: 13.5,
                    fontWeight: 600,
                    borderRadius: 8,
                    boxShadow:
                      "0 6px 20px rgba(40, 160, 100, 0.30), 0 2px 8px rgba(0,0,0,0.25)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "oklch(0.66 0.15 150)";
                    e.currentTarget.style.transform = "translateY(-1px)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "oklch(0.62 0.15 150)";
                    e.currentTarget.style.transform = "translateY(0)";
                  }}
                >
                  Subscribe
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>

      {/* Giant faded "Manthan" watermark - desktop only. Mobile keeps just the left card. */}
      <motion.div
        aria-hidden
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ duration: 0.9, ease: [0.25, 1, 0.5, 1], delay: 0.3 }}
        className="mx-auto pointer-events-none select-none relative hidden md:block"
        style={{
          maxWidth: 1150,
          marginTop: -60,
          zIndex: 0,
          lineHeight: 0,
        }}
      >
        <svg
          ref={watermarkSvgRef}
          viewBox="62 95 876 175"
          preserveAspectRatio="xMidYMid meet"
          xmlns="http://www.w3.org/2000/svg"
          style={{ display: "block", width: "100%", height: "auto", overflow: "visible" }}
        >
          <text
            ref={watermarkTextRef}
            x={500}
            y={240}
            textAnchor="middle"
            fontSize={320}
            style={{
              fontFamily: "Geist, sans-serif",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              fill: "rgba(255,255,255,0.04)",
            }}
          >
            Manthan
          </text>
        </svg>
      </motion.div>
    </footer>
  );
}

/**
 * HeroDemoCTA - the iridescent hero button.
 *
 * Always routes to /signup. Marketing page treats every visitor the
 * same - signed-in users navigate to their workspace from the app
 * sidebar, not from the marketing CTA.
 */
function HeroDemoCTA() {
  return (
    <HeroCTAButton>
      <Link to="/signup" className="inline-flex items-center gap-2">
        Try Now
        <ArrowRight className="h-4 w-4" />
      </Link>
    </HeroCTAButton>
  );
}

/** Shared iridescent pill - same look, two trigger modes. */
function HeroCTAButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.button
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      disabled={disabled}
      className="rounded-full px-8 py-3.5 text-base font-medium inline-flex items-center gap-2 disabled:opacity-90"
      style={{
        background:
          "linear-gradient(95deg, #f5c0d5 0%, #d8c0e8 30%, #b8d8ee 65%, #c8e8d5 100%)",
        color: "#000",
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.5), 0 8px 24px rgba(200, 180, 255, 0.18)",
      }}
    >
      {children}
    </motion.button>
  );
}

function FooterCol({
  title,
  links,
}: {
  title: string;
  links: { label: string; href: string }[];
}) {
  return (
    <div>
      <div
        className="display-italic"
        style={{
          fontSize: 24,
          color: "rgba(255,255,255,0.40)",
          marginBottom: 18,
        }}
      >
        {title}
      </div>
      <ul style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {links.map((l) => {
          const isAnchor = l.href.startsWith("#");
          const isExternal = l.href.startsWith("http");
          const style: React.CSSProperties = {
            fontFamily: "Geist, sans-serif",
            fontSize: 14,
            fontWeight: 600,
            color: "rgba(255,255,255,0.92)",
            textDecoration: "none",
          };
          const onEnter = (e: React.MouseEvent<HTMLElement>) => {
            (e.currentTarget as HTMLElement).style.color = "oklch(0.66 0.15 150)";
          };
          const onLeave = (e: React.MouseEvent<HTMLElement>) => {
            (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.92)";
          };
          return (
            <li key={l.label} style={{ marginBottom: 14 }}>
              {isAnchor || isExternal ? (
                <a
                  href={l.href}
                  className="block transition-colors"
                  style={style}
                  onMouseEnter={onEnter}
                  onMouseLeave={onLeave}
                  {...(isExternal ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                >
                  {l.label}
                </a>
              ) : (
                <Link
                  to={l.href}
                  className="block transition-colors"
                  style={style}
                  onMouseEnter={onEnter}
                  onMouseLeave={onLeave}
                >
                  {l.label}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
