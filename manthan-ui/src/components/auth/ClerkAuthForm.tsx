/**
 * ClerkAuthForm - Clerk's `<SignIn>` / `<SignUp>` themed for the dark
 * AuthShell.
 *
 * We deliberately do NOT use a base theme package; instead we tune
 * `appearance.variables` + `elements` so the widget visually matches the
 * existing form (white-on-dark, accent green for the primary button,
 * rounded-xl 14px height, no extra chrome). That keeps the design the
 * user originally crafted - Clerk only owns the submission logic.
 *
 * If `VITE_CLERK_PUBLISHABLE_KEY` isn't set, the widget falls back to a
 * quiet hint pointing the operator at the env file. The Try-demo block
 * above stays usable in either state.
 */

import { SignIn, SignUp } from "@clerk/react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as
  | string
  | undefined;

/** Tokens kept in sync with globals.css `--color-accent` etc. so the
 *  Clerk widget reads as part of the same palette. */
const APPEARANCE = {
  variables: {
    colorPrimary: "oklch(0.62 0.15 150)", // accent green
    colorBackground: "transparent",
    colorText: "#ffffff",
    colorTextSecondary: "rgba(255,255,255,0.55)",
    colorInputBackground: "rgba(255,255,255,0.04)",
    colorInputText: "#ffffff",
    colorNeutral: "#ffffff",
    fontFamily: '"Geist", "Inter", system-ui, sans-serif',
    fontSize: "14px",
    borderRadius: "12px",
  },
  elements: {
    // Strip the framed card chrome AND override Clerk's default ~25rem
    // card width so the widget fills the AuthShell's right column.
    // We have to set width on multiple wrapper elements because Clerk's
    // internal structure is rootBox → cardBox → card → main → form.
    rootBox: {
      width: "100%",
      maxWidth: "100%",
      margin: "0",
    },
    cardBox: {
      width: "100%",
      maxWidth: "100%",
      margin: "0",
      boxShadow: "none",
      border: "none",
      background: "transparent",
    },
    card: {
      width: "100%",
      maxWidth: "100%",
      background: "transparent",
      boxShadow: "none",
      padding: 0,
      border: "none",
    },
    main: { width: "100%" },
    // We render our own h1 in the page; suppress Clerk's header so we
    // don't get a duplicate "Sign in" line.
    header: { display: "none" },
    headerTitle: { display: "none" },
    headerSubtitle: { display: "none" },
    // Social buttons - match our SocialButton look.
    socialButtonsBlockButton: {
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.10)",
      color: "#ffffff",
      borderRadius: "12px",
      height: "44px",
    },
    socialButtonsBlockButtonText: { color: "#ffffff" },
    dividerLine: { background: "rgba(255,255,255,0.10)" },
    dividerText: { color: "rgba(255,255,255,0.45)", fontSize: "12px" },
    // Inputs.
    formFieldLabel: {
      color: "rgba(255,255,255,0.60)",
      fontSize: "13px",
      fontWeight: 400,
    },
    formFieldInput: {
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.10)",
      color: "#ffffff",
      borderRadius: "12px",
      height: "48px",
    },
    formFieldInputShowPasswordButton: { color: "rgba(255,255,255,0.55)" },
    formFieldHintText: { color: "rgba(255,255,255,0.45)" },
    formFieldErrorText: { color: "var(--color-danger, #d04545)" },
    // Primary submit - match the existing white-on-black submit style
    // (we keep the white-on-black look operators are used to instead of
    // accent-green here, because it sits next to the "Try the demo"
    // accent block and we don't want two competing greens).
    formButtonPrimary: {
      background: "#ffffff",
      color: "#000000",
      height: "56px",
      borderRadius: "14px",
      fontWeight: 600,
      fontSize: "14px",
      "&:hover": { background: "rgba(255,255,255,0.92)" },
    },
    formButtonReset: { color: "rgba(255,255,255,0.55)" },
    // Footer (Clerk's "Don't have an account? Sign up" line). We hide it
    // because our page already shows "Member of the team? Log in".
    footer: { display: "none" },
    footerAction: { display: "none" },
    footerActionLink: { display: "none" },
    // Verification screens / OTP - match input styling.
    otpCodeFieldInput: {
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.10)",
      color: "#ffffff",
    },
    identityPreview: {
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.10)",
      color: "#ffffff",
    },
    identityPreviewText: { color: "rgba(255,255,255,0.85)" },
    identityPreviewEditButton: { color: "var(--color-accent, #3a8a55)" },
  },
} as const;

/** Common props. Both SignIn and SignUp accept `path`, `routing`,
 *  and `*Url` (where they go on success / pivot). */
const COMMON = {
  appearance: APPEARANCE,
  /** Clerk's router-aware mode - keeps url state inside react-router. */
  routing: "path" as const,
  signInUrl: "/login",
  signUpUrl: "/signup",
  /** After a successful auth, drop them in the live workspace. */
  signInFallbackRedirectUrl: "/app",
  signUpFallbackRedirectUrl: "/app",
  forceRedirectUrl: undefined,
};

