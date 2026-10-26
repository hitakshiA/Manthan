import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Sparkles,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { Card, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { cn } from "@/lib/cn";
import {
  caseTypeLabel,
  formatAge,
  formatAmount,
  listCases,
  triggerToSource,
  type ApiCase,
  type CaseStatus,
} from "@/lib/api";

/** ── Dashboard's local view shape ─────────────────────────────────── */
interface Case {
  id: string;                  // route id (uuid)
  shortId: string;             // "CASE-4821"
  customer: string;
  type: string;
  source: string;
  status: "investigating" | "awaiting_approval" | "executing" | "drafted";
  amount?: string;
  age: string;
  pack: string;
}

// Map a status from the API to the four-bucket display status the UI uses.
function mapStatus(s: CaseStatus): Case["status"] {
  if (s === "acting") return "executing";
  if (s === "resolved" || s === "errored" || s === "escalated") return "investigating";
  return s;
}

function fromApi(c: ApiCase): Case {
  return {
    id: c.id,
    shortId: c.short_id,
    customer: c.customer_ref ?? "-",
    type: caseTypeLabel(c.case_type),
    source: triggerToSource(c.trigger_surface),
    status: mapStatus(c.status),
    amount: formatAmount(c.amount_minor, c.currency),
    age: formatAge(c.created_at),
    pack: "Billing Ops",
  };
}

interface ActivityEvent {
  time: string;
  source: string;
  message: string;
  variant: "auto" | "approved" | "investigating" | "escalated";
  amount?: string;
  customer: string;
}

const ACTIVITY: ActivityEvent[] = [
  {
    time: "2m",
    source: "stripe",
    message: "Issued refund · ",
    customer: "AcmeInc",
    amount: "$1,200",
    variant: "approved",
  },
  {
    time: "5m",
    source: "gmail",
    message: "Drafted apology email · ",
    customer: "TechCorp",
    variant: "investigating",
  },
  {
    time: "8m",
    source: "slack",
    message: "Posted cited brief to ",
    customer: "#billing-ops",
    variant: "auto",
  },
  {
    time: "12m",
    source: "hubspot",
    message: "Updated lifecycle to at_risk · ",
    customer: "Loop & Co",
    variant: "auto",
  },
  {
    time: "16m",
    source: "linear",
    message: "Opened CSM ticket · ",
    customer: "Mira Labs",
    variant: "auto",
  },
  {
    time: "23m",
    source: "stripe",
    message: "Retry succeeded · ",
    customer: "StartupY",
    amount: "$840",
    variant: "auto",
  },
  {
    time: "31m",
    source: "salesforce",
    message: "Added note to opportunity · ",
    customer: "Hyperion",
    variant: "auto",
  },
  {
    time: "44m",
    source: "zendesk",
    message: "Closed ticket with resolution · ",
    customer: "Cobalt Studio",
    variant: "approved",
  },
  {
    time: "1h",
    source: "intercom",
    message: "Escalated to human · ",
    customer: "FrostByte",
    variant: "escalated",
  },
];

export default function Dashboard() {
  const [cases, setCases] = useState<Case[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCases({ limit: 50 })
      .then((r) => {
        if (!cancelled) setCases(r.cases.map(fromApi));
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="px-6 py-6 max-w-7xl mx-auto space-y-6">
      <PageHeader />
      <MetricsRow />
      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-5">
        <ActiveCases cases={cases ?? []} loading={cases === null} error={error} />
        <ActivityFeed events={ACTIVITY} />
      </div>
    </div>
  );
}

function PageHeader() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex items-start justify-between gap-4 flex-wrap"
    >
      <div>
        <h1 className="text-2xl md:text-3xl font-medium tracking-tight">
          Good afternoon, Hitakshi.
        </h1>
        <p className="mt-1.5 text-sm text-white/55">
          Manthan handled <span className="text-white">31 cases</span> overnight.
          You have <span className="text-[#fbbf24]">3 awaiting approval</span>.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Link to="/app/active">
          <button className="inline-flex items-center gap-2 h-9 px-3.5 rounded-full bg-white/[0.04] border border-white/10 hover:bg-white/[0.07] text-sm transition-colors">
            View all active
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </Link>
      </div>
    </motion.div>
  );
}

function MetricsRow() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.05 }}
      className="grid grid-cols-2 md:grid-cols-4 gap-3"
    >
      <Metric
        label="Recovered today"
        value="$12,340"
        delta="+18%"
        trend="up"
        accent
      />
      <Metric
        label="Cases resolved"
        value="47"
        delta="+12"
        trend="up"
      />
      <Metric
        label="Avg MTTR"
        value="42s"
        delta="-31%"
        trend="up"
      />
      <Metric
        label="Awaiting human"
        value="3"
        delta="–"
        trend="flat"
      />
    </motion.div>
  );
}

