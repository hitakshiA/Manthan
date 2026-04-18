import { AnimatePresence } from "motion/react";
import { Sidebar } from "@/components/layout/Sidebar";
import { MainWorkspace } from "@/components/layout/MainWorkspace";
import { StatusBar } from "@/components/layout/StatusBar";
import { ErrorBoundary } from "@/components/layout/ErrorBoundary";
import { CalculationDrawer } from "@/components/audit/CalculationDrawer";
import { SourcePicker } from "@/components/datasets/SourcePicker";
import { useAgentStore } from "@/stores/agent-store";
import { useUIStore } from "@/stores/ui-store";

export default function App() {
  const hasContent = useAgentStore((s) => s.events.length > 0);
  const artifactFullscreen = useUIStore((s) => s.artifactFullscreen);
  const analyzeMode = useUIStore((s) => s.analyzeMode);
  const sourcePickerOpen = useUIStore((s) => s.sourcePickerOpen);
  const setSourcePickerOpen = useUIStore((s) => s.setSourcePickerOpen);
  // Sidebar is a chat-space affordance — it appears once the user has
  // committed to a conversation (Start Analyzing pressed, or events
  // streaming). Dataset lister + dataset profile stay unframed so the
  // semantic contract reads cleanly, and the landing page stays clean.
  const showSidebar =
    (hasContent || analyzeMode) && !artifactFullscreen;

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
