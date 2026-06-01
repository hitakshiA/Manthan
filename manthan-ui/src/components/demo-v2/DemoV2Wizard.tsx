// DemoV2Wizard - guided interactive tour for the autonomous-email
// flow.
//
// Drives the user through the REAL product UI: spotlight the Policies
// sidebar link, then the New rule button, then each field of the
// create-rule modal, then back to Inbox, then through the email round-
// trip. The wizard never fills the form or clicks the buttons for the
// user - the point is they feel like they're operating the product.
//
// Each step is either:
//   - a Spotlight pointing at a real DOM element + tooltip card, or
//   - a center modal (intro, send-email instruction, waiting countdown,
//     outro).
//
// Steps auto-advance when their wait condition is met:
//   URL change       (router useLocation)
//   element appears  (a target selector becomes findable in the DOM)
//   element state    (input has content, button has data-tour-selected)
//   API state        (policy-ready, check-inbound)

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  CANCELLABLE_STEPS,
  NAV_LOCKED_STEPS,
  POLL_INTERVAL_MS,
  POLL_TIMEOUT_MS,
  STEP_ORDER,
  type DemoV2State,
  type DemoV2Template,
  type StepId,
  checkInbound,
  checkPolicyReady,
  clearState,
  fetchTemplate,
  freshState,
  loadState,
  resetPolicies,
  saveState,
  seedPolicy,
} from "@/lib/demo-v2";
import { Spotlight } from "./Spotlight";

interface DemoV2WizardProps {
  loggedInEmail: string;
  onClose: () => void;
}

