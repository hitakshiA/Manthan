import { ActivityBar } from "@/components/layout/ActivityBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { MainWorkspace } from "@/components/layout/MainWorkspace";
import { StatusBar } from "@/components/layout/StatusBar";
import { ErrorBoundary } from "@/components/layout/ErrorBoundary";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";

export default function App() {
  const hasContent = useAgentStore((s) => s.events.length > 0);
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);

  // Sidebar only shows when actively querying (dataset selected + events flowing)
  const showSidebar = hasContent && !!activeDatasetId;

  return (
    <ErrorBoundary>
      <div className="h-screen flex flex-col overflow-hidden">
        <div className="flex-1 flex min-h-0">
          {showSidebar && <ActivityBar />}
          {showSidebar && <Sidebar />}
          <MainWorkspace />
        </div>
        <StatusBar />
      </div>
    </ErrorBoundary>
  );
}