function Metric({
  label,
  value,
  delta,
  trend,
  accent,
}: {
  label: string;
  value: string;
  delta: string;
  trend: "up" | "down" | "flat";
  accent?: boolean;
}) {
  return (
    <Card hover>
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs uppercase tracking-wider text-white/40">
            {label}
          </span>
          <span
            className={cn(
              "inline-flex items-center gap-1 text-[10.5px] font-medium px-1.5 py-0.5 rounded",
              trend === "up" && "bg-[#16d05e]/10 text-[#1ee06b]",
              trend === "down" && "bg-[#ef4444]/10 text-[#f87171]",
              trend === "flat" && "bg-white/[0.04] text-white/40",
            )}
          >
            {trend === "up" && <TrendingUp className="h-3 w-3" />}
            {trend === "down" && <TrendingDown className="h-3 w-3" />}
            {delta}
          </span>
        </div>
        <div
          className={cn(
            "text-3xl font-medium tracking-tight",
            accent && "text-[#16d05e]",
          )}
        >
          {value}
        </div>
        <Sparkline trend={trend} />
      </CardBody>
    </Card>
  );
}

function Sparkline({ trend }: { trend: "up" | "down" | "flat" }) {
  const color =
    trend === "up" ? "#16d05e" : trend === "down" ? "#ef4444" : "rgba(255,255,255,0.3)";
  const path =
    trend === "up"
      ? "M0 28 L12 24 L24 20 L36 22 L48 16 L60 14 L72 18 L84 10 L96 6"
      : trend === "down"
        ? "M0 8 L12 10 L24 16 L36 14 L48 20 L60 22 L72 26 L84 24 L96 30"
        : "M0 18 L12 16 L24 20 L36 17 L48 19 L60 18 L72 20 L84 16 L96 18";
  return (
    <svg
      viewBox="0 0 96 36"
      className="w-full h-8"
      fill="none"
      strokeLinecap="round"
    >
      <path d={path} stroke={color} strokeWidth="1.5" opacity="0.9" />
      <path
        d={`${path} L96 36 L0 36 Z`}
        fill={color}
        opacity="0.08"
      />
    </svg>
  );
}

