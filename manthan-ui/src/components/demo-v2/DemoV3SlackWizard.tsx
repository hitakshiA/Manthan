// DemoV3SlackWizard - center-modal guided tour for the
// Slack-mention flow. Sibling of DemoV2Wizard. Walks the user
// through: join the ManthanDemo workspace -> @-mention @manthantest
// in #all-manthandemo with a copy-button-prefilled message -> watch
// the case auto-resolve.
//
// Identity bridge: the mention's slack_user_id is resolved to email
// server-side (slack_bot.users.info) and matched to a Manthan member
// row, which routes the new case into the operator's personal org.

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { call as apiCall } from "@/lib/api";
import {
  CANCELLABLE_STEPS,
  NAV_LOCKED_STEPS,
  POLL_INTERVAL_MS,
  POLL_TIMEOUT_MS,
  STEP_ORDER,
  VERIFY_POLL_INTERVAL_MS,
  checkSlackInbound,
  checkSlackMember,
  clearState,
  fetchTemplate,
  freshState,
  loadState,
  saveState,
  type DemoV3State,
  type DemoV3Template,
  type StepId,
} from "@/lib/demo-v3";

interface DemoV3WizardProps {
  loggedInEmail: string;
  onClose: () => void;
}

export function DemoV3SlackWizard({ loggedInEmail, onClose }: DemoV3WizardProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const [state, setState] = useState<DemoV3State>(
    () => loadState() ?? freshState(loggedInEmail),
  );
  const [template, setTemplate] = useState<DemoV3Template | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => saveState(state), [state]);

  useEffect(() => {
    let cancelled = false;
    fetchTemplate()
      .then((t) => !cancelled && setTemplate(t))
      .catch((e) => !cancelled && setErrorMsg(`Couldn't load demo template: ${String(e)}`));
    return () => {
      cancelled = true;
    };
  }, []);

  const cancellable = CANCELLABLE_STEPS.has(state.step);
  const setStep = useCallback((step: StepId) => {
    setState((p) => ({ ...p, step }));
  }, []);

  const handleCancel = useCallback(() => {
    clearState();
    onClose();
    navigate("/app");
  }, [navigate, onClose]);

  // ── verify-join: poll users.lookupByEmail until the user is in ───
  useEffect(() => {
    if (state.step !== "verify-join") return;
    let aborted = false;
    const tick = async () => {
      if (aborted || !state.loggedInEmail) return;
      try {
        const r = await checkSlackMember(state.loggedInEmail);
        if (aborted) return;
        if (r.member) {
          setState((p) => ({
            ...p,
            step: "send-mention",
            slackDisplayName: r.slack_display_name,
            // Start the wait window NOW so that any mention the user
            // posts during the send-mention step still falls inside
            // the time filter when they click "I've sent it" - even if
            // they post in Slack before clicking. Was being set only
            // after the click, which excluded already-posted cases.
            waitingStartedAt: Date.now(),
          }));
        }
      } catch {
        /* transient */
      }
    };
    void tick();
    const id = window.setInterval(tick, VERIFY_POLL_INTERVAL_MS);
    return () => {
      aborted = true;
      window.clearInterval(id);
    };
  }, [state.step, state.loggedInEmail]);

  // ── waiting-for-mention step removed. The user explicitly didn't want
  //   a polling-progress-bar between "I've sent the mention" and the
  //   case workspace - the in-Slack bot reply already has a "Watch
  //   live in Manthan" deep-link button, and the inbox surfaces the
  //   case via SSE the moment it lands. The onSentMention handler now
  //   does a short inline one-shot lookup (~4s) and either advances
  //   directly to case-opened or drops the user on /app to wait.

  // ── case-opened: navigate to /app/case/{id}, watch for resolved ──
  useEffect(() => {
    if (state.step !== "case-opened" || !state.caseId) return;
    const target = `/app/case/${state.caseId}`;
    if (!location.pathname.startsWith(target)) navigate(target);
  }, [state.step, state.caseId, location.pathname, navigate]);

  useEffect(() => {
    if (state.step !== "case-opened") return;
    if (!state.loggedInEmail || !state.waitingStartedAt) return;
    let aborted = false;
    const tick = async () => {
      if (aborted) return;
      try {
        const r = await checkSlackInbound(state.loggedInEmail!, state.waitingStartedAt!);
        if (aborted) return;
        if (r.matched && (r.status === "resolved" || r.status === "errored")) {
          setState((p) => ({ ...p, step: "case-resolved" }));
        }
      } catch {
        /* transient */
      }
    };
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      aborted = true;
      window.clearInterval(id);
    };
  }, [state.step, state.loggedInEmail, state.waitingStartedAt]);

  // ── 404 watchdog: clear stale state if the tracked case is gone ──
  useEffect(() => {
    if (state.step !== "case-opened" && state.step !== "case-resolved") return;
    if (!state.caseId) return;
    let cancelled = false;
    apiCall(`/api/cases/${state.caseId}`).catch((e: Error) => {
      if (cancelled) return;
      if (String(e).includes("404")) {
        clearState();
        onClose();
        navigate("/app");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [state.step, state.caseId, navigate, onClose]);

  // ── nav lock on the active phases ────────────────────────────────
  useEffect(() => {
    if (!NAV_LOCKED_STEPS.has(state.step)) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "The agent is mid-investigation. Leave anyway?";
      return e.returnValue;
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [state.step]);

  const progressIdx = STEP_ORDER.indexOf(state.step);
  const progressTotal = STEP_ORDER.length - 1;

  // case-opened is a side-of-screen floating tip (don't block the
  // workspace) - everything else is a full center modal.
  if (state.step === "case-opened") {
    return (
      <FloatingTip>
        <Eyebrow>Step {progressIdx + 1} of {progressTotal}</Eyebrow>
        <H3 style={{ marginTop: 4 }}>Watching the agent</H3>
        <P style={{ fontSize: 13 }}>
          The case is running with the policy attached. We'll surface the
          resolution as soon as the brief lands.
        </P>
        <P style={{ color: "rgba(239,236,228,0.55)", fontSize: 12 }}>
          Case {state.shortId ?? ""} · usually 30-90 seconds.
        </P>
        <ExitLink onClick={handleCancel} cancellable={cancellable} />
      </FloatingTip>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Manthan Slack demo"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9000,
        background: "rgba(8,10,8,0.74)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        display: "grid",
        placeItems: "center",
        padding: "clamp(12px, 4vw, 24px)",
      }}
    >
      <div
        style={{
          width: "min(560px, 100%)",
          background: "#15171a",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 16,
          padding: "clamp(18px, 4vw, 26px) clamp(18px, 4vw, 26px) 20px",
          color: "#efece4",
          fontFamily: SYS_FONT,
          boxShadow: "0 30px 80px rgba(0,0,0,0.5)",
          maxHeight: "92vh",
          overflowY: "auto",
        }}
      >
        <div style={{ marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <Eyebrow>
            Manthan · Slack demo · step {Math.max(0, progressIdx) + 1} of {progressTotal}
          </Eyebrow>
          {state.slackDisplayName && (
            <span style={{ fontSize: 11, color: "rgba(239,236,228,0.45)" }}>
              joined as {state.slackDisplayName}
            </span>
          )}
        </div>

        {errorMsg && <ErrorBox>{errorMsg}</ErrorBox>}

        <StepBody
          state={state}
          template={template}
          onStartNow={() => setStep("join-workspace")}
          onOpenInvite={() => {
            if (template?.invite_url) {
              window.open(template.invite_url, "_blank", "noopener,noreferrer");
            }
            setStep("verify-join");
          }}
          onSentMention={async () => {
            // Inline one-shot lookup so we never sit on a polling step.
            // Try for ~4 seconds, then either advance to case-opened
            // (if we matched a case) or close the wizard and drop the
            // user on the inbox - the SSE-driven inbox surfaces the
            // case as soon as it lands, and the bot's "Watch live in
            // Manthan" thread button is the canonical entry anyway.
            const since = state.waitingStartedAt ?? Date.now() - 60_000;
            const deadline = Date.now() + 4000;
            while (Date.now() < deadline) {
              try {
                const r = await checkSlackInbound(state.loggedInEmail!, since);
                if (r.matched && r.case_id) {
                  setState((p) => ({
                    ...p,
                    step: "case-opened",
                    caseId: r.case_id,
                    shortId: r.short_id,
                  }));
                  return;
                }
              } catch {
                /* transient */
              }
              await new Promise((res) => window.setTimeout(res, 600));
            }
            // Nothing matched within the budget. Don't keep the user
            // staring at the wizard; let the inbox/Slack thread carry
            // them the rest of the way.
            clearState();
            onClose();
            navigate("/app");
          }}
          onAbortWaiting={() =>
            setState((p) => ({ ...p, step: "send-mention", waitingStartedAt: null }))
          }
          onFinish={() => {
            clearState();
            onClose();
            navigate("/app");
          }}
        />

        <ExitLink onClick={handleCancel} cancellable={cancellable} />
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Per-step content
// ──────────────────────────────────────────────────────────────────────

function StepBody(props: {
  state: DemoV3State;
  template: DemoV3Template | null;
  onStartNow: () => void;
  onOpenInvite: () => void;
  onSentMention: () => void;
  onAbortWaiting: () => void;
  onFinish: () => void;
}) {
  const { state, template } = props;

  switch (state.step) {
    case "intro":
      return (
        <>
          <H2>Manthan from Slack — autonomous mention triggers</H2>
          <P>
            The third trigger surface. You'll join a shared demo Slack
            workspace, @-mention <code>@manthantest</code> in{" "}
            <code>#all-manthandemo</code> with a chargeback to investigate,
            and watch the same end-to-end resolution flow but driven from
            a Slack thread.
          </P>
          <P style={{ color: "rgba(239,236,228,0.65)" }}>
            We'll route the case into <strong>your</strong> Manthan workspace
            because the bot can read your Slack email and match it to your
            login.
          </P>
          <ActionRow>
            <PrimaryButton onClick={props.onStartNow}>Start</PrimaryButton>
          </ActionRow>
        </>
      );

    case "join-workspace":
      if (!template) return <P>Loading…</P>;
      return (
        <>
          <H2>Join the ManthanDemo workspace</H2>
          <P>
            Open the invite link below. Slack will ask you to sign in or
            create a workspace account — use the same email you're
            logged into Manthan with so we can route the case back to{" "}
            <strong>your</strong> workspace.
          </P>
          <KVCard rows={[
            { label: "Workspace", value: template.workspace_name },
            { label: "Channel", value: template.channel },
            { label: "Bot handle", value: template.bot_handle },
            { label: "Your Manthan login", value: state.loggedInEmail ?? "—" },
          ]} />
          <VideoOrFallback
            src="/demo-v3/slack-mention.mp4"
            captionFallback={
              <>
                Once you're in the workspace, open{" "}
                <code>{template.channel}</code> from the channel sidebar
                and we'll show you exactly what to type.
              </>
            }
          />
          <ActionRow>
            <PrimaryButton onClick={props.onOpenInvite}>
              Open invite link
            </PrimaryButton>
          </ActionRow>
        </>
      );

    case "verify-join":
      return (
        <>
          <H2>Waiting for you to join…</H2>
          <P>
            Looking up <code>{state.loggedInEmail}</code> in the Slack
            workspace. As soon as you accept the invite this advances
            automatically.
          </P>
          <PulsingDot />
          <div
            style={{
              marginTop: 18,
              padding: "12px 14px",
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10,
              fontSize: 12.5,
              lineHeight: 1.55,
              color: "rgba(239,236,228,0.78)",
            }}
          >
            <div
              style={{
                fontSize: 10,
                letterSpacing: "0.16em",
                color: "rgba(239,236,228,0.45)",
                marginBottom: 6,
                textTransform: "uppercase",
              }}
            >
              Don't have an account on this workspace yet?
            </div>
            That message from Slack means you tried to sign in <em>before</em>{" "}
            accepting the invite. You need to open the invite link first —
            Slack will then let you create a fresh workspace account using{" "}
            <code>{state.loggedInEmail}</code>.
          </div>
          {template?.invite_url ? (
            <ActionRow style={{ marginTop: 12 }}>
              <PrimaryButton onClick={props.onOpenInvite}>
                Open invite link again
              </PrimaryButton>
            </ActionRow>
          ) : null}
          <P style={{ color: "rgba(239,236,228,0.55)", fontSize: 12.5, marginTop: 14 }}>
            Tip: when Slack asks for an email during the invite flow, use{" "}
            <strong>{state.loggedInEmail}</strong> — the same email
            you're signed into Manthan with. That's how we route the
            case back to your workspace.
          </P>
        </>
      );

    case "send-mention":
      if (!template) return <P>Loading…</P>;
      return (
        <>
          <H2>Tag the bot in <code>{template.channel}</code></H2>
          <P style={{ marginBottom: 8 }}>
            Important: you have to <strong>type the tag yourself</strong> -
            pasting <code>@manthantest</code> as plain text won't trigger
            an actual mention. Two steps:
          </P>
          <NumberedStep n={1}>
            In <code>{template.channel}</code>, click the message box and
            type <code>@manth</code>. Slack's autocomplete will surface
            <code> @manthantest</code> — press <kbd>Tab</kbd> or click it
            to accept the blue pill.
          </NumberedStep>
          <NumberedStep n={2}>
            After the <code>@manthantest</code> pill appears, paste or
            type this message and hit Enter:
          </NumberedStep>
          <CopyBlock value={template.mention_text} />
          <VideoOrFallback
            src="/demo-v3/slack-mention.mp4"
            captionFallback={
              <>
                Recording: click message box → type <code>@manth</code> →
                accept autocomplete → paste/type the message above →
                press Enter → bot replies in-thread.
              </>
            }
          />
          <ActionRow style={{ gap: 8 }}>
            <PrimaryButton onClick={props.onSentMention}>
              I've sent the mention
            </PrimaryButton>
          </ActionRow>
          <P style={{ color: "rgba(239,236,228,0.55)", fontSize: 11.5, marginTop: 10 }}>
            Last cancel point — once you confirm, we watch the case
            end-to-end.
          </P>
        </>
      );

    // "waiting-for-mention" removed - the onSentMention handler does
    // an inline one-shot lookup and either advances to case-opened
    // directly or closes the wizard. Old localStorage states that
    // still mention it fall through to the default case below.

    case "case-resolved":
      return (
        <>
          <H2>Resolved. Manthan replied in the thread.</H2>
          <P>
            The agent investigated across every connected source,
            decided per the matching policy, and posted the brief back
            into the Slack thread you started.
          </P>
          <P style={{ color: "rgba(239,236,228,0.75)" }}>
            <strong>Check Slack</strong> — the resolution card is now in
            your <code>{template?.channel ?? "#all-manthandemo"}</code>{" "}
            thread, and the resolved case lives in your Manthan inbox.
          </P>
          <ActionRow>
            <PrimaryButton onClick={props.onFinish}>Finish</PrimaryButton>
          </ActionRow>
        </>
      );

    case "done":
    default:
      return null;
  }
}

function WaitingPanel({
  startedAt,
  channel,
  onAbort,
}: {
  startedAt: number;
  channel: string;
  onAbort: () => void;
}) {
  const [elapsed, setElapsed] = useState(() => Date.now() - startedAt);
  useEffect(() => {
    const id = window.setInterval(() => setElapsed(Date.now() - startedAt), 500);
    return () => window.clearInterval(id);
  }, [startedAt]);
  const remaining = Math.max(0, POLL_TIMEOUT_MS - elapsed);
  const expired = remaining === 0;
  const mins = Math.floor(remaining / 60_000);
  const secs = Math.floor((remaining % 60_000) / 1_000);
  const pct = Math.min(100, (elapsed / POLL_TIMEOUT_MS) * 100);
  return (
    <>
      <H2>Listening for your mention…</H2>
      <P>
        We're polling for an <code>@manthantest</code> mention in{" "}
        <code>{channel}</code>. As soon as the bot receives it the case
        opens in your inbox.
      </P>
      <div
        style={{
          background: "rgba(255,255,255,0.06)",
          borderRadius: 999,
          height: 6,
          overflow: "hidden",
          margin: "10px 0 6px",
        }}
      >
        <div
          style={{
            background: expired ? "rgba(220,140,120,0.7)" : "rgba(22,208,94,0.7)",
            height: "100%",
            width: `${pct}%`,
            transition: "width 0.5s linear",
          }}
        />
      </div>
      <P style={{ color: expired ? "#ffb3a3" : "rgba(239,236,228,0.6)", fontSize: 12, margin: 0 }}>
        {expired
          ? "Didn't arrive within 5 minutes."
          : `Waiting · ${mins}:${String(secs).padStart(2, "0")} left`}
      </P>
      {expired && (
        <>
          <P style={{ marginTop: 12, fontSize: 13.5 }}>
            Common causes: mention wasn't sent in the right channel,
            bot wasn't tagged via autocomplete, or you sent it from a
            different Slack workspace. Try again from the previous step.
          </P>
          <ActionRow style={{ gap: 8 }}>
            <SecondaryButton onClick={onAbort}>Back to the send step</SecondaryButton>
          </ActionRow>
        </>
      )}
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Visual primitives (consciously copied from DemoV2Wizard so both
// wizards stay aesthetically aligned. Could be extracted to a shared
// primitives file if a v4 lands.)
// ──────────────────────────────────────────────────────────────────────

const SYS_FONT =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontFamily: '"Spectral", Georgia, serif',
        fontWeight: 500,
        fontStyle: "italic",
        fontSize: 24,
        lineHeight: 1.18,
        margin: "0 0 12px 0",
        color: "#efece4",
      }}
    >
      {children}
    </h2>
  );
}

function H3({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <h3
      style={{
        fontFamily: '"Spectral", Georgia, serif',
        fontWeight: 500,
        fontStyle: "italic",
        fontSize: 18,
        margin: "0 0 6px",
        color: "#efece4",
        ...style,
      }}
    >
      {children}
    </h3>
  );
}

function P({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <p
      style={{
        margin: "0 0 12px 0",
        fontSize: 14.5,
        lineHeight: 1.55,
        color: "rgba(239,236,228,0.85)",
        ...style,
      }}
    >
      {children}
    </p>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10,
        letterSpacing: "0.16em",
        textTransform: "uppercase",
        color: "rgba(239,236,228,0.45)",
      }}
    >
      {children}
    </div>
  );
}

function ErrorBox({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        background: "rgba(220,80,80,0.10)",
        border: "1px solid rgba(220,80,80,0.32)",
        color: "#ffb3b3",
        padding: "10px 12px",
        borderRadius: 10,
        fontSize: 13,
        marginBottom: 14,
      }}
    >
      {children}
    </div>
  );
}

function ActionRow({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "flex-end",
        gap: 10,
        marginTop: 18,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function PrimaryButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: disabled ? "rgba(22,208,94,0.35)" : "#16d05e",
        color: "#0a0c0a",
        border: 0,
        borderRadius: 10,
        padding: "10px 16px",
        fontSize: 13.5,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {children}
    </button>
  );
}

function SecondaryButton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: "transparent",
        color: "#efece4",
        border: "1px solid rgba(255,255,255,0.18)",
        borderRadius: 10,
        padding: "10px 14px",
        fontSize: 13.5,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function KVCard({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 10,
        padding: "10px 12px",
        margin: "8px 0 14px",
        display: "grid",
        gap: 6,
      }}
    >
      {rows.map((r) => (
        <div key={r.label} style={{ display: "flex", gap: 12, fontSize: 12.5 }}>
          <span
            style={{
              minWidth: 130,
              color: "rgba(239,236,228,0.5)",
              textTransform: "uppercase",
              letterSpacing: "0.12em",
              fontSize: 10.5,
            }}
          >
            {r.label}
          </span>
          <span style={{ color: "rgba(239,236,228,0.92)", wordBreak: "break-all" }}>
            {r.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function NumberedStep({
  n,
  children,
}: {
  n: number;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "22px 1fr",
        gap: 10,
        marginBottom: 10,
        fontSize: 13.5,
        lineHeight: 1.5,
        color: "rgba(239,236,228,0.85)",
      }}
    >
      <span
        style={{
          background: "rgba(22,208,94,0.16)",
          color: "#16d05e",
          borderRadius: 4,
          width: 22,
          height: 22,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          fontWeight: 600,
          fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
        }}
      >
        {n}
      </span>
      <div>{children}</div>
    </div>
  );
}

function CopyBlock({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* noop */
    }
  }, [value]);
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 10,
        padding: "10px 12px",
        marginBottom: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 6,
        }}
      >
        <div
          style={{
            fontSize: 10.5,
            letterSpacing: "0.14em",
            color: "rgba(239,236,228,0.5)",
            textTransform: "uppercase",
          }}
        >
          Mention text
        </div>
        <button
          onClick={onCopy}
          style={{
            background: copied ? "rgba(22,208,94,0.18)" : "transparent",
            color: copied ? "#16d05e" : "rgba(239,236,228,0.75)",
            border: `1px solid ${copied ? "rgba(22,208,94,0.36)" : "rgba(255,255,255,0.14)"}`,
            borderRadius: 6,
            padding: "3px 8px",
            fontSize: 11,
            cursor: "pointer",
          }}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <div
        style={{
          fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
          fontSize: 12.5,
          color: "rgba(239,236,228,0.92)",
          whiteSpace: "pre-wrap",
          lineHeight: 1.5,
          wordBreak: "break-word",
        }}
      >
        {value}
      </div>
    </div>
  );
}

