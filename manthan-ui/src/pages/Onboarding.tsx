import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { SOURCES, CATEGORY_LABELS } from "@/lib/sources";
import type { SourceCategory } from "@/lib/sources";
import { cn } from "@/lib/cn";

/** A list of (category, primary source) tuples for the v1 connect flow. */
const ONBOARDING_CATEGORIES: SourceCategory[] = [
  "payments",
  "crm",
  "support",
  "comms",
  "docs",
  "identity",
];

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [connected, setConnected] = useState<Record<string, string | null>>({});

  // Step 0 = workspace name, Step 1 = connect sources, Step 2 = policy
  return (
    <AuthShell
      heading="One AI worker."
      description="Pick a primary tool per category. You can change or add more later."
      activeStep={Math.max(0, step + 1)}
      steps={[
        { label: "Account created" },
        { label: "Name your workspace" },
        { label: "Connect your stack" },
        { label: "Set policies + go live" },
      ]}
    >
      {step === 0 && <WorkspaceStep onNext={() => setStep(1)} />}
      {step === 1 && (
        <ConnectStep
          connected={connected}
          setConnected={setConnected}
          onNext={() => setStep(2)}
        />
      )}
      {step === 2 && <PolicyStep onLaunch={() => navigate("/app")} />}
    </AuthShell>
  );
}

function WorkspaceStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-7">
      <header>
        <h1 className="text-3xl font-medium tracking-tight">
          Name your workspace
        </h1>
        <p className="mt-1.5 text-sm text-white/45">
          Each workspace is isolated - separate connections, policies, audit
          log.
        </p>
      </header>

      <div className="space-y-4">
        <label className="block">
          <div className="text-sm font-medium mb-1.5">Workspace name</div>
          <input
            placeholder="Caldera"
            className="w-full h-12 px-4 rounded-xl bg-white/[0.04] border border-white/10 text-white placeholder:text-white/30 focus:bg-white/[0.06] focus:border-white/20 focus:outline-none"
          />
          <div className="text-[11.5px] text-white/40 mt-1.5">
            We'll use this in URLs and audit attribution.
          </div>
        </label>

        <label className="block">
          <div className="text-sm font-medium mb-1.5">Region</div>
          <select className="w-full h-12 px-4 rounded-xl bg-white/[0.04] border border-white/10 text-white focus:outline-none">
            <option>US East - N. Virginia</option>
            <option>US West - Oregon</option>
            <option>EU - Frankfurt</option>
            <option>APAC - Singapore</option>
          </select>
          <div className="text-[11.5px] text-white/40 mt-1.5">
            All your customer data + audit log stays in this region. EU AI Act
            ready.
          </div>
        </label>
      </div>

      <Button
        variant="primary"
        size="lg"
        className="w-full"
        onClick={onNext}
        rightIcon={<ArrowRight className="h-4 w-4" />}
      >
        Continue
      </Button>
    </div>
  );
}

function ConnectStep({
  connected,
  setConnected,
  onNext,
}: {
  connected: Record<string, string | null>;
  setConnected: (v: Record<string, string | null>) => void;
  onNext: () => void;
}) {
  const all = ONBOARDING_CATEGORIES;
  const connectedCount = all.filter((c) => connected[c]).length;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-medium tracking-tight">
          Connect your stack
        </h1>
        <p className="mt-1.5 text-sm text-white/45">
          Pick the primary tool for each category. OAuth handles the rest.
        </p>
      </header>

      <div className="space-y-2.5">
        {all.map((cat) => (
          <CategoryRow
            key={cat}
            category={cat}
            selectedId={connected[cat]}
            onSelect={(id) =>
              setConnected({ ...connected, [cat]: id ?? null })
            }
          />
        ))}
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-white/[0.06]">
        <span className="text-xs text-white/40">
          {connectedCount} of {all.length} connected
        </span>
        <Button
          variant={connectedCount >= 3 ? "accent" : "secondary"}
          size="md"
          onClick={onNext}
          rightIcon={<ArrowRight className="h-4 w-4" />}
          disabled={connectedCount < 1}
        >
          {connectedCount >= 3 ? "Continue" : "I'll add more later"}
        </Button>
      </div>
    </div>
  );
}