function ActiveCases({
  cases,
  loading,
  error,
}: {
  cases: Case[];
  loading: boolean;
  error: string | null;
}) {
  return (
    <Card>
      <CardBody className="p-0">
        <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-medium">Active cases</h2>
            <Badge tone="live" dot>
              {loading ? "loading" : `${cases.length} in flight`}
            </Badge>
          </div>
          <div className="flex items-center gap-1.5">
            <button className="h-7 px-2.5 text-xs rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/65">
              All
            </button>
            <button className="h-7 px-2.5 text-xs rounded-md text-white/45 hover:text-white">
              Awaiting
            </button>
            <button className="h-7 px-2.5 text-xs rounded-md text-white/45 hover:text-white">
              Mine
            </button>
          </div>
        </div>
        {error && (
          <div className="px-5 py-4 text-sm text-red-300/85">
            API error: {error}
          </div>
        )}
        {!error && loading && (
          <div className="px-5 py-10 text-sm text-white/40">Loading cases…</div>
        )}
        {!error && !loading && cases.length === 0 && (
          <div className="px-5 py-10 text-sm text-white/40">
            No active cases. Trigger one via Stripe webhook, the Slack bot, or
            <Link to="/app/new" className="text-white/70 hover:text-white"> + New case</Link>.
          </div>
        )}
        <ul className="divide-y divide-white/[0.04]">
          {cases.map((c) => (
            <CaseRow key={c.id} c={c} />
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

function CaseRow({ c }: { c: Case }) {
  const statusMap = {
    investigating: { tone: "info" as const, label: "Investigating" },
    awaiting_approval: { tone: "warning" as const, label: "Approve" },
    executing: { tone: "accent" as const, label: "Executing" },
    drafted: { tone: "info" as const, label: "Drafted" },
  };
  const s = statusMap[c.status];

  return (
    <li>
      <Link
        to={`/app/case/${c.id}`}
        className="flex items-center gap-4 px-5 py-3.5 hover:bg-white/[0.02] transition-colors group"
      >
        <div className="h-9 w-9 rounded-lg bg-white/[0.04] inline-flex items-center justify-center shrink-0">
          <SourceIcon id={c.source} size={16} tinted />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">
              {c.customer}
            </span>
            {c.amount && (
              <span className="text-xs text-white/40 font-mono">
                {c.amount}
              </span>
            )}
          </div>
          <div className="text-[12.5px] text-white/55 truncate mt-0.5">
            {c.type}
          </div>
        </div>
        <div className="hidden md:flex items-center gap-2 shrink-0">
          <Badge tone={s.tone} dot={c.status === "investigating" || c.status === "executing"}>
            {s.label}
          </Badge>
          <span className="text-[11px] text-white/35 font-mono w-10 text-right">
            {c.age}
          </span>
          <ArrowRight className="h-3.5 w-3.5 text-white/20 group-hover:text-white/60 transition-colors" />
        </div>
      </Link>
    </li>
  );
}

function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <Card>
      <CardBody className="p-0">
        <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-medium">Recent activity</h2>
            <Badge tone="neutral">Last hour</Badge>
          </div>
          <button className="text-xs text-white/45 hover:text-white inline-flex items-center gap-1">
            View all
            <ArrowUpRight className="h-3 w-3" />
          </button>
        </div>
        <ul className="divide-y divide-white/[0.04] max-h-[640px] overflow-y-auto">
          {events.map((e, i) => (
            <ActivityRow key={i} e={e} />
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

function ActivityRow({ e }: { e: ActivityEvent }) {
  const variantIcons = {
    auto: <Sparkles className="h-3 w-3 text-white/55" />,
    approved: <CheckCircle2 className="h-3 w-3 text-[#16d05e]" />,
    investigating: <Clock className="h-3 w-3 text-[#6db1ff]" />,
    escalated: <XCircle className="h-3 w-3 text-[#fbbf24]" />,
  };
  return (
    <li className="px-5 py-3 flex items-start gap-3 hover:bg-white/[0.015] transition-colors">
      <div className="h-7 w-7 rounded-md bg-white/[0.04] inline-flex items-center justify-center shrink-0 mt-0.5">
        <SourceIcon id={e.source} size={13} tinted />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] text-white/85">
          {e.message}
          <span className="text-white font-medium">{e.customer}</span>
          {e.amount && (
            <span className="text-white/40 font-mono"> · {e.amount}</span>
          )}
        </div>
        <div className="text-[11px] text-white/35 mt-0.5 flex items-center gap-1.5">
          {variantIcons[e.variant]}
          <span className="capitalize">{e.variant.replace("_", " ")}</span>
          <span>·</span>
          <span>{e.time} ago</span>
        </div>
      </div>
    </li>
  );
}
