import { lazy, Suspense } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";

// Landing stays eager: it's the first thing every cold visitor hits,
// so SEO + first-paint takes priority over chunk size. Login + Signup
// also stay eager because they're the second-most-likely entry routes
// from a hard refresh.
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import { AppShell } from "./components/app/AppShell";

// Everything below is route-split. Each becomes its own JS chunk that
// the browser only fetches when the user actually navigates there.
// React.lazy + Suspense lets the first cold-load skip ~85% of the
// bundle (the entire /app/* admin surface).
const Onboarding = lazy(() => import("./pages/Onboarding"));
const Changelog = lazy(() => import("./pages/Changelog"));
const Contact = lazy(() => import("./pages/Contact"));
const Privacy = lazy(() => import("./pages/Privacy"));
const Terms = lazy(() => import("./pages/Terms"));
const DPA = lazy(() => import("./pages/DPA"));
const Blog = lazy(() => import("./pages/Blog"));
const BlogTokensAreTheNewSalary = lazy(
  () => import("./pages/BlogTokensAreTheNewSalary"),
);

const Workspace = lazy(() => import("./pages/Workspace"));
const Sources = lazy(() => import("./pages/Sources"));
const Approvals = lazy(() => import("./pages/Approvals"));
const Settings = lazy(() => import("./pages/Settings"));
const AgentChat = lazy(() => import("./pages/AgentChat"));
const PolicyPage = lazy(() => import("./pages/Policy"));
const AuditPage = lazy(() => import("./pages/Audit"));
const CaseList = lazy(() => import("./pages/CaseList"));
const Memory = lazy(() => import("./pages/Memory"));
const Metrics = lazy(() => import("./pages/Metrics"));
const SourceHealth = lazy(() => import("./pages/SourceHealth"));
const Packs = lazy(() => import("./pages/Packs"));
const Help = lazy(() => import("./pages/Help"));
const Inbox = lazy(() => import("./pages/Inbox"));
const InvestigationMemo = lazy(() => import("./pages/drafts/InvestigationMemo"));

/**
 * Minimal Suspense fallback - matches the bg color of the route shell
 * so the brief loading flash is barely visible.
 */
function RouteFallback() {
  return (
    <div
      style={{
        height: "100%",
        width: "100%",
        background: "var(--color-bg)",
        color: "var(--color-ink-faint)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "Geist Mono, ui-monospace, monospace",
        fontSize: 12,
        letterSpacing: "0.16em",
        textTransform: "uppercase",
      }}
    >
      Loading…
    </div>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* Public marketing */}
          <Route path="/" element={<Landing />} />
          {/* Auth routes use /* so Clerk's internal routing - SSO
              callback, factor-two verification, OAuth account-link
              flows - can mount sub-paths under /login/* and /signup/*
              without our catch-all bouncing them to the landing page. */}
          <Route path="/login/*" element={<Login />} />
          <Route path="/signup/*" element={<Signup />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/changelog" element={<Changelog />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/dpa" element={<DPA />} />
          <Route path="/blog" element={<Blog />} />
          <Route
            path="/blog/tokens-are-the-new-salary"
            element={<BlogTokensAreTheNewSalary />}
          />

          {/* App shell */}
          <Route path="/app" element={<AppShell />}>
            {/* /app is the editorial Inbox (scannable triage view).
                /app/case/:id is the 3-column workspace for one case. */}
            <Route index element={<Inbox />} />
            <Route
              path="active"
              element={
                <CaseList
                  title="Active cases"
                  description="Manthan is on these right now or waiting on your nod."
                  statuses={["investigating", "awaiting_approval", "acting"]}
                  emptyHint="Nothing in flight. Inbox zero - Manthan is idle."
                />
              }
            />
            <Route
              path="done"
              element={
                <CaseList
                  title="Done"
                  description="Closed cases with full audit trails."
                  statuses={["resolved"]}
                  emptyHint="No resolved cases yet."
                />
              }
            />
            <Route
              path="escalated"
              element={
                <CaseList
                  title="Escalated"
                  description="Cases the agent handed back to a human - by policy, low confidence, or hard error."
                  statuses={["escalated", "errored"]}
                  emptyHint="Nothing escalated. Manthan is handling everything itself."
                />
              }
            />
            <Route path="approvals" element={<Approvals />} />
            <Route path="case/:id" element={<Workspace />} />
            <Route path="sources" element={<Sources />} />
            <Route path="sources/health" element={<SourceHealth />} />
            <Route path="packs/billing" element={<Packs pack="billing" />} />
            <Route path="packs/renewals" element={<Packs pack="renewals" />} />
            <Route path="chat" element={<AgentChat />} />
            <Route path="memory" element={<Memory />} />
            <Route path="memory/:customerRef" element={<Memory />} />
            <Route path="policy" element={<PolicyPage />} />
            <Route path="metrics" element={<Metrics />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="settings" element={<Settings />} />
            <Route path="help" element={<Help />} />

            {/* Investigation-phase canvas (live agent narrative). Only
                reachable via deep-link; production routes through
                /app/case/:id which dispatches based on status. */}
            <Route
              path="investigation-memo/:id"
              element={<InvestigationMemo />}
            />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
