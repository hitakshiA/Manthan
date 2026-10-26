import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  ExternalLink,
  FileText,
  Mail,
  MessageSquare,
  Send,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import { Card, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { cn } from "@/lib/cn";
import {
  caseTypeLabel,
  formatAge,
  formatAmount,
  getCase,
  triggerToSource,
  type ApiCase,
  type ApiFinding,
  type TriggerSurface,
} from "@/lib/api";

const TRIGGER_LABEL: Record<TriggerSurface, string> = {
  stripe_webhook: "Stripe webhook",
  inbound_email: "inbound email",
  slack_mention: "Slack mention",
  cron: "scheduled scan",
  web_new: "manual trigger",
  api: "API call",
};

const STATUS_TONE: Record<
  ApiCase["status"],
  { tone: "info" | "warning" | "accent" | "danger" | "neutral"; label: string }
> = {
  investigating: { tone: "info", label: "Investigating" },
  awaiting_approval: { tone: "warning", label: "Awaiting approval" },
  acting: { tone: "accent", label: "Executing" },
  resolved: { tone: "accent", label: "Resolved" },
  errored: { tone: "danger", label: "Errored" },
  escalated: { tone: "neutral", label: "Escalated" },
};

export default function CaseDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [caseData, setCaseData] = useState<ApiCase | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getCase(id)
      .then((c) => {
        if (!cancelled) setCaseData(c);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto space-y-5">
      <Header caseData={caseData} error={error} fallbackId={id} />
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-5">
        <div className="space-y-5">
          <CustomerSnapshot />
          <InvestigationTrace />
          <CitedBrief findings={caseData?.findings ?? null} loading={!caseData && !error} />
        </div>
        <aside className="space-y-5">
          <ProposedActions />
          <AuditCard />
        </aside>
      </div>
    </div>
  );
}

function Header({
  caseData,
  error,
  fallbackId,
}: {
  caseData: ApiCase | null;
  error: string | null;
  fallbackId: string;
}) {
  const title = caseData
    ? `${caseData.customer_ref ?? "-"} · ${caseTypeLabel(caseData.case_type).toLowerCase()} investigation`
    : "Loading case…";
  const status = caseData ? STATUS_TONE[caseData.status] : null;
  const shortId = caseData?.short_id ?? fallbackId;
  const amount = caseData?.amount_minor != null
    ? `${formatAmount(caseData.amount_minor, caseData.currency)} disputed`
    : "";
  const trigger = caseData
    ? `Triggered ${formatAge(caseData.created_at)} ago via ${TRIGGER_LABEL[caseData.trigger_surface]}`
    : "";

  return (
    <motion.header
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex items-start justify-between gap-4 flex-wrap"
    >
      <div className="space-y-2">
        <Link
          to="/app"
          className="inline-flex items-center gap-1.5 text-[12.5px] text-white/45 hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to inbox
        </Link>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl md:text-3xl font-medium tracking-tight">{title}</h1>
          {status && (
            <Badge tone={status.tone} dot>
              {status.label}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-3 text-[12.5px] text-white/45 font-mono">
          <span>{shortId}</span>
          {amount && (
            <>
              <span>·</span>
              <span>{amount}</span>
            </>
          )}
          {trigger && (
            <>
              <span>·</span>
              <span>{trigger}</span>
            </>
          )}
        </div>
        {error && (
          <div className="text-xs text-red-300/85 mt-2">API error: {error}</div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" leftIcon={<ThumbsDown className="h-3.5 w-3.5" />}>
          Escalate
        </Button>
        <Button
          variant="accent"
          size="sm"
          leftIcon={<CheckCircle2 className="h-3.5 w-3.5" />}
        >
          Approve all 3 actions
        </Button>
      </div>
    </motion.header>
  );
}

function CustomerSnapshot() {
  return (
    <Card>
      <CardBody>
        <div className="flex items-center justify-between mb-4">
          <div className="text-xs uppercase tracking-wider text-white/45">
            Customer snapshot
          </div>
          <Badge tone="info">Healthy</Badge>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
          <Stat label="MRR" value="$4,167" sub="Annual: $50K" />
          <Stat label="Customer since" value="Feb 2023" sub="2.3 yrs" />
          <Stat label="Health score" value="78 / 100" sub="↘ from 82" tone="warning" />
          <Stat label="Prior disputes" value="0" sub="First time" tone="accent" />
        </div>
      </CardBody>
    </Card>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "neutral" | "accent" | "warning";
}) {
  return (
    <div>
      <div className="text-xs text-white/40">{label}</div>
      <div
        className={cn(
          "mt-1 text-lg font-medium tracking-tight",
          tone === "warning" && "text-[#fbbf24]",
          tone === "accent" && "text-[#16d05e]",
        )}
      >
        {value}
      </div>
      <div className="text-[11px] text-white/40 mt-0.5">{sub}</div>
    </div>
  );
}

function InvestigationTrace() {
  return (
    <Card>
      <CardBody className="p-0">
        <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-medium">Investigation</h2>
            <Badge tone="neutral">11 tool calls · 4.2s</Badge>
          </div>
          <button className="text-xs text-white/45 hover:text-white inline-flex items-center gap-1">
            Replay
            <Sparkles className="h-3 w-3" />
          </button>
        </div>
        <ol className="px-5 py-4 space-y-4">
          <TraceStep
            done
            source="stripe"
            title="Pulled payment timeline"
            detail="3 successful charges Q4–Q1, first dispute, raised 4 min ago"
            tool="run_sql · stripe.charges + stripe.disputes"
          />
          <TraceStep
            done
            source="salesforce"
            title="Loaded account context"
            detail="$50K ARR, customer since Feb 2023, lifecycle: customer, owner: Maria Chen"
            tool="run_sql · salesforce.account + salesforce.opportunity"
          />
          <TraceStep
            done
            source="intercom"
            title="Reviewed support history"
            detail="Last ticket Jan 14: 'invoice amount too high' - closed as 'pricing question', 1 hr resolution"
            tool="run_sql · intercom.conversations"
          />
          <TraceStep
            done
            source="posthog"
            title="Pulled product usage signal"
            detail="Logged in 23 of last 30 days, 200+ events, core feature used daily - actively engaged"
            tool="run_sql · posthog.events"
          />
          <TraceStep
            done
            source="slack"
            title="Checked internal mentions"
            detail="CSM mentioned TechCorp in #cs-expansion 5 days ago - flagged for upsell convo"
            tool="run_sql · slack.messages"
          />
          <TraceStep
            done
            source="notion"
            title="Loaded refund policy runbook"
            detail="14-day refund window if <50% feature usage. This case: customer IS using features, ineligible per policy."
            tool="run_sql · notion.pages"
          />
          <TraceStep
            active
            title="Reasoning"
            detail="Engaged + healthy + recent unresolved pricing complaint. This dispute is likely retaliation, not fraud. Contesting probably loses + damages relationship. Recommend: proactive refund + CSM outreach for save."
            tool="claude-sonnet-4.5 · BYO key · 11.2K input · 482 output"
          />
        </ol>
      </CardBody>
    </Card>
  );
}

function TraceStep({
  done,
  active,
  source,
  title,
  detail,
  tool,
}: {
  done?: boolean;
  active?: boolean;
  source?: string;
  title: string;
  detail: string;
  tool: string;
}) {
  return (
    <li className="flex gap-3">
      <div
        className={cn(
          "shrink-0 inline-flex h-8 w-8 items-center justify-center rounded-lg mt-0.5",
          active
            ? "bg-[#16d05e]/15 text-[#16d05e] ring-1 ring-[#16d05e]/40"
            : "bg-white/[0.04] text-white/75",
        )}
      >
        {active ? (
          <Bot className="h-4 w-4" />
        ) : source ? (
          <SourceIcon id={source} size={14} tinted />
        ) : (
          <CheckCircle2 className="h-4 w-4" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] text-white font-medium">{title}</div>
        <div className="text-[12.5px] text-white/65 mt-0.5 leading-relaxed">
          {detail}
        </div>
        <div className="text-[11px] text-white/35 mt-1.5 font-mono">{tool}</div>
      </div>
      {done && !active && (
        <CheckCircle2 className="h-4 w-4 text-[#16d05e]/60 shrink-0 mt-1" />
      )}
    </li>
  );
}

function CitedBrief({
  findings,
  loading,
}: {
  findings: ApiFinding[] | null;
  loading: boolean;
}) {
  // If we have real findings from the backend, render them. Otherwise fall
  // back to the prototype narrative (which acts as a visual placeholder
  // until the investigate worker produces real findings against this case).
  const hasReal = findings && findings.length > 0;
  const totalCitations = (findings ?? []).reduce(
    (sum, f) => sum + (f.citations?.length ?? 0),
    0,
  );

  return (
    <Card>
      <CardBody>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Drafted brief · for #billing-ops</h2>
          <Badge tone={hasReal ? "accent" : "neutral"}>
            {loading ? "Loading…" : hasReal ? `Cited · ${totalCitations}` : "Prototype"}
          </Badge>
        </div>
        {hasReal ? (
          <div className="space-y-3 text-[13.5px] leading-relaxed text-white/85">
            {findings!.map((f) => (
              <p key={f.id}>
                <FindingText finding={f} />
              </p>
            ))}
          </div>
        ) : (
          <div className="space-y-3 text-[13.5px] leading-relaxed text-white/85">
            <p>
              <span className="font-medium text-white">TechCorp ($50K ARR)</span> disputed{" "}
              <Cite>$1,200</Cite> on their Q4 invoice. Customer is healthy:{" "}
              <Cite>23/30 days active</Cite>, no prior disputes,{" "}
              <Cite>health 78</Cite>.
            </p>
            <p>
              The dispute appears to be retaliation, not fraud - Alice flagged a
              pricing concern <Cite>Jan 14</Cite> that closed without
              resolution. Per policy this case is{" "}
              <Cite>ineligible for refund</Cite>, but the relationship value
              justifies a discretionary credit.
            </p>
            <p>
              <span className="font-medium text-white">Recommendation:</span>{" "}
              issue full refund + apology email + 1mo credit. Loop Maria (CSM)
              for a save call within 24h. Update health to{" "}
              <Cite>at_risk</Cite>.
            </p>
          </div>
        )}
        <div className="mt-4 pt-3 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-white/40">
          <span>
            {hasReal
              ? `${findings!.length} findings · ${totalCitations} citation${totalCitations === 1 ? "" : "s"} · every claim linked to source`
              : "6 citations · every claim linked to source"}
          </span>
          <button className="hover:text-white inline-flex items-center gap-1">
            View provenance
            <ExternalLink className="h-3 w-3" />
          </button>
        </div>
      </CardBody>
    </Card>
  );
}

function FindingText({ finding }: { finding: ApiFinding }) {
  // Render finding text followed by inline citation chips.
  return (
    <>
      <span>{finding.text}</span>
      {finding.citations?.length > 0 && (
        <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
          {finding.citations.map((c, i) => (
            <span
              key={i}
              title={`${c.source}.${c.table}${c.field ? `.${c.field}` : ""} · ${c.ref}`}
              className="inline-flex items-center gap-1 text-[10.5px] px-1.5 py-0.5 rounded
                bg-white/[0.06] text-white/70 border border-white/[0.08]
                hover:bg-white/[0.1] cursor-default"
            >
              <SourceIcon id={c.source} size={10} tinted />
              <span className="font-mono">{c.source}</span>
            </span>
          ))}
        </span>
      )}
    </>
  );
}

function Cite({ children }: { children: ReactNode }) {
  return (
    <button className="inline-flex items-baseline gap-0.5 px-1 -mx-0.5 rounded bg-[#16d05e]/10 text-[#1ee06b] font-medium hover:bg-[#16d05e]/20 transition-colors">
      {children}
    </button>
  );
}

function ProposedActions() {
  const actions = [
    {
      icon: <SourceIcon id="stripe" size={14} tinted />,
      title: "Issue refund · $1,200",
      detail: "Stripe · idempotency: case_4821_rf",
      gate: "HITL · $500+",
      tone: "warning" as const,
    },
    {
      icon: <Mail className="h-3.5 w-3.5 text-white/70" />,
      title: "Send apology + 1mo credit email",
      detail: "alice@techcorp.com · drafted",
      gate: "HITL · email",
      tone: "warning" as const,
    },
    {
      icon: <SourceIcon id="linear" size={14} tinted />,
      title: "Create CSM follow-up ticket",
      detail: "Assignee: Maria · Priority: High",
      gate: "Auto",
      tone: "accent" as const,
    },
    {
      icon: <SourceIcon id="hubspot" size={14} tinted />,
      title: "Update account health",
      detail: "78 → 45 · lifecycle: at_risk",
      gate: "Auto",
      tone: "accent" as const,
    },
    {
      icon: <SourceIcon id="slack" size={14} tinted />,
      title: "Post brief to #billing-ops",
      detail: "With audit link",
      gate: "Auto",
      tone: "accent" as const,
    },
  ];

  return (
    <Card>
      <CardBody className="p-0">
        <div className="px-5 py-4 border-b border-white/[0.06]">
          <h2 className="text-sm font-medium">Actions to take</h2>
          <p className="text-[11.5px] text-white/45 mt-0.5">
            2 need your nod · 3 auto-execute on approval
          </p>
        </div>
        <ul className="px-5 py-3 space-y-2.5">
          {actions.map((a, i) => (
            <li
              key={i}
              className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-white/[0.02] border border-white/[0.04]"
            >
              <div className="h-7 w-7 rounded-md bg-white/[0.04] inline-flex items-center justify-center shrink-0">
                {a.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[13px] text-white font-medium leading-tight">
                  {a.title}
                </div>
                <div className="text-[11px] text-white/45 truncate mt-0.5">
                  {a.detail}
                </div>
              </div>
              <Badge tone={a.tone} className="shrink-0">
                {a.gate}
              </Badge>
            </li>
          ))}
        </ul>
        <div className="p-5 pt-3 space-y-2">
          <Button
            variant="accent"
            className="w-full"
            leftIcon={<Send className="h-3.5 w-3.5" />}
          >
            Approve & execute
          </Button>
          <Button
            variant="secondary"
            className="w-full"
            leftIcon={<MessageSquare className="h-3.5 w-3.5" />}
          >
            Edit drafts
          </Button>
          <button className="w-full h-9 text-[12.5px] text-white/45 hover:text-white inline-flex items-center justify-center gap-1.5">
            <XCircle className="h-3.5 w-3.5" />
            Dismiss this case
          </button>
        </div>
      </CardBody>
    </Card>
  );
}

function AuditCard() {
  return (
    <Card>
      <CardBody>
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck className="h-4 w-4 text-[#16d05e]" />
          <h2 className="text-sm font-medium">Audit trail</h2>
        </div>
        <dl className="text-[12px] space-y-1.5">
          <Field label="Triggered by" value="stripe.charge.dispute.created" />
          <Field label="Webhook ID" value="evt_3PqL8c..." mono />
          <Field label="Model" value="claude-sonnet-4.5-20251001" mono />
          <Field label="Prompts" value="11.2K input / 482 output" />
          <Field label="SQL queries" value="6 · all DCD-validated" />
          <Field label="HITL gates" value="2 · per refund + email policy" />
          <Field label="AIBOM" value="CycloneDX-AI 1.6" />
        </dl>
        <button className="mt-4 w-full h-9 rounded-lg bg-white/[0.04] border border-white/10 text-[12.5px] text-white/75 hover:bg-white/[0.07] inline-flex items-center justify-center gap-1.5">
          <FileText className="h-3.5 w-3.5" />
          Download evidence pack
        </button>
      </CardBody>
    </Card>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-white/45">{label}</dt>
      <dd
        className={cn(
          "text-white/85 truncate text-right",
          mono && "font-mono text-[11.5px]",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
