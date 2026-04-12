import { ActivityBar } from "@/components/layout/ActivityBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { MainWorkspace } from "@/components/layout/MainWorkspace";
import { StatusBar } from "@/components/layout/StatusBar";
import { ErrorBoundary } from "@/components/layout/ErrorBoundary";

export default function App() {
  return (
    <ErrorBoundary>
      <div className="h-screen flex flex-col overflow-hidden">
        <div className="flex-1 flex min-h-0">
          <ActivityBar />
          <Sidebar />
          <MainWorkspace />
        </div>
        <StatusBar />
      </div>
    </ErrorBoundary>
  );
}
