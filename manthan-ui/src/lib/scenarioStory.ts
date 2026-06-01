/**
 * Story slides for the Aperture demo. The reader walks through these
 * six beats BEFORE the case fires - they get the setup (what's at
 * stake, why this is hard, how Manthan is going to attack it), then
 * the agent actually runs and shows them the answer live. The story
 * intentionally never pre-reveals the verdict (the brief, the math,
 * the recommended credit amount) - that's what the investigation is
 * for.
 *
 * Images live in /public/story/aperture/ as WebP (~40-130KB each).
 */

export interface SourceBeat {
  /** Slug from the source catalog (stripe, hubspot, notion, …). */
  src: string;
  /** One-line description of what THIS source will answer for the case. */
  what: string;
}

export interface StorySlide {
  image: string;
  eyebrow?: string;
  heading: string;
  /** Paragraph or paragraphs. Each entry renders as a separate <p>. */
  body: string | string[];
  /** Optional structured source-breakdown rendered as a list of
   *  brand-color rows. Used on the "what each system holds" slide. */
  sources?: SourceBeat[];
  footer?: string;
}

export interface ScenarioStory {
  slides: StorySlide[];
  /** Last-slide CTA text on the "fire" button. */
  ctaLabel: string;
}

export const STORY_BY_SCENARIO: Record<string, ScenarioStory> = {
  aperture: {
    ctaLabel: "Begin investigation",
    slides: [
      {
        image: "/story/aperture/01-dispute-arrives.webp",
        eyebrow: "Tuesday · 06:14 UTC",
        heading: "An $8,400 chargeback just landed.",
        body: [
          "Aperture Analytics - a data-analytics customer on the Premium tier - disputed their April monthly charge through their bank. Stripe flagged the reason as “product not as described.” Their internal note: a 48-hour outage on Custom Reports that hit them mid-billing-cycle.",
          "The clock is now Stripe's. We have seven days to either issue a refund or submit evidence the charge was valid. Either way: a decision has to be made before Saturday.",
        ],
        footer:
          "Dispute du_1Tch1OCNe0SBMhzIAppAdJjT · Charge ch_3Tch1LCNe0SBMhzI0FIYdCkF · Stripe",
      },
      {
        image: "/story/aperture/02-the-weight.webp",
        eyebrow: "What's at stake",
        heading: "Two bad answers and a customer in the middle.",
        body: [
          "Refund the full $8,400 and we lose revenue we've already recognized, set a precedent, and signal that disputes get paid. Fight without evidence and we lose a $100k-ARR customer who legitimately felt unheard - Aperture downgraded to Standard four days after the outage.",
          "The right answer isn't refund-or-fight. It's whether the outage actually happened, how long it lasted, and what our own internal policy says we owe when paid-tier features degrade for documented incidents.",
        ],
      },
      {
        image: "/story/aperture/03-eight-tab-scramble.webp",
        eyebrow: "Why this is hard",
        heading: "The answer lives in eight different systems.",
        body: [
          "No single tool knows the full story. The truth is split across the systems your company already paid for - billing, CRM, observability, support, internal docs, product analytics, ops chat. Each one holds one piece. None of them talk to each other.",
        ],
        sources: [
          {
            src: "stripe",
            what:
              "The dispute itself, the original charge, and the customer record - payment of truth.",
          },
          {
            src: "hubspot",
            what:
              "Aperture's company record: ARR, contract size, lifecycle stage. Tells us how much this customer is worth keeping.",
          },
          {
            src: "datadog",
            what:
              "Did the outage actually happen? When did it start and end? Was Custom Reports the affected service?",
          },
          {
            src: "notion",
            what:
              "The Pro-Rata Refund Credit Policy - the SOP that defines exactly what we owe for documented operational incidents.",
          },
          {
            src: "intercom",
            what:
              "Did Aperture's billing contact actually complain at the time, or are they re-litigating now?",
          },
          {
            src: "zendesk",
            what:
              "Did anyone in support verbally promise a credit that was never actioned? That's a different remedy than the policy.",
          },
          {
            src: "posthog",
            what:
              "Did Aperture's actual product usage drop during the disputed window? Or did they keep using the feature they're claiming was broken?",
          },
          {
            src: "slack",
            what:
              "Did engineering internally acknowledge the incident in the ops channel? That's our admission.",
          },
        ],
      },
      {
        image: "/story/aperture/04-gut-decision.webp",
        eyebrow: "The old way",
        heading: "Five hours of tabs and gut.",
        body: [
          "A senior analyst opens all eight tools, logs in eight times, pastes the customer email into eight search boxes, learns each system's quirks. By hour three they have half the context. By hour five they're in a meeting and have to make a call.",
          "Most chargeback decisions get made with less data than the customer used to file the dispute. The cheap answer wins: just refund it and move on.",
        ],
      },
      {
        image: "/story/aperture/05-manthan-arrives.webp",
        eyebrow: "Manthan",
        heading: "One agent. Eight systems. In parallel.",
        body: [
          "Manthan starts the second the chargeback hits the webhook. Instead of clicking through dashboards, it queries every connected source as a unified data layer (that's Coral) - the same way you'd join two tables in SQL, except the tables live in Stripe, HubSpot, Datadog, Notion, and five other vendors.",
          "Every fact it surfaces gets cited back to the source record. Click a citation, the actual Datadog incident or Notion page opens in a new tab. No hidden reasoning, no “trust me.”",
        ],
      },
      {
        image: "/story/aperture/05-manthan-arrives.webp",
        eyebrow: "Investigation begins",
        heading: "Now watch Manthan work.",
        body: [
          "Manthan has live read access to all eight connected sources - Stripe, HubSpot, Datadog, Notion, Intercom, Zendesk, PostHog, Slack. The moment you click Begin, it starts querying them in parallel as a unified data layer and surfaces facts as they land.",
          "You'll see every SQL it runs, every source it touches, every claim it makes - each one with a citation back to the underlying record. Nothing hidden, nothing fabricated.",
        ],
      },
    ],
  },
};

export function storyFor(scenarioId: string): ScenarioStory | null {
  return STORY_BY_SCENARIO[scenarioId] ?? null;
}
