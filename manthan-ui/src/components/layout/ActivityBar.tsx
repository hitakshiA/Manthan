import { Database, MessageSquareText, Brain, Settings } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

const items = [
  { id: "datasets" as const, icon: Database, label: "Datasets" },
  { id: "memory" as const, icon: Brain, label: "Memory" },
  { id: "history" as const, icon: MessageSquareText, label: "History" },
] as const;

export function ActivityBar() {
  const { sidebarView, setSidebarView, toggleSidebar, sidebarOpen } = useUIStore();

  return (
    <nav className="flex flex-col items-center w-12 shrink-0 border-r border-border bg-surface-1 py-3 gap-1">
      {items.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          onClick={() => {
            if (sidebarView === id && sidebarOpen) toggleSidebar();
            else setSidebarView(id);
          }}
          title={label}
          className={cn(
            "w-9 h-9 flex items-center justify-center rounded-md transition-colors duration-150",
            sidebarView === id && sidebarOpen
              ? "bg-accent-soft text-accent"
              : "text-text-tertiary hover:text-text-secondary hover:bg-surface-2",
          )}
        >
          <Icon size={18} strokeWidth={1.8} />
        </button>
      ))}
      <div className="mt-auto">
        <button
          title="Settings"
          className="w-9 h-9 flex items-center justify-center rounded-md text-text-tertiary hover:text-text-secondary hover:bg-surface-2 transition-colors duration-150"
        >
          <Settings size={18} strokeWidth={1.8} />
        </button>
      </div>
    </nav>
  );
}
