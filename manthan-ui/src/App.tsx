import { AnimatePresence } from "motion/react";
import { Sidebar } from "@/components/layout/Sidebar";
import { MainWorkspace } from "@/components/layout/MainWorkspace";
import { StatusBar } from "@/components/layout/StatusBar";
import { ErrorBoundary } from "@/components/layout/ErrorBoundary";
import { CalculationDrawer } from "@/components/audit/CalculationDrawer";
import { SourcePicker } from "@/components/datasets/SourcePicker";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useUIStore } from "@/stores/ui-store";

export default function App() {
  const hasContent = useAgentStore((s) => s.events.length > 0);
  const artifactFullscreen = useUIStore((s) => s.artifactFullscreen);
  const analyzeMode = useUIStore((s) => s.analyzeMode);
  const sourcePickerOpen = useUIStore((s) => s.sourcePickerOpen);
  const setSourcePickerOpen = useUIStore((s) => s.setSourcePickerOpen);
  // Once any dataset is selected (or the user hit Start Analyzing, or
  // a conversation has started) we pin the sidebar open. The only
  // state that leaves the sidebar hidden is the first-run landing
  // page where there's nothing to navigate back to yet.
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const showSidebar =
    (hasContent || analyzeMode || !!activeDatasetId) && !artifactFullscreen;

  return (
    <ErrorBoundary>
      <div className="h-screen flex flex-col overflow-hidden">
        <div className="flex-1 flex min-h-0">
          <AnimatePresence initial={false}>
            {showSidebar && <Sidebar key="sidebar" />}
          </AnimatePresence>
          <MainWorkspace />
        </div>
        {showSidebar && <StatusBar />}
      </div>
      {/* Phase 3 audit drawer — opens when a numeric claim is clicked
          anywhere in the conversation stream. */}
      <CalculationDrawer />
      {/* One source picker instance for the whole app. Opened from
          the landing page hero, the dataset explorer, and the
          sidebar Upload rail button — all through the UI store. */}
      {sourcePickerOpen && <SourcePicker onClose={() => setSourcePickerOpen(false)} />}
    </ErrorBoundary>
  );
}