export function DemoV2Wizard({ loggedInEmail, onClose }: DemoV2WizardProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const [state, setState] = useState<DemoV2State>(() => {
    return loadState() ?? freshState(loggedInEmail);
  });
  const [template, setTemplate] = useState<DemoV2Template | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Persist every state change.
  useEffect(() => {
    saveState(state);
  }, [state]);

  // Load the canonical template once. Also wipe any pre-existing
  // policies so the user gets a clean slate when starting the demo
  // (they'd be confused by leftover rules from a prior run).
  useEffect(() => {
    let cancelled = false;
    fetchTemplate()
      .then((t) => !cancelled && setTemplate(t))
      .catch((e) => !cancelled && setErrorMsg(`Couldn't load demo template: ${String(e)}`));
    // Best-effort wipe; we don't block the wizard on this.
    resetPolicies().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const setStep = useCallback((step: StepId) => {
    setState((prev) => ({ ...prev, step }));
  }, []);

  const cancellable = CANCELLABLE_STEPS.has(state.step);

  const handleCancel = useCallback(() => {
    if (!cancellable) return;
    clearState();
    onClose();
  }, [cancellable, onClose]);

  // ── DOM polling helper (used by several step wait conditions) ─────
  const useDomCondition = (predicate: () => boolean, enabled: boolean) => {
    useEffect(() => {
      if (!enabled) return;
      const tick = () => {
        try {
          if (predicate()) onAdvance();
        } catch {
          /* ignore */
        }
      };
      tick();
      const id = window.setInterval(tick, 250);
      return () => window.clearInterval(id);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, predicate]);
  };

  const onAdvance = useCallback(() => {
    const idx = STEP_ORDER.indexOf(state.step);
    const next = STEP_ORDER[Math.min(idx + 1, STEP_ORDER.length - 1)];
    if (next !== state.step) setStep(next);
  }, [state.step, setStep]);

  // ── Step-specific advance conditions ──────────────────────────────

  // goto-policies: advance when user navigates to /app/policy
  useEffect(() => {
    if (state.step === "goto-policies" && location.pathname.startsWith("/app/policy")) {
      onAdvance();
    }
  }, [state.step, location.pathname, onAdvance]);

  // goto-inbox: advance when user navigates to /app (and only /app)
  useEffect(() => {
    if (state.step === "goto-inbox" && location.pathname === "/app") {
      onAdvance();
    }
  }, [state.step, location.pathname, onAdvance]);

  // click-new-rule: advance when the create-rule modal opens (we
  // detect this by waiting for the Name input to appear in the DOM)
  useDomCondition(
    () => !!document.querySelector('[data-tour-target="rule-name-input"]'),
    state.step === "click-new-rule",
  );

  // name-rule: advance when the Name input has any content
  useDomCondition(
    () => {
      const el = document.querySelector(
        '[data-tour-target="rule-name-input"]',
      ) as HTMLInputElement | null;
      return !!el && el.value.trim().length > 0;
    },
    state.step === "name-rule",
  );

  // select-auto-mode: advance when the auto-execute button is selected
  useDomCondition(
    () => {
      const el = document.querySelector('[data-tour-target="rule-mode-auto"]');
      return el?.getAttribute("data-tour-selected") === "true";
    },
    state.step === "select-auto-mode",
  );

  // save-rule: advance when the demo policy actually exists in the DB
  // (the modal closes too, but polling the API is more reliable - if
  // the save errored we don't want to advance prematurely).
  useEffect(() => {
    if (state.step !== "save-rule") return;
    let aborted = false;
    const tick = async () => {
      try {
        const r = await checkPolicyReady();
        if (!aborted && r.ready) onAdvance();
      } catch {
        /* ignore */
      }
    };
    const id = window.setInterval(tick, 1500);
    return () => {
      aborted = true;
      window.clearInterval(id);
    };
  }, [state.step, onAdvance]);

  // waiting-for-email: poll check-inbound
  useEffect(() => {
    if (state.step !== "waiting-for-email") return;
    if (!state.senderEmail || !state.waitingStartedAt) return;
    let aborted = false;
    const tick = async () => {
      if (aborted) return;
      try {
        const r = await checkInbound(state.senderEmail!, state.waitingStartedAt!);
        if (aborted) return;
        if (r.matched && r.case_id) {
          setState((prev) => ({
            ...prev,
            step: "case-opened",
            caseId: r.case_id,
            shortId: r.short_id,
          }));
        }
      } catch {
        /* transient */
      }
    };
    void tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      aborted = true;
      window.clearInterval(id);
    };
  }, [state.step, state.senderEmail, state.waitingStartedAt]);

  // case-opened: navigate to the case + watch for resolution
  useEffect(() => {
    if (state.step !== "case-opened" || !state.caseId) return;
    const target = `/app/case/${state.caseId}`;
    if (!location.pathname.startsWith(target)) navigate(target);
  }, [state.step, state.caseId, location.pathname, navigate]);

  useEffect(() => {
    if (state.step !== "case-opened") return;
    if (!state.senderEmail || !state.waitingStartedAt) return;
    let aborted = false;
    const tick = async () => {
      try {
        const r = await checkInbound(state.senderEmail!, state.waitingStartedAt!);
        if (!aborted && r.matched && (r.status === "resolved" || r.status === "errored")) {
          setStep("case-resolved");
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
  }, [state.step, state.senderEmail, state.waitingStartedAt, setStep]);

  // Nav lock during the watch / wait phases
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

  // ── Action handlers from the tooltip cards ────────────────────────

  const handleSentEmail = useCallback(() => {
    setState((prev) => ({
      ...prev,
      step: "waiting-for-email",
      waitingStartedAt: Date.now(),
    }));
  }, []);

  const handleAbortWaiting = useCallback(() => {
    setStep("send-email");
    setState((prev) => ({ ...prev, waitingStartedAt: null }));
  }, [setStep]);

  const handleFinish = useCallback(() => {
    clearState();
    onClose();
    navigate("/app");
  }, [navigate, onClose]);

  // "Do it for me" escape hatch on the form steps. Calls the seed-policy
  // endpoint (idempotent) to create the rule directly, then jumps the
  // tour past the form to the goto-inbox step. The user still drives
  // every later step - this just spares them the dropdown fiddle on the
  // rule editor if they'd rather skip.
  const [autofillBusy, setAutofillBusy] = useState(false);
  const handleAutofillPolicy = useCallback(async () => {
    setAutofillBusy(true);
    setErrorMsg(null);
    try {
      const r = await seedPolicy();
      if (!r.ready) throw new Error("seed-policy did not report ready");
      setStep("goto-inbox");
    } catch (e) {
      setErrorMsg(`Couldn't set up the policy: ${String(e)}`);
    } finally {
      setAutofillBusy(false);
    }
  }, [setStep]);

  // ── Render ────────────────────────────────────────────────────────

  return (
    <StepRenderer
      state={state}
      template={template}
      errorMsg={errorMsg}
      cancellable={cancellable}
      autofillBusy={autofillBusy}
      onCancel={handleCancel}
      onStartNow={() => setStep("goto-policies")}
      onManualNext={onAdvance}
      onAutofillPolicy={handleAutofillPolicy}
      onSentEmail={handleSentEmail}
      onAbortWaiting={handleAbortWaiting}
      onFinish={handleFinish}
    />
  );
}

// ──────────────────────────────────────────────────────────────────────
// Step renderer - picks Spotlight vs CenterModal based on step
// ──────────────────────────────────────────────────────────────────────

function StepRenderer(props: {
  state: DemoV2State;
  template: DemoV2Template | null;
  errorMsg: string | null;
  cancellable: boolean;
  autofillBusy: boolean;
  onCancel: () => void;
  onStartNow: () => void;
  onManualNext: () => void;
  onAutofillPolicy: () => void;
  onSentEmail: () => void;
  onAbortWaiting: () => void;
  onFinish: () => void;
}) {
  const { state, template, errorMsg, cancellable, autofillBusy, onCancel } = props;

  // Tiny "skip the form" affordance for the policy-creation steps.
  // Calls seed-policy then jumps straight to goto-inbox.
  const skipAhead = (
    <div style={{ marginTop: 10, fontSize: 11.5 }}>
      <button
        onClick={props.onAutofillPolicy}
        disabled={autofillBusy}
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          color: "rgba(22,208,94,0.85)",
          cursor: autofillBusy ? "wait" : "pointer",
          textDecoration: "underline",
          textUnderlineOffset: 3,
          fontSize: 11.5,
        }}
      >
        {autofillBusy
          ? "Setting up…"
          : "Or — set up the policy for me and skip ahead"}
      </button>
    </div>
  );
  const stepNum = Math.max(0, STEP_ORDER.indexOf(state.step)) + 1;
  const totalSteps = STEP_ORDER.length - 1; // hide "done" from count

  // Common tooltip wrapper - adds the step number + cancel button
  const tipFrame = (body: React.ReactNode) => (
    <>
      <div
        style={{
          fontSize: 10,
          letterSpacing: "0.16em",
          color: "rgba(239,236,228,0.45)",
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        Step {stepNum} of {totalSteps}
      </div>
      {body}
      {errorMsg && <ErrorBox>{errorMsg}</ErrorBox>}
      {cancellable && (
        <div style={{ marginTop: 12, textAlign: "right" }}>
          <button
            onClick={onCancel}
            style={{
              background: "transparent",
              color: "rgba(239,236,228,0.5)",
              border: "none",
              fontSize: 11,
              cursor: "pointer",
              padding: 0,
            }}
          >
            Cancel demo
          </button>
        </div>
      )}
    </>
  );

  switch (state.step) {
    case "intro":
      return (
        <CenterModal>
          {tipFrame(
            <>
              <H2>Set up an autonomous billing agent — together.</H2>
              <P>
                Manthan can read customer emails, investigate across every
                connected system, and resolve cases on its own when a policy
                says it can.
              </P>
              <P>
                You'll walk through the real product to set a policy, then
                send a real email and watch Manthan handle it end to end.
                I'll guide each step — you do the clicking.
              </P>
              <ActionRow>
                <Primary onClick={props.onStartNow}>Begin</Primary>
              </ActionRow>
            </>,
          )}
        </CenterModal>
      );

    case "goto-policies":
      return (
        <Spotlight
          target='a[href="/app/policy"]'
          tooltip={tipFrame(
            <>
              <H3>Open the Policies page</H3>
              <P>
                Policies are the rules Manthan follows when deciding whether
                to act on its own. Click <strong>Policies</strong> in the
                sidebar.
              </P>
            </>,
          )}
        />
      );

    case "click-new-rule":
      return (
        <Spotlight
          target='[data-tour-target="new-rule-button"]'
          tooltip={tipFrame(
            <>
              <H3>Create a new rule</H3>
              <P>
                Click <strong>New rule</strong> to open the policy editor.
              </P>
            </>,
          )}
        />
      );

    case "name-rule":
      return (
        <Spotlight
          target='[data-tour-target="rule-name-input"]'
          tooltip={tipFrame(
            <>
              <H3>Name the policy</H3>
              <P>
                Give it a clear identifier. Try:
              </P>
              <CodeRow value="autonomous-email-refunds" />
              <P style={{ marginTop: 8, color: "rgba(239,236,228,0.55)", fontSize: 12.5 }}>
                Names are kebab-case by convention. Anything works as long
                as it's unique.
              </P>
              {skipAhead}
            </>,
          )}
        />
      );

    case "set-conditions":
      return (
        <Spotlight
          target='[data-tour-target="rule-conditions"]'
          tooltip={tipFrame(
            <>
              <H3>Set the trigger conditions</H3>
              <P>
                Tell Manthan <em>when</em> to fire this rule. For the demo,
                we want refund requests that came in by email. Set:
              </P>
              <CondRow field="case.case_type" op="eq" value="refund_request" />
              <P style={{ marginTop: 8 }}>
                Then click <strong>+ Add condition</strong> and add:
              </P>
              <CondRow field="case.trigger_surface" op="eq" value="inbound_email" />
              <ActionRow style={{ marginTop: 12 }}>
                <Primary onClick={props.onManualNext}>Done — next</Primary>
              </ActionRow>
              {skipAhead}
            </>,
          )}
        />
      );

    case "select-auto-mode":
      return (
        <Spotlight
          target='[data-tour-target="rule-mode-group"]'
          tooltip={tipFrame(
            <>
              <H3>Choose auto-execute</H3>
              <P>
                Modes control what happens when the rule matches:
              </P>
              <ul
                style={{
                  margin: "6px 0 10px 0",
                  paddingLeft: 16,
                  fontSize: 13,
                  color: "rgba(239,236,228,0.78)",
                  lineHeight: 1.55,
                }}
              >
                <li><strong>auto-execute</strong> — Manthan acts immediately, no review.</li>
                <li><strong>recommend</strong> — drafts the brief, you approve.</li>
                <li><strong>escalate</strong> — pushes to a human reviewer.</li>
              </ul>
              <P>
                Click <strong>auto-execute</strong> so Manthan handles the
                demo case without asking.
              </P>
              {skipAhead}
            </>,
          )}
        />
      );

    case "save-rule":
      return (
        <Spotlight
          target='[data-tour-target="rule-save"]'
          tooltip={tipFrame(
            <>
              <H3>Save the rule</H3>
              <P>
                Click <strong>Create rule</strong>. We'll detect it landed
                and move you to the next step automatically.
              </P>
              {skipAhead}
            </>,
          )}
        />
      );

    case "goto-inbox":
      return (
        <Spotlight
          target='a[href="/app"]'
          tooltip={tipFrame(
            <>
              <H3>Back to the Inbox</H3>
              <P>
                Your policy is live. Click <strong>Inbox</strong> in the
                sidebar so you're set up to receive the case.
              </P>
            </>,
          )}
        />
      );

    case "send-email":
      return (
        <CenterModal>
          {tipFrame(
            <SendEmailBody
              template={template}
              loggedInEmail={state.senderEmail ?? ""}
              onSentEmail={props.onSentEmail}
            />,
          )}
        </CenterModal>
      );

    case "waiting-for-email":
      return (
        <CenterModal>
          {tipFrame(
            <WaitingBody
              startedAt={state.waitingStartedAt ?? Date.now()}
              loggedInEmail={state.senderEmail ?? ""}
              onAbort={props.onAbortWaiting}
            />,
          )}
        </CenterModal>
      );

    case "case-opened":
      // Don't dim - the workspace itself is the show. Just float a
      // small tip at the top-right explaining what's about to happen.
      return (
        <FloatingTip>
          {tipFrame(
            <>
              <H3>Watching Manthan work</H3>
              <P>
                Behind this card, Manthan is querying every connected
                source — billing records, customer history, the policy
                doc you just set. Because the policy says auto-execute,
                actions will fire the moment the brief is ready. No
                approve button.
              </P>
              <P style={{ color: "rgba(239,236,228,0.55)", fontSize: 12 }}>
                Case {state.shortId ?? ""} · usually 30-90 seconds.
              </P>
            </>,
          )}
        </FloatingTip>
      );

    case "case-resolved":
      return (
        <CenterModal>
          {tipFrame(
            <>
              <H2>Resolved end-to-end.</H2>
              <P>
                Manthan investigated, decided per the policy you set, fired
                the refund, and emailed your customer back.
              </P>
              <P style={{ color: "rgba(239,236,228,0.78)" }}>
                <strong>Check your inbox</strong> — there's a reply waiting
                for you ("Re: {template?.subject ?? "your refund"}"). That's
                the actual email Manthan sent your customer, delivered to
                you because you sent the demo from your own address.
              </P>
              <ActionRow>
                <Primary onClick={props.onFinish}>Finish</Primary>
              </ActionRow>
            </>,
          )}
        </CenterModal>
      );

    case "done":
      return null;
  }
}

// ──────────────────────────────────────────────────────────────────────
// Body subcomponents
// ──────────────────────────────────────────────────────────────────────

function SendEmailBody({
  template,
  loggedInEmail,
  onSentEmail,
}: {
  template: DemoV2Template | null;
  loggedInEmail: string;
  onSentEmail: () => void;
}) {
  if (!template) return <P>Loading template…</P>;
  const mailto =
    `mailto:${encodeURIComponent(template.to)}` +
    `?subject=${encodeURIComponent(template.subject)}` +
    `&body=${encodeURIComponent(template.body)}`;
  return (
    <>
      <H2>Now send the test email</H2>
      <P>
        Send the message below from <strong>{loggedInEmail}</strong> so
        Manthan can verify the round-trip against your account.
      </P>
      <CopyRow label="To" value={template.to} />
      <CopyRow label="Subject" value={template.subject} />
      <CopyRow label="Body" value={template.body} multiline />
      <ActionRow style={{ gap: 8 }}>
        <Secondary onClick={() => window.open(mailto, "_blank")}>
          Compose in mail client
        </Secondary>
        <Primary onClick={onSentEmail}>I've sent it</Primary>
      </ActionRow>
      <P style={{ color: "rgba(239,236,228,0.55)", fontSize: 11.5, marginTop: 10 }}>
        Last cancel point — once you confirm we'll wait for the inbound
        case and lock the page until the agent finishes.
      </P>
    </>
  );
}

function WaitingBody({
  startedAt,
  loggedInEmail,
  onAbort,
}: {
  startedAt: number;
  loggedInEmail: string;
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
      <H2>Listening for your email…</H2>
      <P>
        Polling for an inbound email from <strong>{loggedInEmail}</strong>.
        As soon as it lands, we'll jump you to the case.
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
            background: expired
              ? "rgba(220,140,120,0.7)"
              : "rgba(22,208,94,0.7)",
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
        <ActionRow style={{ gap: 8 }}>
          <Secondary onClick={onAbort}>Back to the send step</Secondary>
        </ActionRow>
      )}
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Primitives
// ──────────────────────────────────────────────────────────────────────

function CenterModal({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9000,
        background: "rgba(8,10,8,0.74)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "min(540px, 100%)",
          background: "#15171a",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 16,
          padding: "26px 26px 20px",
          color: "#efece4",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          boxShadow: "0 30px 80px rgba(0,0,0,0.5)",
        }}
      >
        {children}
      </div>
    </div>
  );
}

function FloatingTip({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        position: "fixed",
        top: 20,
        right: 20,
        zIndex: 9000,
        width: 340,
        background: "#15171a",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 12,
        padding: "16px",
        color: "#efece4",
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        boxShadow: "0 20px 50px rgba(0,0,0,0.45)",
      }}
    >
      {children}
    </div>
  );
}

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
      }}
    >
      {children}
    </h2>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        fontFamily: '"Spectral", Georgia, serif',
        fontWeight: 500,
        fontStyle: "italic",
        fontSize: 18,
        lineHeight: 1.25,
        margin: "0 0 8px 0",
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
        margin: "0 0 10px 0",
        fontSize: 13.5,
        lineHeight: 1.55,
        color: "rgba(239,236,228,0.84)",
        ...style,
      }}
    >
      {children}
    </p>
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
        marginTop: 16,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function Primary({
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
        padding: "9px 14px",
        fontSize: 13,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {children}
    </button>
  );
}