function VideoOrFallback({
  src,
  captionFallback,
}: {
  src: string;
  captionFallback: React.ReactNode;
}) {
  // HEAD-probe the video so we render the fallback caption directly
  // instead of briefly painting a broken-video placeholder while the
  // browser races to discover the 404 on its own. Default to `missing`
  // and flip to `false` only when the asset confirms reachable. Net
  // result: when the recording isn't shipped, users see the clean text
  // instructions immediately.
  const [missing, setMissing] = useState(true);
  useEffect(() => {
    let cancelled = false;
    fetch(src, { method: "HEAD" })
      .then((r) => {
        if (cancelled) return;
        if (r.ok) setMissing(false);
      })
      .catch(() => {
        // Stay in fallback state - network failure or 404 both mean
        // we can't promise a video to the user.
      });
    return () => {
      cancelled = true;
    };
  }, [src]);
  if (missing) {
    return (
      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px dashed rgba(255,255,255,0.12)",
          borderRadius: 10,
          padding: "12px 14px",
          marginBottom: 12,
          fontSize: 12.5,
          color: "rgba(239,236,228,0.7)",
          lineHeight: 1.55,
        }}
      >
        <div
          style={{
            fontSize: 10,
            letterSpacing: "0.16em",
            color: "rgba(239,236,228,0.45)",
            marginBottom: 6,
            textTransform: "uppercase",
          }}
        >
          How to send it
        </div>
        {captionFallback}
      </div>
    );
  }
  return (
    <div style={{ marginBottom: 12 }}>
      <video
        src={src}
        autoPlay
        loop
        muted
        playsInline
        onError={() => setMissing(true)}
        style={{
          width: "100%",
          borderRadius: 10,
          border: "1px solid rgba(255,255,255,0.08)",
          background: "rgba(0,0,0,0.4)",
        }}
      />
    </div>
  );
}

