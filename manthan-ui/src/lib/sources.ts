/**
 * Source catalog for Manthan - every SaaS Manthan reads (via Coral) or
 * writes to (via native action layer). Logos are sourced from simple-icons.
 *
 * Per-icon NAMED imports (NOT `import * as si`) so the bundler only
 * ships the ~25 icons we actually use, not all ~3000 brands in the
 * 5MB simple-icons catalog. simple-icons sets sideEffects=false; named
 * imports tree-shake cleanly.
 */

import {
  siClerk,
  siClickup,
  siConfluence,
  siDatadog,
  siDiscord,
  siGithub,
  siGitlab,
  siGmail,
  siHubspot,
  siIntercom,
  siJira,
  siLinear,
  siMixpanel,
  siNotion,
  siOkta,
  siPaddle,
  siPagerduty,
  siPosthog,
  siRazorpay,
  siSentry,
  siStripe,
  siZendesk,
  type SimpleIcon,
} from "simple-icons";

const SI_BY_KEY: Record<string, SimpleIcon> = {
  Clerk: siClerk,
  Clickup: siClickup,
  Confluence: siConfluence,
  Datadog: siDatadog,
  Discord: siDiscord,
  Github: siGithub,
  Gitlab: siGitlab,
  Gmail: siGmail,
  Hubspot: siHubspot,
  Intercom: siIntercom,
  Jira: siJira,
  Linear: siLinear,
  Mixpanel: siMixpanel,
  Notion: siNotion,
  Okta: siOkta,
  Paddle: siPaddle,
  Pagerduty: siPagerduty,
  Posthog: siPosthog,
  Razorpay: siRazorpay,
  Sentry: siSentry,
  Stripe: siStripe,
  Zendesk: siZendesk,
};

export type SourceCategory =
  | "payments"
  | "crm"
  | "support"
  | "comms"
  | "issue_tracking"
  | "docs"
  | "product_analytics"
  | "identity"
  | "feature_flags"
  | "observability"
  | "incident"
  | "version_control"
  | "infra"
  | "marketing";

export type ManthanCapability = "read" | "write" | "trigger";

export interface SourceMeta {
  id: string;
  name: string;
  category: SourceCategory;
  description: string;
  /** Path data + brand hex. simple-icons defaults to a "0 0 24 24"
   *  viewBox; brands shipped from their own kits may use a different
   *  one (e.g. Resend ships 0 0 1800 1800). `viewBox` is optional -
   *  omit it for simple-icons entries. */
  simpleIcon?: { hex: string; path: string; viewBox?: string };
  capabilities: ManthanCapability[];
  oauth: boolean;
  /** Whether the source is "primary" for its category (default selected in onboarding). */
  primary?: boolean;
}

/**
 * Manual fallbacks for brands that simple-icons has dropped due to
 * trademark requests (Salesforce, Slack - both removed mid-2024) or
 * never carried (Resend ships its own brand kit).
 *
 * Most entries omit `viewBox` and inherit the simple-icons standard
 * "0 0 24 24"; brand kits with their own coordinate system (Resend's
 * 1800x1800) declare it explicitly.
 */
const ICON_OVERRIDES: Record<
  string,
  { hex: string; path: string; viewBox?: string }
> = {
  Salesforce: {
    hex: "00A1E0",
    path:
      "M10.006 5.415a4.195 4.195 0 0 1 3.045-1.306c1.56 0 2.954.9 3.69 2.205.63-.297 1.35-.45 2.1-.45 2.85 0 5.159 2.34 5.159 5.22 0 2.879-2.31 5.219-5.16 5.219-.36 0-.69-.044-1.005-.104a3.78 3.78 0 0 1-3.3 1.95c-.6 0-1.155-.15-1.65-.375A4.314 4.314 0 0 1 8.88 20.4a4.302 4.302 0 0 1-4.05-2.834 3.96 3.96 0 0 1-.83.089A4.08 4.08 0 0 1 0 13.563c0-1.5.81-2.805 2.01-3.51a4.643 4.643 0 0 1-.39-1.86 4.687 4.687 0 0 1 8.378-2.865c.508-.965 1.519-1.625 2.688-1.625a2.998 2.998 0 0 1 2.41 1.21z",
  },
  Slack: {
    hex: "4A154B",
    path:
      "M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z",
  },
  // Resend ships its own brand assets - the white icon from
  // resend-brand-assets.zip. Native 1800x1800 viewBox; SourceIcon
  // honors the override. The brand hex is white; on light backgrounds
  // the DARK_ON_DARK override in SourceIcon flips it to ink-strong
  // for legibility (same trick we use for Notion/PostHog).
  Resend: {
    hex: "FDFDFD",
    viewBox: "0 0 1800 1800",
    path:
      "M1000.46 450C1174.77 450 1278.43 553.669 1278.43 691.282C1278.43 828.896 1174.77 932.563 1000.46 932.563H912.382L1350 1350H1040.82L707.794 1033.48C683.944 1011.47 672.936 985.781 672.935 963.765C672.935 932.572 694.959 905.049 737.161 893.122L908.712 847.244C973.85 829.812 1018.81 779.353 1018.81 713.298C1018.8 632.567 952.745 585.78 871.095 585.78H450V450H1000.46Z",
  },
};

