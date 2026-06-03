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
  maya: {
    ctaLabel: "Walk me through it",
    slides: [
      {
        image: "/story/maya/01-the-email-lands.webp",
        eyebrow: "Monday · 06:42 PT",
        heading: "An $89 refund request just hit support.",
        body: [
          "Maya Patel runs a five-person design studio called Maya Patel Design. She pays $89 a month for Caldera Pro. On May 22 our billing system charged her twice in the same four-minute window. The first charge was clean. The second was a glitch. She caught it three days later, opened her Gmail, typed nine polite lines, hit send.",
          "Her email is now sitting in support@manthan.quest along with forty-six other tickets that landed overnight. Forty-five of them are not refunds. The one that is, is Maya's.",
        ],
        footer: "From: maya@mayapateldesign.com · Subject: Charged twice for Caldera Pro, please refund · Resend inbound",
      },
      {
        image: "/story/maya/02-the-cost-of-waiting.webp",
        eyebrow: "What's at stake",
        heading: "Tickets like Maya's pay for themselves to fix.",
        body: [
          "A duplicate-charge refund is the easy case. The customer is right, the math is obvious, the policy is clear, the action is one button. And yet at most companies it still takes a human five to eighteen hours to close. The ticket waits in a queue, an agent reads it, an agent opens Stripe, an agent verifies the duplicate, an agent fires the refund, an agent writes Maya back. The cost of resolving an $89 refund quietly exceeds $89.",
          "Slow refunds also cost trust. Maya is in a Slack community with three other studio owners who all use Caldera. If we take a week to issue eighty-nine dollars back, the next renewal cycle costs us more than the refund did.",
        ],
      },
      {
        image: "/story/maya/03-four-systems.webp",
        eyebrow: "Why this is hard",
        heading: "A refund is one click, but the decision lives in four systems.",
        body: [
          "The agent needs to confirm Maya was actually charged twice, confirm the second charge was not a separate seat or upgrade she forgot, check whether she already opened a parallel ticket we are about to step on, and check our own refund policy for which charge to reverse and what to tell her. Each answer lives in a different tool, none of them talking to each other.",
        ],
        sources: [
          {
            src: "stripe",
            what: "Both charges and the customer record. Which one is the duplicate, which one stays.",
          },
          {
            src: "hubspot",
            what: "Maya's company profile and plan history. Was the second charge a legitimate seat add or a glitch.",
          },
          {
            src: "intercom",
            what: "Did Maya already open a ticket about this. Are we about to refund something a teammate is already handling.",
          },
          {
            src: "notion",
            what: "The Refund Policy SOP. Which charge to reverse, what to email Maya, what to log in the audit trail.",
          },
        ],
      },
      {
        image: "/story/maya/04-the-old-way.webp",
        eyebrow: "The old way",
        heading: "A ticket queue, four tabs, twelve copy-pastes.",
        body: [
          "A support agent opens Maya's email, copies her address into Stripe, lands on her customer record, scrolls to find the two charges, opens both, eyeballs the timestamps, decides which is the duplicate, opens HubSpot to confirm her plan, opens Intercom to make sure they are not stepping on a teammate, opens Notion to remember the refund-email template, switches back to Stripe, clicks Refund, switches to the support inbox, writes a reply that sounds like a human wrote it.",
          "That ritual is twenty minutes if the agent is fast and forty if the agent is new. Multiply by forty-six tickets a day. This is what burns out support teams.",
        ],
      },
      {
        image: "/story/maya/05-autonomous-lane.webp",
        eyebrow: "Manthan",
        heading: "One inbox. One agent. End to end.",
        body: [
          "Manthan reads every email that lands in your support inbox. The obvious cases (duplicate charges, failed-renewal recoveries, refund requests inside your own policy window) it resolves end to end. It queries Stripe, HubSpot, Intercom, and your Notion SOPs in parallel, drafts the refund, fires it if policy says auto, queues it for one-click approval if policy says human in the loop, and writes Maya back in your team's voice with the receipt attached.",
          "The hard ones (a $4,000 enterprise refund with a half-signed amendment) it escalates with the brief already written, the evidence already cited, the policy clause already located. The human walks in with everything they need.",
        ],
      },
      {
        image: "/story/maya/05-autonomous-lane.webp",
        eyebrow: "Send your own ticket",
        heading: "Run Maya's email through it yourself.",
        body: [
          "What's next is a short guided walkthrough. You'll send the same email Maya sent (a one-click prefilled template from your own inbox) to support@manthan.quest. Manthan will see it land, open the case in your workspace, investigate across the connected sources, and either auto-resolve or hand you a brief with a one-button approve.",
          "Every fact in the brief cites the system it came from. Click any citation, the source record opens in a new tab. No trust, just receipts.",
        ],
      },
    ],
  },
  vermillion: {
    ctaLabel: "Walk me through it",
    slides: [
      {
        image: "/story/vermillion/01-cfo-pings-slack.webp",
        eyebrow: "Wednesday · 14:12 IST",
        heading: "The CFO just dropped a chargeback in your Slack.",
        body: [
          "Marcus Webb (CFO at Vermillion Studios, the design agency on our Pro Annual plan) just filed a $4,500 chargeback through his bank. The reason on the dispute is \"product not received.\" His message to your billing team, ten minutes later, is sharper: \"we are being billed for 25 seats but we only have 15.\"",
          "That message just landed in #billing-platform along with three other pings and a meme. Your finance lead saw it on a phone notification, knows it is real, has a board call in an hour.",
        ],
        footer: "From: Marcus Webb (CFO, Vermillion Studios) · #billing-platform · Slack",
      },
      {
        image: "/story/vermillion/02-two-truths.webp",
        eyebrow: "What's at stake",
        heading: "Two truths, one of them outdated.",
        body: [
          "Marcus is right that the original contract was for 15 seats. Marcus is wrong that the contract still says 15 seats. Eight months ago his own COO, Sarah Chen, signed a written addendum adding 10 more during a hiring sprint. The addendum is on Vermillion's letterhead, in our Notion, with Sarah's signature and a date stamp.",
          "If we refund the $4,500 because Marcus said so on Slack, we set a precedent: CFOs can override their own COO's signed amendments by yelling in chat. If we ignore him because the addendum is signed, we lose the customer. The right answer is to show him the addendum inside an hour, in his channel, with the signature receipt.",
        ],
      },
      {
        image: "/story/vermillion/03-four-places.webp",
        eyebrow: "Why this is hard",
        heading: "The proof is split across four places nobody opens together.",
        body: [
          "Marcus's claim is in Slack. The active subscription is in Stripe. The signed amendment is a Notion page. The seat-count reality (24 active users out of the 25 we are billing for) is in product analytics. Building the receipt for Marcus means joining all four in under an hour, on a phone, while you are already late to the board call.",
        ],
        sources: [
          {
            src: "stripe",
            what: "The disputed charge and the active subscription. Confirms we are billing 25 seats, not 15.",
          },
          {
            src: "hubspot",
            what: "Vermillion's company record, account owner, deal history. Who Marcus is in our world.",
          },
          {
            src: "notion",
            what: "The signed seat-addendum from Sarah Chen, dated 2026-02-08. The receipt that ends the conversation.",
          },
          {
            src: "slack",
            what: "Marcus's own message in #billing-platform. The thread we will post the answer back into.",
          },
        ],
      },
      {
        image: "/story/vermillion/04-chase-colleagues.webp",
        eyebrow: "The old way",
        heading: "Slack a colleague, wait for a colleague, miss the window.",
        body: [
          "Your finance lead opens the thread, cannot answer in real time, pings the account owner: \"do you remember if Vermillion added seats.\" Account owner is in a Loom recording. Forty minutes later, account owner pings Sales. Sales pings Legal. Legal finally finds the Notion page. By the time the answer comes back, Marcus has opened a second dispute, escalated to LinkedIn, and the board call is over.",
          "Most billing chargebacks are not won or lost on the merits. They are won or lost on response time.",
        ],
      },
      {
        image: "/story/vermillion/05-manthan-in-slack.webp",
        eyebrow: "Manthan",
        heading: "Mention the bot. Get the receipt in the thread.",
        body: [
          "Manthan lives in your workspace as a regular member. You tag it in any channel (\"@manthan, look into the Vermillion chargeback\"), it investigates across every connected system as one unified data layer, and posts back into the same thread with the answer, the evidence, and the recommended action.",
          "Every claim links back to the source record. Click the addendum citation, the Notion page opens. Click the seat-count citation, the analytics view opens. The brief is small enough to read on a phone. The approve button takes a real signature. The whole thing fits in the thread your CFO already started.",
        ],
      },
      {
        image: "/story/vermillion/05-manthan-in-slack.webp",
        eyebrow: "Mention the bot yourself",
        heading: "Run the Vermillion case in your own Slack.",
        body: [
          "What's next is a short guided walkthrough. You'll join a shared Slack workspace (we'll route the case back to your own Manthan workspace), open #all-manthandemo, tag @manthantest with the Vermillion chargeback message, and watch the agent respond in-thread with the brief, the citations, and the approve button.",
          "What you see in Slack is what your CFO would see if you wired Manthan into your real workspace today. The exact same Coral query layer drives both.",
        ],
      },
    ],
  },
};

export function storyFor(scenarioId: string): ScenarioStory | null {
  return STORY_BY_SCENARIO[scenarioId] ?? null;
}
