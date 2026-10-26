/**
 * Auth shell - verbatim port of the Aurora Onboard prompt.
 *
 *   main: flex min-h-screen w-full bg-black selection:bg-white/30 p-2
 *         transition-all duration-500. lg: h-screen overflow-hidden p-4
 *   left: w-[52%] hidden lg:flex, relative flex-col items-center
 *         justify-end pb-32 px-12 rounded-3xl overflow-hidden shadow-2xl
 *   video bg: exact CDN URL from prompt, no overlay tint
 *   hero content: z-10 max-w-xs space-y-8, staggered motion reveal
 *   brand: Circle (filled white) + workspace name
 *   StepItem: active = bg-white text-black border; inactive =
 *     bg-brand-gray (#1A1A1A) border-none
 */

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Logo } from "@/components/Logo";

const AURORA_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260506_081238_406ed0e3-5d83-436e-a512-0bbff7ec5b95.mp4";

interface Step {
  label: string;
}

interface AuthShellProps {
  /** kept for backwards compat with callers; no longer rendered */
  heading?: string;
  description?: string;
  steps?: Step[];
  activeStep?: number;
  children: ReactNode;
}

export function AuthShell({ children }: AuthShellProps) {
  return (
    <main className="flex min-h-screen w-full bg-black selection:bg-white/30 text-white p-2 transition-all duration-500 lg:h-screen lg:overflow-hidden lg:p-4">
      {/* LEFT - green-shifted video with the Manthan mark centered on top. */}
      <aside className="hidden lg:flex w-[52%] relative rounded-3xl overflow-hidden shadow-2xl h-full items-center justify-center">
        <video
          src={AURORA_VIDEO}
          autoPlay
          muted
          loop
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
          style={{
            filter: "hue-rotate(220deg) saturate(0.85) brightness(0.95)",
          }}
        />
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, ease: [0.25, 1, 0.5, 1], delay: 0.15 }}
          className="relative text-white"
          style={{
            filter: "drop-shadow(0 0 32px rgba(22, 208, 94, 0.45))",
          }}
        >
          <Logo size={140} showWordmark={false} />
        </motion.div>
      </aside>

      {/* RIGHT */}
      <section className="flex-1 flex flex-col items-center justify-center py-12 lg:py-6 px-4 sm:px-12 lg:px-16 xl:px-24 overflow-y-auto lg:overflow-hidden">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="w-full max-w-xl space-y-8 lg:space-y-6 sm:space-y-10"
        >
          {children}
        </motion.div>
      </section>
    </main>
  );
}

