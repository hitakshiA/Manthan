import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Onboarding from "./pages/Onboarding";
import Changelog from "./pages/Changelog";
import Contact from "./pages/Contact";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import DPA from "./pages/DPA";
import { AppShell } from "./components/app/AppShell";
import Workspace from "./pages/Workspace";
import Sources from "./pages/Sources";
import Approvals from "./pages/Approvals";
import Settings from "./pages/Settings";
import AgentChat from "./pages/AgentChat";
import PolicyPage from "./pages/Policy";
import AuditPage from "./pages/Audit";
import { Placeholder } from "./pages/Placeholder";
import CaseList from "./pages/CaseList";
import Memory from "./pages/Memory";
import Metrics from "./pages/Metrics";
import SourceHealth from "./pages/SourceHealth";
import Packs from "./pages/Packs";
import Help from "./pages/Help";
import Inbox from "./pages/Inbox";
import WorkspaceMemo from "./pages/drafts/WorkspaceMemo";
import DraftInbox from "./pages/drafts/DraftInbox";
import DraftAudit from "./pages/drafts/DraftAudit";
import DraftPolicies from "./pages/drafts/DraftPolicies";
import DraftSources from "./pages/drafts/DraftSources";
import InvestigationMemo from "./pages/drafts/InvestigationMemo";

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public marketing */}
        <Route path="/" element={<Landing />} />
        {/* Auth routes use /* so Clerk's internal routing - SSO
            callback, factor-two verification, OAuth account-link
            flows - can mount sub-paths under /login/* and /signup/*
            without our catch-all bouncing them to the landing page.
            (Previously: clicking Google on /signup with an existing
            account redirected back to /signup/sso-callback which
            didn't match exact-only routes, fell through to *, and
            sent the visitor to /.) */}
        <Route path="/login/*" element={<Login />} />
        <Route path="/signup/*" element={<Signup />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/changelog" element={<Changelog />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/dpa" element={<DPA />} />

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

          {/* Throwaway dashboard-redesign prototypes - editorial-memo
              vocabulary, pulled from the landing's BriefCanvas + the
              AuditVisual / CrossSourceVisual patterns. */}
          <Route path="workspace-memo" element={<WorkspaceMemo />} />
          <Route path="inbox-memo" element={<DraftInbox />} />
          <Route path="audit-memo" element={<DraftAudit />} />
          <Route path="policies-memo" element={<DraftPolicies />} />
          <Route path="sources-memo" element={<DraftSources />} />
          <Route path="investigation-memo/:id" element={<InvestigationMemo />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
