import { useUIStore } from "@/stores/ui-store";
import { useSessionStore } from "@/stores/session-store";
import { useAgentStore } from "@/stores/agent-store";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import { Home, Database, Plus, Upload } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

const SIDEBAR_WIDTH = 56;

export function Sidebar() {
  const setAnalyzeMode = useUIStore((s) => s.setAnalyzeMode);
  const setSourcePickerOpen = useUIStore((s) => s.setSourcePickerOpen);
  const setLandingView = useUIStore((s) => s.setLandingView);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const resetAgent = useAgentStore((s) => s.reset);
  const hasContent = useAgentStore((s) => s.events.length > 0);
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);

  const canNewAnalysis = hasContent || !!activeDatasetId;

  // Home and Datasets both clear the conversation + active dataset
  // + analyze mode, but they route to different views: Home goes to
  // the hero landing, Datasets opens the full lister.
  const goHome = () => {
    resetAgent();
    setAnalyzeMode(false);
    setActiveDataset(null);
    setLandingView("home");
  };
  const browseDatasets = () => {
    resetAgent();
    setAnalyzeMode(false);
    setActiveDataset(null);
    setLandingView("explore");
  };
  const newAnalysis = () => { resetAgent(); setAnalyzeMode(true); };
  // Opens the same Files/Cloud/Database/SaaS modal that the landing
  // page's "Connect warehouse" button uses. Single source picker
  // lifted into the UI store so sidebar + main workspace never race.
  const openSourcePicker = () => setSourcePickerOpen(true);

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: SIDEBAR_WIDTH, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ type: "spring", stiffness: 420, damping: 40, mass: 0.6 }}
      className="shrink-0 overflow-hidden border-r border-border bg-surface-1 flex flex-col h-full"
    >
      <div
        className="flex flex-col h-full shrink-0"
        style={{ width: SIDEBAR_WIDTH }}
      >
        <RailButton icon={Home} label="Home" onClick={goHome} />
        <RailButton icon={Database} label="Datasets" onClick={browseDatasets} />
        <RailButton
          icon={Plus}
          label="New chat"
          onClick={newAnalysis}
          disabled={!canNewAnalysis}
          accent
        />
        <RailButton icon={Upload} label="Upload" onClick={openSourcePicker} />
      </div>
    </motion.aside>
  );
}

function RailButton({
  icon: Icon,
  label,
  onClick,
  accent,
  disabled,
}: {
  icon: ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: ReactNode;
  onClick: () => void;
  accent?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={typeof label === "string" ? label : undefined}
      className={cn(
        "group relative flex-1 w-full flex flex-col items-center justify-center gap-1.5",
        "border-b border-border last:border-b-0 transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-inset",
        disabled && "opacity-40 cursor-not-allowed",
        !disabled && (accent
          ? "text-accent hover:bg-accent-soft"
          : "text-text-faint hover:text-text-primary hover:bg-surface-raised"),
      )}
    >
      <Icon
        size={18}
        strokeWidth={accent ? 2.25 : 1.75}
        className={cn("transition-transform", !disabled && "group-hover:scale-110")}
      />
      <span className="text-[10px] font-medium tracking-wide">
        {label}
      </span>
    </button>
  );
}