function Secondary({
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
        padding: "9px 14px",
        fontSize: 13,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function ErrorBox({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        background: "rgba(220,80,80,0.10)",
        border: "1px solid rgba(220,80,80,0.32)",
        color: "#ffb3b3",
        padding: "8px 10px",
        borderRadius: 8,
        fontSize: 12.5,
        marginTop: 10,
      }}
    >
      {children}
    </div>
  );
}

function CodeRow({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        } catch {
          /* ignore */
        }
      }}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        background: "rgba(255,255,255,0.05)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 8,
        padding: "8px 10px",
        fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
        fontSize: 12.5,
        color: "rgba(239,236,228,0.92)",
        cursor: "pointer",
        transition: "background 150ms",
      }}
      title="Copy"
    >
      {value}
      <span
        style={{
          float: "right",
          fontSize: 10,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: copied ? "#16d05e" : "rgba(239,236,228,0.4)",
        }}
      >
        {copied ? "Copied" : "Copy"}
      </span>
    </button>
  );
}

function CondRow({ field, op, value }: { field: string; op: string; value: string }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto 1fr",
        gap: 6,
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 8,
        padding: "6px 8px",
        fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
        fontSize: 12,
        color: "rgba(239,236,228,0.9)",
        marginTop: 6,
      }}
    >
      <span style={{ color: "rgba(120,200,140,0.95)" }}>{field}</span>
      <span style={{ color: "rgba(239,236,228,0.5)" }}>{op}</span>
      <span style={{ color: "rgba(255,210,140,0.95)" }}>{value}</span>
    </div>
  );
}