export function ClerkAuthForm({ mode }: { mode: "signin" | "signup" }) {
  if (!CLERK_KEY) {
    return <MissingKeyNotice />;
  }
  return mode === "signin" ? (
    <SignIn {...COMMON} path="/login" />
  ) : (
    <SignUpWithExistsDetection />
  );
}

/**
 * Wraps Clerk's `<SignUp />` widget with a watcher that catches the
 * specific "account already exists" failure mode - which Clerk
 * surfaces as a generic "Unable to complete action at this time"
 * error message. When a user clicks Google/GitHub on the sign-up
 * form but their OAuth identity is already registered, that vague
 * error is all Clerk offers; we replace it with a clear banner
 * pointing at the sign-in page.
 *
 * Detection is text-pattern based on the widget's rendered DOM -
 * the only signal Clerk exposes for this state without going
 * full-custom-UI with `useSignUp`.
 */
function SignUpWithExistsDetection() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [accountExists, setAccountExists] = useState(false);

  useEffect(() => {
    const root = wrapRef.current;
    if (!root) return;

    const check = () => {
      // The Clerk error message we want to catch. The phrasing of
      // "Unable to complete action at this time" is what Clerk shows
      // for OAuth-identity-already-linked failures, which is the
      // single most likely cause when a user clicks Google/GitHub
      // on a sign-up form for an account they've created before.
      const text = (root.textContent || "").toLowerCase();
      const matched =
        text.includes("unable to complete action") ||
        text.includes("already exists") ||
        text.includes("already taken") ||
        text.includes("identifier already exists");
      setAccountExists(matched);
    };

    const obs = new MutationObserver(check);
    obs.observe(root, { childList: true, subtree: true, characterData: true });
    // Initial check in case the message rendered before we wired up.
    check();
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={wrapRef} className="relative">
      {accountExists && <AccountExistsBanner />}
      <SignUp {...COMMON} path="/signup" />
    </div>
  );
}

/**
 * Banner shown when sign-up fails because the OAuth/email identity is
 * already in the system. Routes the visitor to /login with a clean
 * one-line explanation - no jargon, no "contact support".
 */
function AccountExistsBanner() {
  return (
    <div
      className="rounded-xl p-4 mb-4 flex items-start gap-3"
      style={{
        background: "rgba(86, 207, 131, 0.08)",
        border: "1px solid rgba(86, 207, 131, 0.30)",
        color: "rgba(255,255,255,0.92)",
      }}
      role="alert"
    >
      <span
        aria-hidden
        className="shrink-0 inline-flex items-center justify-center mt-0.5"
        style={{
          width: 18,
          height: 18,
          borderRadius: 999,
          background: "var(--color-accent, #56cf83)",
          color: "#0a0a0a",
          fontSize: 11,
          fontWeight: 700,
        }}
      >
        ✓
      </span>
      <div className="flex-1 min-w-0">
        <div
          className="text-[12px] uppercase mb-1"
          style={{
            color: "rgba(86, 207, 131, 0.92)",
            letterSpacing: "0.14em",
            fontWeight: 500,
          }}
        >
          You already have an account
        </div>
        <p
          className="text-[13px] leading-relaxed"
          style={{ color: "rgba(255,255,255,0.78)" }}
        >
          Looks like you&apos;ve signed up here before. Sign in to pick up
          where you left off.
        </p>
        <Link
          to="/login"
          className="inline-flex items-baseline gap-1.5 mt-2.5 text-[13px] font-medium hover:opacity-90"
          style={{
            color: "var(--color-accent, #56cf83)",
            paddingBottom: 2,
            borderBottom: "1px solid var(--color-accent, #56cf83)",
          }}
        >
          Sign in instead →
        </Link>
      </div>
    </div>
  );
}

function MissingKeyNotice() {
  return (
    <div
      className="rounded-xl p-4 text-sm"
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.10)",
        color: "rgba(255,255,255,0.75)",
      }}
    >
      <div
        className="text-[11px] uppercase tracking-[0.14em] mb-1"
        style={{ color: "rgba(255,255,255,0.5)" }}
      >
        Clerk not configured
      </div>
      <p className="leading-relaxed">
        Set <code className="font-mono">VITE_CLERK_PUBLISHABLE_KEY</code>{" "}
        in <code className="font-mono">manthan-ui/.env.local</code> from
        your{" "}
        <a
          href="https://dashboard.clerk.com"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "var(--color-accent, #3a8a55)" }}
        >
          Clerk dashboard
        </a>{" "}
        - the publishable key starts with{" "}
        <code className="font-mono">pk_test_</code>. Restart{" "}
        <code className="font-mono">npm run dev</code> afterwards.
      </p>
    </div>
  );
}
