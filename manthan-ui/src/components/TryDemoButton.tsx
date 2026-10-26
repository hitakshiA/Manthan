/**
 * TryDemoButton - public "Try the live demo" CTA.
 *
 * Used on Landing / Login / Signup so a fresh viewer can land on a
 * running case in one click. Fires a pre-baked scenario (default: Quill,
 * the centerpiece) via /api/demo/trigger/{id}, then navigates straight
 * to the new case so the investigation streams in front of them.
 *
 * If the demo endpoint is disabled (404, e.g. prod), falls back to a
 * plain navigate to /app so the button never just breaks.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { triggerDemoScenario } from "@/lib/api";

interface TryDemoButtonProps {
  /** Which pre-baked scenario to fire. Defaults to the Quill chargeback. */
  scenarioId?: "quill" | "vermillion" | "maya";
  /** Visual variant. */
  variant?: "primary" | "secondary" | "subtle";
  /** Custom label override. */
  label?: string;
  /** Optional extra Tailwind classes. */
  className?: string;
}

export function TryDemoButton({
  scenarioId = "quill",
  variant = "primary",
  label = "Try the live demo",
  className = "",
}: TryDemoButtonProps) {
  const navigate = useNavigate();
  const [firing, setFiring] = useState(false);

  const onClick = async () => {
    setFiring(true);
    try {
      const r = await triggerDemoScenario(scenarioId);
      navigate(`/app/case/${r.case_id}`);
    } catch {
      // Demo endpoint disabled or unreachable - just route to /app.
      navigate("/app");
    } finally {
      setFiring(false);
    }
  };

  const base =
    "inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all active:scale-[0.98] disabled:opacity-50";
  const variants: Record<string, string> = {
    primary: "h-14 px-6 bg-white text-black hover:bg-white/90 text-[15px]",
    secondary:
      "h-12 px-5 bg-white/[0.06] text-white border border-white/15 hover:bg-white/[0.10] text-[14px]",
    subtle:
      "h-10 px-4 text-white/70 hover:text-white text-[13px] underline-offset-4 hover:underline",
  };

  return (
    <button
      onClick={onClick}
      disabled={firing}
      className={`${base} ${variants[variant]} ${className}`}
    >
      {firing ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Spinning up your case…</span>
        </>
      ) : (
        <>
          <span>{label}</span>
          <ArrowRight className="h-4 w-4" />
        </>
      )}
    </button>
  );
}
