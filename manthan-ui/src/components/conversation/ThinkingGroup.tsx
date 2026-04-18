import { useState } from "react";
import { ChevronRight, ChevronDown, Clock, Terminal, Check, X } from "lucide-react";
import type { ThinkingGroupBlock, ThinkingStep } from "@/types/conversation";
import { SqlResultBlock } from "./SqlResultBlock";
import { cn } from "@/lib/utils";

/**
 * Claude-style collapsible phase card.
 *
 * Collapsed default: one-line past-tense summary + right-chevron (">").
 * Expanding reveals a vertical timeline of steps — clock icon for the
 * agent's own reasoning, terminal icon for tool calls (with a "Script"
 * badge for Python/SQL). Long reasoning text folds behind a "Show more"
 * toggle. A `Done` marker closes the timeline.
 *
 * Script steps are click-to-expand — the code only renders when the
 * user opts in, keeping the scrollable stream light.
 */

const LONG_TEXT_CHARS = 240;
const CODE_PEEK_CHARS = 400;

function StepText({ step }: { step: ThinkingStep }) {
  const [open, setOpen] = useState(false);
  const raw =
    step.display_label ??
    (step.code
      ? step.tool === "run_python"
        ? "Ran analysis"
        : step.tool === "run_sql"
          ? "Pulled data"
          : step.text.split("\n")[0].slice(0, 80)
      : step.text);
  const isLong = raw.length > LONG_TEXT_CHARS;
  const shown = isLong && !open ? raw.slice(0, LONG_TEXT_CHARS) + "…" : raw;
  return (
    <>
      <span className={cn(
        "text-sm font-body leading-relaxed",
        step.kind === "tool_call" ? "text-text-secondary" : "text-text-tertiary",
      )}>
        {shown}
      </span>
      {isLong && (
        <button
          onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
          className="block text-[12px] text-text-faint hover:text-text-secondary mt-1 font-body"
        >
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </>
  );
}

function ScriptBlock({ step }: { step: ThinkingStep }) {
  const [open, setOpen] = useState(false);
  if (!step.code) return null;
  const long = step.code.length > CODE_PEEK_CHARS;
  const peek = long ? step.code.slice(0, CODE_PEEK_CHARS) + "\n…" : step.code;
  const displayed = open ? step.code : peek;
  return (
    <div className="mt-2">
      <div className="rounded-md bg-surface-sunken border border-border/60 overflow-hidden">
        <div className="px-3 py-1.5 border-b border-border/40 flex items-center justify-between text-[10px] text-text-faint font-mono uppercase tracking-wider">
          <span>{step.tool === "run_python" ? "python" : step.tool === "run_sql" ? "sql" : "script"}</span>
          {long && (
            <button
              onClick={() => setOpen(!open)}
              className="text-text-faint hover:text-text-secondary font-body normal-case text-[11px]"
            >
              {open ? "Show less" : `Show full (${step.code.length} chars)`}
            </button>
          )}
        </div>
        <pre className="px-3 py-2 text-[11px] font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto">
          {displayed}
        </pre>
      </div>
    </div>
  );
}

function StepNode({ step, isLast }: { step: ThinkingStep; isLast: boolean }) {
  // Icon: clock = reasoning, terminal = tool call, check/x = tool result
  const icon =
    step.kind === "reasoning" ? (
      <Clock size={13} className="text-text-faint" />
    ) : step.kind === "tool_call" ? (
      <Terminal size={13} className="text-text-secondary" />
    ) : step.success !== false ? (
      <Check size={13} className="text-success" />
    ) : (
      <X size={13} className="text-error" />
    );

  return (
    <div className="relative flex gap-3">
      {/* Vertical connector line */}
      {!isLast && (
        <div className="absolute left-[6px] top-[22px] bottom-0 w-px bg-border-strong/70" />
      )}

      {/* Icon well — sits on top of the connector */}
      <div className="relative z-10 mt-1 shrink-0 bg-surface-0 rounded-full w-[13px] h-[13px] flex items-center justify-center">
        {icon}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-3">
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <StepText step={step} />
          </div>
          {step.badge && (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-surface-sunken text-text-faint shrink-0 mt-0.5">
              {step.badge}
            </span>
          )}
          {step.elapsed_ms != null && (
            <span className="text-[10px] text-text-faint tabular-nums shrink-0 mt-1">
              {step.elapsed_ms < 1000
                ? `${Math.round(step.elapsed_ms)}ms`
                : `${(step.elapsed_ms / 1000).toFixed(1)}s`}
            </span>
          )}
        </div>

        {/* Code reveal for SQL/Python — click-to-expand */}
        {step.code && <ScriptBlock step={step} />}

        {/* SQL result — only rendered here in the expanded view */}
        {step.table && step.table.columns.length > 0 && (
          <div className="mt-2">
            <SqlResultBlock
              result={{
                type: "sql_result",
                tool_call_id: "",
                query: step.table.query,
                columns: step.table.columns,
                rows: step.table.rows,
                row_count: step.table.row_count,
                truncated: step.table.truncated,
                elapsed_ms: step.table.elapsed_ms,
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

interface ThinkingGroupProps {
  group: ThinkingGroupBlock;
  /** Render with a spinner + "live" styling for an in-progress phase.
   *  Defaults expanded when live so the exec sees work as it happens. */
  live?: boolean;
}

export function ThinkingGroup({ group, live = false }: ThinkingGroupProps) {
  const [expanded, setExpanded] = useState(live);

  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <div className="group">
      {/* Collapsed / Expand header — Claude-style single line + chevron */}
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="flex items-center gap-1.5 w-full text-left text-[15px] text-text-secondary hover:text-text-primary font-body transition-colors py-1 group/header"
      >
        {live && (
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse shrink-0"
            aria-hidden
          />
        )}
        <span className="truncate">{group.summary}</span>
        <Chevron
          size={14}
          className="text-text-faint shrink-0 group-hover/header:text-text-secondary transition-colors"
        />
      </button>

      {/* Expanded timeline */}
      {expanded && (
        <div className="mt-3 ml-1.5 pl-1">
          {group.steps.map((step, i) => (
            <StepNode
              key={i}
              step={step}
              isLast={i === group.steps.length - 1}
            />
          ))}
          {!live && (
            <div className="flex items-center gap-2 text-xs text-text-faint font-body pt-1">
              <Check size={12} className="text-text-faint" />
              <span>Done</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