function CopyRow({
  label,
  value,
  multiline,
}: {
  label: string;
  value: string;
  multiline?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 8,
        padding: "8px 10px",
        marginBottom: 6,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: multiline ? 5 : 0,
          gap: 10,
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
          {label}
        </div>
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1200);
            } catch {
              /* noop */
            }
          }}
          style={{
            background: copied ? "rgba(22,208,94,0.18)" : "transparent",
            color: copied ? "#16d05e" : "rgba(239,236,228,0.75)",
            border: `1px solid ${
              copied ? "rgba(22,208,94,0.36)" : "rgba(255,255,255,0.14)"
            }`,
            borderRadius: 6,
            padding: "3px 8px",
            fontSize: 10.5,
            cursor: "pointer",
            transition: "all 120ms",
          }}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <div
        style={{
          fontFamily: multiline
            ? 'ui-sans-serif, system-ui, -apple-system, sans-serif'
            : 'ui-monospace, "SF Mono", Menlo, monospace',
          fontSize: multiline ? 12.5 : 12,
          color: "rgba(239,236,228,0.92)",
          whiteSpace: multiline ? "pre-wrap" : "nowrap",
          overflow: multiline ? "visible" : "hidden",
          textOverflow: multiline ? "clip" : "ellipsis",
          lineHeight: multiline ? 1.5 : 1.3,
        }}
      >
        {value}
      </div>
    </div>
  );
}
