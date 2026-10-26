/**
 * Signup - faithful port of Aurora Onboard's right column.
 *
 * - "Create New Profile" header + subtitle
 * - 2-col Google + GitHub socials
 * - "Or" divider
 * - 2-col first/last name
 * - Email full width
 * - Password full width with Eye toggle + hint
 * - Submit "Create Account" - w-full h-14 bg-white text-black rounded-xl
 * - Footer link "Member of the team? Log in"
 */

import { Link } from "react-router-dom";
import { AuthShell } from "@/components/auth/AuthShell";
import { ClerkAuthForm } from "@/components/auth/ClerkAuthForm";
import { useLockedTheme } from "@/lib/theme";

export default function Signup() {
  // Auth pages are designed around dark; lock to it regardless of the
  // user's stored workspace theme preference.
  useLockedTheme("dark");
  return (
    <AuthShell
      heading="Join Manthan"
      description="Follow these 3 quick phases to activate your space."
      activeStep={0}
      steps={[
        { label: "Register your identity" },
        { label: "Connect your stack" },
        { label: "Finalize your profile" },
      ]}
    >
      <header>
        <h1 className="text-3xl font-medium tracking-tight">
          Create New Profile
        </h1>
        <p className="mt-1.5 text-sm text-white/40">
          Input your basic details to begin the journey.
        </p>
      </header>

      {/* Clerk-hosted sign-up - themed to match the dark form style.
          Brings the social buttons + divider + email/password fields
          inside one widget. Submission lands on Clerk; on success Clerk
          redirects to `/app` per the provider config in main.tsx.
          Note: there is intentionally no "Try the demo · no signup"
          bypass on this page - authentication is the only path into
          the workspace so every visitor's email is captured (Clerk's
          user.created webhook fires the MVP welcome). */}
      <ClerkAuthForm mode="signup" />

      <p className="text-center text-sm text-white/50">
        Member of the team?{" "}
        <Link to="/login" className="text-white hover:underline font-medium">
          Log in
        </Link>
      </p>
    </AuthShell>
  );
}
