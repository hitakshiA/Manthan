import { Database, Brain, MessageSquareText, Settings } from "lucide-react";
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
    <nav
      aria-label="Main navigation"
      className="flex flex-col items-center w-[52px] shrink-0 bg-surface-1 border-r border-border py-3 gap-1"
    >
      {items.map(({ id, icon: Icon, label }) => {
        const isActive = sidebarView === id && sidebarOpen;
        return (
          <button
            key={id}
            onClick={() => {
              if (isActive) toggleSidebar();
              else setSidebarView(id);
            }}
            aria-label={label}
            aria-pressed={isActive}
            className={cn(
              "w-9 h-9 flex items-center justify-center rounded-lg transition-all duration-150",
              isActive
                ? "bg-accent text-accent-text shadow-xs"
                : "text-text-faint hover:text-text-secondary hover:bg-surface-raised",
            )}
          >
            <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
          </button>
        );
      })}
      <div className="mt-auto">
        <button
          aria-label="Settings"
          className="w-9 h-9 flex items-center justify-center rounded-lg text-text-faint hover:text-text-secondary hover:bg-surface-raised transition-all duration-150"
        >
          <Settings size={17} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}
