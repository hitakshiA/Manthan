import { useAgentStore } from "@/stores/agent-store";
import { useRef, useEffect } from "react";
import { ActivityEvent } from "./ActivityEvent";
import { ManthanLogo } from "@/components/ManthanLogo";

export function ActivityFeed() {
  const events = useAgentStore((s) => s.events);
  const phase = useAgentStore((s) => s.phase);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  // Dynamic tab title
  useEffect(() => {
    const isWorking = phase !== "idle" && phase !== "done" && phase !== "error";
    document.title = isWorking ? "⏳ Analyzing… — Manthan" : phase === "done" ? "✓ Done — Manthan" : "Manthan";
    return () => { document.title = "Manthan"; };
  }, [phase]);

  if (events.length === 0 && phase === "idle") return null;

  const isWorking = phase !== "idle" && phase !== "done" && phase !== "error";

  return (
    <div className="flex flex-col gap-1 px-8 py-6">
      {/* Animated logo header when working */}
      {isWorking && (
        <div className="flex items-center gap-3 mb-4 animate-fade-up">
          <ManthanLogo size={24} animate className="text-accent" />
          <span className="text-sm font-medium text-text-secondary">Analyzing your data…</span>
        </div>
      )}

      {events.map((event, i) => (
        <ActivityEvent key={i} event={event} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
