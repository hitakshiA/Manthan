/**
 * OriginalEmailModal - for email-triggered cases.
 *
 * The sketch annotation: "The Case Description should link to the
 * email it got and maybe can create new UI here ... [box with smaller
 * box labelled] email verbatim".
 *
 * Opens when the operator clicks "Original email" in the Brief header.
 * Shows the raw inbound message: from / subject / received-at / body.
 * If the inbound email had HTML, we sandbox it in an iframe so styling
 * doesn't bleed into the workspace; falls back to the plain-text body
 * when only that's available.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Mail, X } from "lucide-react";

import { fetchTriggerEmail, type TriggerEmail } from "@/lib/api";

export interface OriginalEmailModalProps {
  caseId: string | null;
  open: boolean;
  onClose: () => void;
}

export function OriginalEmailModal({
  caseId,
  open,
  onClose,
}: OriginalEmailModalProps) {
  const [email, setEmail] = useState<TriggerEmail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !caseId) return;
    let cancelled = false;
    setEmail(null);
    setError(null);
    setLoading(true);
    fetchTriggerEmail(caseId)
      .then((r) => {
        if (cancelled) return;
        setEmail(r);
      })
      .catch((e) => {
        if (cancelled) return;
        setError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, caseId]);

  // Esc closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[60] flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.55)" }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="w-full max-w-[640px] overflow-hidden flex flex-col"
            style={{
              maxHeight: "85vh",
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-md)",
              boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex items-start gap-3 px-5 pt-4 pb-3 border-b shrink-0"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <div
                className="flex items-center justify-center shrink-0"
                style={{
                  width: 32,
                  height: 32,
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-rule-soft)",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <Mail size={15} style={{ color: "var(--color-ink-muted)" }} />
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className="eyebrow"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  Original email
                </div>
                <div
                  className="text-[14px] mt-0.5 truncate"
                  style={{ color: "var(--color-ink-strong)" }}
                >
                  {email?.subject || (loading ? "Loading…" : "(no subject)")}
                </div>
                {email && (
                  <div
                    className="text-[11px] mt-0.5 truncate"
                    style={{ color: "var(--color-ink-faint)" }}
                  >
                    {email.from_name
                      ? `${email.from_name} <${email.from_addr}>`
                      : email.from_addr}
                    {email.received_at && (
                      <span style={{ color: "var(--color-ink-ghost)" }}>
                        {" · "}
                        {formatReceived(email.received_at)}
                      </span>
                    )}
                  </div>
                )}
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="shrink-0 -mt-1 -mr-1 p-1 rounded hover:bg-[color:var(--color-surface)]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                <X size={14} />
              </button>
            </div>

            <div className="px-5 py-4 overflow-auto" style={{ flex: 1 }}>
              {loading && <Skeleton />}
              {!loading && error && (
                <p
                  className="text-[12.5px]"
                  style={{ color: "var(--color-danger)" }}
                >
                  Couldn&apos;t load the email: {error}
                </p>
              )}
              {!loading && !error && !email && (
                <p
                  className="text-[12.5px] italic"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  No original email - this case wasn&apos;t opened from
                  email.
                </p>
              )}
              {!loading && !error && email && (
                <EmailBody email={email} />
              )}
            </div>

            <div
              className="px-5 py-3 border-t flex items-center justify-between gap-3 shrink-0"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <span
                className="text-[10.5px]"
                style={{
                  color: "var(--color-ink-ghost)",
                  letterSpacing: "0.04em",
                }}
              >
                Replies to this address attach to the same case automatically
              </span>
              {email && (
                <a
                  href={`mailto:${email.from_addr}`}
                  className="text-[12px] tabular-nums hover:opacity-90"
                  style={{ color: "var(--color-accent)" }}
                >
                  {email.from_addr}
                </a>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Pick whichever body the email has. We sandbox HTML in an iframe so
 *  the email's CSS / scripts can't leak into the workspace. */
function EmailBody({ email }: { email: TriggerEmail }) {
  if (email.html && email.html.trim().length > 0) {
    return (
      <iframe
        title="Original email body"
        srcDoc={email.html}
        sandbox=""
        style={{
          width: "100%",
          minHeight: "360px",
          maxHeight: "60vh",
          background: "white",
          border: "1px solid var(--color-rule-soft)",
          borderRadius: "var(--radius-sm)",
        }}
      />
    );
  }
  if (email.text && email.text.trim().length > 0) {
    return (
      <pre
        className="font-display text-[14px] leading-[1.6] whitespace-pre-wrap"
        style={{
          color: "var(--color-ink-strong)",
          fontFamily: "inherit",
        }}
      >
        {email.text}
      </pre>
    );
  }
  return (
    <p
      className="text-[12.5px] italic"
      style={{ color: "var(--color-ink-faint)" }}
    >
      The email had no body content (rare, but possible).
    </p>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2" aria-label="loading email">
      <div
        className="h-3 rounded animate-pulse"
        style={{ background: "var(--color-rule-soft)", width: "85%" }}
      />
      <div
        className="h-3 rounded animate-pulse"
        style={{ background: "var(--color-rule-soft)", width: "72%" }}
      />
      <div
        className="h-3 rounded animate-pulse"
        style={{ background: "var(--color-rule-soft)", width: "60%" }}
      />
    </div>
  );
}

function formatReceived(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
