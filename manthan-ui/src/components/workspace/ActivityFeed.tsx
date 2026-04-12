import { useAgentStore } from "@/stores/agent-store";
import { useRef, useEffect } from "react";
import { ActivityEvent } from "./ActivityEvent";

export function ActivityFeed() {
  const events = useAgentStore((s) => s.events);
  const phase = useAgentStore((s) => s.phase);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0 && phase === "idle") return null;

  return (
    <div className="flex flex-col gap-1 px-6 py-4">
      {events.map((event, i) => (
        <ActivityEvent key={i} event={event} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
