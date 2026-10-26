import { ClerkProvider } from "@clerk/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./globals.css";
import App from "./App";
import { ClerkIdentitySync } from "./components/auth/ClerkIdentitySync";
import { bootTheme } from "./lib/theme";

// Apply persisted theme BEFORE React mounts so there's no flash.
bootTheme();

// Publishable key - written into .env.local by `clerk init`. Vite
// exposes it via import.meta.env. Crash loudly if missing so the
// dev catches the misconfig before users do.
const CLERK_PUBLISHABLE_KEY = import.meta.env
  .VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

if (!CLERK_PUBLISHABLE_KEY) {
  // eslint-disable-next-line no-console
  console.warn(
    "[manthan] VITE_CLERK_PUBLISHABLE_KEY is not set - auth pages will " +
      "render a 'Clerk not configured' notice. Run `clerk env pull` or add " +
      "the key to manthan-ui/.env.local from dashboard.clerk.com.",
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider
      publishableKey={CLERK_PUBLISHABLE_KEY ?? ""}
      // After a successful auth, everyone lands in the demo workspace.
      // Same destination for sign-in and sign-up - once authenticated,
      // there is one place to be: /app.
      signInFallbackRedirectUrl="/app"
      signUpFallbackRedirectUrl="/app"
      // After sign-out we send them back to the marketing site.
      afterSignOutUrl="/"
    >
      {/* Bridges Clerk session → api module's X-Manthan-Dev-Email
          header so the dev tenant resolver picks the right member. */}
      <ClerkIdentitySync />
      <App />
    </ClerkProvider>
  </StrictMode>,
);
