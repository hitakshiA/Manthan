import { Link } from "react-router-dom";
import { AuthShell } from "@/components/auth/AuthShell";
import { ClerkAuthForm } from "@/components/auth/ClerkAuthForm";
import { useLockedTheme } from "@/lib/theme";

export default function Login() {
  // Auth pages are designed around dark; lock to it regardless of the
  // user's stored workspace theme preference.
  useLockedTheme("dark");
  return (
    <AuthShell
      heading="Welcome back"
      description="Your AI worker has been busy. Pick up where you left off."
      activeStep={-1}
      steps={[
        { label: "Sign in to your workspace" },
        { label: "Review pending approvals" },
        { label: "Watch the queue work" },
      ]}
    >
      <header>
        <h1 className="text-3xl font-medium tracking-tight">Sign in</h1>
        <p className="mt-1.5 text-sm text-white/40">
          Continue to your Manthan workspace.
        </p>
      </header>

      {/* Clerk-hosted sign-in - themed to match the dark form style.
          On success Clerk redirects to `/app` per the provider config
          in main.tsx. The earlier "Try the demo · no signup" bypass
          has been removed by design: authentication is the only path
          into the workspace, so every visitor lands as a known user. */}
      <ClerkAuthForm mode="signin" />

      <p className="text-center text-sm text-white/50">
        New to Manthan?{" "}
        <Link to="/signup" className="text-white hover:underline font-medium">
          Create an account
        </Link>
      </p>
    </AuthShell>
  );
}
