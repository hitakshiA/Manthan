/**
 * DemoTriggerMenu - TopBar widget for firing pre-baked demo scenarios.
 *
 * Editorial form: a single italic "Demo" link in the top bar that drops
 * a quiet menu of scenarios on click. No amber pill, no zap icon - the
 * dropdown does the speaking, the trigger is a typographic affordance.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import {
  listDemoScenarios,
  resetDemoState,
  triggerDemoScenario,
  type DemoScenario,
} from "@/lib/api";

export function DemoTriggerMenu() {
  const [open, setOpen] = useState(false);
  const [scenarios, setScenarios] = useState<DemoScenario[] | null>(null);
  const [firingId, setFiringId] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open || scenarios !== null) return;
    listDemoScenarios()
      .then((r) => setScenarios(r.scenarios))
      .catch(() => setScenarios([]));
  }, [open, scenarios]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Endpoint is dev-only; hide the affordance entirely in prod.
  if (scenarios !== null && scenarios.length === 0) return null;

  const fire = async (id: string) => {
    setFiringId(id);
    try {
      const r = await triggerDemoScenario(id);
      setOpen(false);
      navigate(`/app/case/${r.case_id}`);
    } catch {
      // ignore
    } finally {
      setFiringId(null);
    }
  };

  const reset = async () => {
    if (!confirm("Wipe all cases / events / actions / policy matches for this tenant?")) return;
    setResetting(true);
    try {
      await resetDemoState();
      setOpen(false);
      navigate("/app", { replace: true });
      location.reload();
    } catch {
      // ignore
    } finally {
      setResetting(false);
    }
  };

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="font-display italic text-[14px] tracking-[0.005em] hover:opacity-90 transition-opacity"
        style={{
          color: open ? "var(--color-ink-strong)" : "var(--color-ink-muted)",
        }}
        title="Fire a pre-baked demo scenario"
      >
        Demo<span style={{ color: "var(--color-ink-ghost)" }}>&nbsp;↘</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -2 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-80 z-50 border"
            style={{
              background: "var(--color-surface-2)",
              borderColor: "var(--color-rule)",
              borderRadius: "var(--radius-md)",
              boxShadow: "0 16px 40px rgba(0,0,0,0.65)",
            }}
          >
            <div
              className="px-3 py-2 border-b"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <div
                className="eyebrow"
                style={{ color: "var(--color-ink-faint)" }}
              >
                Fire a scenario
              </div>
            </div>

            <ul className="divide-y" style={{ borderColor: "var(--color-rule-soft)" }}>
              {scenarios === null && (
                <li
                  className="px-3 py-2.5 text-[12px]"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  Loading
                  <span className="animate-pulse-dot">…</span>
                </li>
              )}
              {scenarios?.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => fire(s.id)}
                    disabled={firingId !== null}
                    className="w-full text-left px-3 py-2.5 hover:bg-[var(--color-surface)] transition-colors disabled:opacity-50"
                  >
                    <div
                      className="text-[12.5px]"
                      style={{ color: "var(--color-ink-strong)" }}
                    >
                      {s.label}
                    </div>
                    <div
                      className="mt-0.5 text-[10.5px] uppercase tracking-[0.12em] flex items-baseline gap-2"
                      style={{ color: "var(--color-ink-faint)" }}
                    >
                      <span>{s.surface}</span>
                      {firingId === s.id && (
                        <span style={{ color: "var(--color-accent)" }}>
                          firing<span className="animate-pulse-dot">…</span>
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>

            <div
              className="px-3 py-2 border-t"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <button
                onClick={reset}
                disabled={resetting}
                className="text-[11px] tracking-[0.04em] hover:opacity-90 disabled:opacity-50"
                style={{ color: "var(--color-ink-faint)" }}
              >
                {resetting ? "Resetting…" : "Reset demo state"}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