function icon(
  key: string,
): { hex: string; path: string; viewBox?: string } | undefined {
  if (ICON_OVERRIDES[key]) return ICON_OVERRIDES[key];
  const found = SI_BY_KEY[key];
  return found ? { hex: found.hex, path: found.path } : undefined;
}

export const SOURCES: SourceMeta[] = [
  // ─── Payments ─────────────────────────────────────────────────────────
  {
    id: "stripe",
    name: "Stripe",
    category: "payments",
    description: "Payments, subscriptions, chargebacks, refunds",
    simpleIcon: icon("Stripe"),
    capabilities: ["read", "write", "trigger"],
    oauth: true,
    primary: true,
  },
  {
    id: "razorpay",
    name: "Razorpay",
    category: "payments",
    description: "Payments (India + APAC)",
    simpleIcon: icon("Razorpay"),
    capabilities: ["read", "write"],
    oauth: false,
  },
  {
    id: "paddle",
    name: "Paddle",
    category: "payments",
    description: "Merchant of record payments",
    simpleIcon: icon("Paddle"),
    capabilities: ["read", "write"],
    oauth: false,
  },

  // ─── CRM ─────────────────────────────────────────────────────────────
  {
    id: "salesforce",
    name: "Salesforce",
    category: "crm",
    description: "Enterprise CRM - accounts, opportunities",
    simpleIcon: icon("Salesforce"),
    capabilities: ["read", "write", "trigger"],
    oauth: true,
    primary: true,
  },
  {
    id: "hubspot",
    name: "HubSpot",
    category: "crm",
    description: "Mid-market CRM - contacts, companies, deals",
    simpleIcon: icon("Hubspot"),
    capabilities: ["read", "write", "trigger"],
    oauth: true,
  },

  // ─── Support ─────────────────────────────────────────────────────────
  {
    id: "zendesk",
    name: "Zendesk",
    category: "support",
    description: "Enterprise support tickets + CSAT",
    simpleIcon: icon("Zendesk"),
    capabilities: ["read", "write", "trigger"],
    oauth: true,
    primary: true,
  },
  {
    id: "intercom",
    name: "Intercom",
    category: "support",
    description: "Modern support, in-app messaging",
    simpleIcon: icon("Intercom"),
    capabilities: ["read", "write", "trigger"],
    oauth: true,
  },

  // ─── Comms ───────────────────────────────────────────────────────────
  {
    id: "slack",
    name: "Slack",
    category: "comms",
    description: "Briefs, approvals, and live activity",
    simpleIcon: icon("Slack"),
    capabilities: ["read", "write", "trigger"],
    oauth: true,
    primary: true,
  },
  {
    id: "discord",
    name: "Discord",
    category: "comms",
    description: "Community + ops chat",
    simpleIcon: icon("Discord"),
    capabilities: ["read", "write"],
    oauth: true,
  },
  {
    id: "gmail",
    name: "Gmail",
    category: "comms",
    description: "Draft + send customer email",
    simpleIcon: icon("Gmail"),
    capabilities: ["read", "write"],
    oauth: true,
  },
  {
    id: "resend",
    name: "Resend",
    category: "comms",
    description: "Transactional + inbound email - Manthan's outbound rail",
    simpleIcon: icon("Resend"),
    capabilities: ["write"],
    oauth: false,
    primary: true,
  },

  // ─── Issue tracking ──────────────────────────────────────────────────
  {
    id: "linear",
    name: "Linear",
    category: "issue_tracking",
    description: "Modern issue tracker for escalations",
    simpleIcon: icon("Linear"),
    capabilities: ["read", "write"],
    oauth: true,
    primary: true,
  },
  {
    id: "jira",
    name: "Jira",
    category: "issue_tracking",
    description: "Enterprise issue tracker",
    simpleIcon: icon("Jira"),
    capabilities: ["read", "write"],
    oauth: true,
  },
  {
    id: "clickup",
    name: "ClickUp",
    category: "issue_tracking",
    description: "Multi-team task tracker",
    simpleIcon: icon("Clickup"),
    capabilities: ["read", "write"],
    oauth: true,
  },

  // ─── Docs / runbooks ─────────────────────────────────────────────────
  {
    id: "notion",
    name: "Notion",
    category: "docs",
    description: "Runbooks + policy docs",
    simpleIcon: icon("Notion"),
    capabilities: ["read", "write"],
    oauth: true,
    primary: true,
  },
  {
    id: "confluence",
    name: "Confluence",
    category: "docs",
    description: "Enterprise runbooks",
    simpleIcon: icon("Confluence"),
    capabilities: ["read"],
    oauth: true,
  },

  // ─── Product analytics ───────────────────────────────────────────────
  {
    id: "posthog",
    name: "PostHog",
    category: "product_analytics",
    description: "Open-source product analytics",
    simpleIcon: icon("Posthog"),
    capabilities: ["read"],
    oauth: false,
    primary: true,
  },
  {
    id: "mixpanel",
    name: "Mixpanel",
    category: "product_analytics",
    description: "Event analytics",
    simpleIcon: icon("Mixpanel"),
    capabilities: ["read"],
    oauth: true,
  },

  // ─── Identity ────────────────────────────────────────────────────────
  {
    id: "okta",
    name: "Okta",
    category: "identity",
    description: "Enterprise SSO + identity",
    simpleIcon: icon("Okta"),
    capabilities: ["read"],
    oauth: true,
    primary: true,
  },
  {
    id: "clerk",
    name: "Clerk",
    category: "identity",
    description: "Modern auth",
    simpleIcon: icon("Clerk"),
    capabilities: ["read"],
    oauth: true,
  },
  {
    id: "auth0",
    name: "Auth0",
    category: "identity",
    description: "Identity platform",
    simpleIcon: icon("Auth0"),
    capabilities: ["read"],
    oauth: true,
  },

  // ─── Observability ───────────────────────────────────────────────────
  {
    id: "sentry",
    name: "Sentry",
    category: "observability",
    description: "Error tracking - bug context for billing issues",
    simpleIcon: icon("Sentry"),
    capabilities: ["read", "trigger"],
    oauth: true,
  },
  {
    id: "datadog",
    name: "Datadog",
    category: "observability",
    description: "APM + monitors",
    simpleIcon: icon("Datadog"),
    capabilities: ["read"],
    oauth: true,
  },
  {
    id: "pagerduty",
    name: "PagerDuty",
    category: "incident",
    description: "Incident pages + on-call",
    simpleIcon: icon("Pagerduty"),
    capabilities: ["read", "trigger"],
    oauth: true,
  },

  // ─── Version control ─────────────────────────────────────────────────
  {
    id: "github",
    name: "GitHub",
    category: "version_control",
    description: "Audit log of code changes that affect billing",
    simpleIcon: icon("Github"),
    capabilities: ["read"],
    oauth: true,
    primary: true,
  },
  {
    id: "gitlab",
    name: "GitLab",
    category: "version_control",
    description: "VCS alt",
    simpleIcon: icon("Gitlab"),
    capabilities: ["read"],
    oauth: true,
  },
];

export const CATEGORY_LABELS: Record<SourceCategory, string> = {
  payments: "Payments & Billing",
  crm: "CRM",
  support: "Support",
  comms: "Communications",
  issue_tracking: "Issue Tracking",
  docs: "Runbooks & Docs",
  product_analytics: "Product Analytics",
  identity: "Identity & SSO",
  feature_flags: "Feature Flags",
  observability: "Observability",
  incident: "Incident",
  version_control: "Version Control",
  infra: "Infrastructure",
  marketing: "Marketing",
};

export function sourcesByCategory(): Record<SourceCategory, SourceMeta[]> {
  const out = {} as Record<SourceCategory, SourceMeta[]>;
  for (const src of SOURCES) {
    (out[src.category] ??= []).push(src);
  }
  return out;
}

export function getSource(id: string): SourceMeta | undefined {
  return SOURCES.find((s) => s.id === id);
}

/** The exact 10 sources Manthan ships with for the Billing Ops pack. */
export const BILLING_OPS_STACK = [
  "stripe",
  "salesforce",
  "hubspot",
  "zendesk",
  "intercom",
  "slack",
  "linear",
  "notion",
  "gmail",
  "okta",
] as const;