function PulsingDot() {
  return (
    <div style={{ margin: "16px 0 4px" }}>
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: "#16d05e",
          animation: "manthan-pulse 1.4s ease-in-out infinite",
        }}
      />
      <style>{`
        @keyframes manthan-pulse {
          0%, 100% { opacity: 0.95; transform: scale(1); }
          50% { opacity: 0.35; transform: scale(0.7); }
        }
      `}</style>
    </div>
  );
}

function FloatingTip({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        position: "fixed",
        bottom: 20,
        left: 20,
        zIndex: 9000,
        width: 300,
        background: "rgba(21,23,26,0.92)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 12,
        padding: 14,
        color: "#efece4",
        fontFamily: SYS_FONT,
        boxShadow: "0 20px 50px rgba(0,0,0,0.45)",
        opacity: 0.85,
        transition: "opacity 160ms ease",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
      onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.85")}
    >
      {children}
    </div>
  );
}

function ExitLink({
  onClick,
  cancellable,
}: {
  onClick: () => void;
  cancellable: boolean;
}) {
  return (
    <div style={{ marginTop: 12, textAlign: "right" }}>
      <button
        onClick={onClick}
        style={{
          background: "transparent",
          color: "rgba(239,236,228,0.5)",
          border: "none",
          fontSize: 11,
          cursor: "pointer",
          padding: 0,
        }}
      >
        {cancellable ? "Cancel demo" : "Exit guide (case keeps running)"}
      </button>
    </div>
  );
}