function CategoryRow({
  category,
  selectedId,
  onSelect,
}: {
  category: SourceCategory;
  selectedId: string | null | undefined;
  onSelect: (id: string | null) => void;
}) {
  const sources = SOURCES.filter((s) => s.category === category);
  const selectedSource = selectedId
    ? sources.find((s) => s.id === selectedId)
    : undefined;

  return (
    <div
      className={cn(
        "card-surface p-3.5 transition-all",
        selectedSource &&
          "ring-1 ring-[#16d05e]/30 bg-[#16d05e]/[0.03]",
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-white/45">
            {CATEGORY_LABELS[category]}
          </span>
          {selectedSource && (
            <CheckCircle2 className="h-3.5 w-3.5 text-[#16d05e]" />
          )}
        </div>
        {selectedSource && (
          <button
            onClick={() => onSelect(null)}
            className="text-[11px] text-white/40 hover:text-white"
          >
            Change
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(selectedId === s.id ? null : s.id)}
            className={cn(
              "inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-[12.5px] transition-all border",
              selectedId === s.id
                ? "bg-[#16d05e] text-[#00120a] border-[#16d05e] font-medium"
                : "bg-white/[0.03] text-white/75 border-white/10 hover:bg-white/[0.07]",
            )}
          >
            <SourceIcon id={s.id} size={14} tinted={selectedId !== s.id} />
            <span>{s.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function PolicyStep({ onLaunch }: { onLaunch: () => void }) {
  return (
    <div className="space-y-7">
      <header>
        <h1 className="text-3xl font-medium tracking-tight">
          Set your policy
        </h1>
        <p className="mt-1.5 text-sm text-white/45">
          Defaults that follow industry norms. You can tune anything from your
          dashboard later.
        </p>
      </header>

      <div className="space-y-3.5">
        <PolicyRow
          label="Auto-issue refund under"
          value="$50"
          description="Anything above goes to one-click approval in Slack."
        />
        <PolicyRow
          label="One-approver refunds up to"
          value="$500"
          description="Above this, two-person approval required."
        />
        <PolicyRow
          label="Customer emails"
          value="Always reviewed"
          description="Manthan drafts. You approve before send."
        />
        <PolicyRow
          label="Escalation channel"
          value="#billing-ops"
          description="Where cited briefs and approval requests land."
        />
        <PolicyRow
          label="Working model"
          value="Anthropic Claude (your key)"
          description="Bring your own key - your data stays out of vendor pools."
        />
      </div>

      <div className="card-surface p-4 bg-[#16d05e]/[0.04] border-[#16d05e]/20">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="h-4 w-4 text-[#16d05e]" />
          <span>
            Free tier: <span className="font-semibold">50 resolutions / month</span> · no card needed
          </span>
        </div>
      </div>

      <Button
        variant="accent"
        size="lg"
        className="w-full"
        onClick={onLaunch}
        rightIcon={<ArrowRight className="h-4 w-4" />}
      >
        Put Manthan on the queue
      </Button>

      <p className="text-center text-[11.5px] text-white/40">
        First case fires whenever your next Stripe event lands.
      </p>
    </div>
  );
}

function PolicyRow({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="card-surface p-4 card-surface-hover">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-white">{label}</div>
          <div className="text-[11.5px] text-white/45 mt-0.5">{description}</div>
        </div>
        <button className="shrink-0 inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-white/[0.04] border border-white/10 text-sm text-white hover:bg-white/[0.08]">
          <span>{value}</span>
          <span className="text-white/30">›</span>
        </button>
      </div>
    </div>
  );
}
