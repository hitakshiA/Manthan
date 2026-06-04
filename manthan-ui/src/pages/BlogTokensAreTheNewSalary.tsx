/**
 * "Tokens are the new salary" - canonical home for the Captain's Log
 * essay before it cross-posts to LinkedIn. Uses a custom layout (not
 * the MarketingShell content slot) because the inline illustrations
 * need to break out of the 3xl prose column to land at editorial
 * width, and the body is set in Spectral serif at 19px to match the
 * tone of the story-overlay slides rather than the legal-page copy.
 */

import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { useEffect } from "react";
import { Logo } from "@/components/Logo";

// ──────────────────────────────────────────────────────────────────────
// Typography primitives - kept inline because this is a one-off
// page; nothing else in the app needs Spectral-at-20 yet.
// ──────────────────────────────────────────────────────────────────────

function Para({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        fontFamily: "Spectral, serif",
        fontSize: 19,
        lineHeight: 1.62,
        color: "oklch(0.86 0.006 75)",
        letterSpacing: "-0.003em",
      }}
    >
      {children}
    </p>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontFamily: "Spectral, serif",
        fontStyle: "italic",
        fontSize: "clamp(28px, 3.2vw, 38px)",
        lineHeight: 1.15,
        color: "oklch(0.97 0.004 75)",
        letterSpacing: "-0.012em",
        fontWeight: 400,
        marginTop: 56,
        marginBottom: 28,
      }}
    >
      {children}
    </h2>
  );
}

function H3({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        fontFamily: "Geist, sans-serif",
        fontSize: 17,
        fontWeight: 600,
        color: "oklch(0.96 0.004 75)",
        letterSpacing: "-0.005em",
        marginTop: 32,
        marginBottom: 8,
      }}
    >
      {children}
    </h3>
  );
}

function PullQuote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote
      style={{
        fontFamily: "Spectral, serif",
        fontStyle: "italic",
        fontSize: "clamp(22px, 2.5vw, 28px)",
        lineHeight: 1.35,
        color: "oklch(0.96 0.004 75)",
        borderLeft: "2px solid #C97B2A",
        paddingLeft: 22,
        marginLeft: 0,
        marginTop: 36,
        marginBottom: 36,
        letterSpacing: "-0.006em",
      }}
    >
      {children}
    </blockquote>
  );
}

function Figure({
  src,
  alt,
  caption,
}: {
  src: string;
  alt: string;
  caption?: string;
}) {
  return (
    <figure
      style={{
        marginTop: 48,
        marginBottom: 48,
        marginLeft: "calc(50% - min(50vw, 540px))",
        marginRight: "calc(50% - min(50vw, 540px))",
      }}
    >
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        style={{
          width: "100%",
          height: "auto",
          borderRadius: 8,
          border: "1px solid rgba(255,255,255,0.08)",
          display: "block",
        }}
      />
      {caption && (
        <figcaption
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "oklch(0.55 0.006 75)",
            marginTop: 12,
            textAlign: "center",
          }}
        >
          {caption}
        </figcaption>
      )}
    </figure>
  );
}

// ──────────────────────────────────────────────────────────────────────
// The page
// ──────────────────────────────────────────────────────────────────────

export default function BlogTokensAreTheNewSalary() {
  // Set the document title + canonical link for SEO. Not via Helmet
  // because we don't pull that dep just for one page; direct DOM is
  // fine inside a useEffect on a route component.
  useEffect(() => {
    const prevTitle = document.title;
    document.title = "Tokens are the new salary · Manthan";
    let canonical = document.querySelector(
      'link[rel="canonical"]',
    ) as HTMLLinkElement | null;
    const created = !canonical;
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.appendChild(canonical);
    }
    canonical.href = "https://manthan.quest/blog/tokens-are-the-new-salary";

    // OG meta for LinkedIn share preview.
    const metas: Array<[string, string]> = [
      ["og:title", "Tokens are the new salary"],
      [
        "og:description",
        "Uber burned its 2026 AI budget in four months. The next hundred AI-native service companies will hit the same wall. The bet we made on Coral that we think survives it.",
      ],
      [
        "og:image",
        "https://manthan.quest/blog/01-cover-many-to-one.webp",
      ],
      ["og:url", "https://manthan.quest/blog/tokens-are-the-new-salary"],
      ["og:type", "article"],
    ];
    const createdMetas: HTMLMetaElement[] = [];
    metas.forEach(([property, content]) => {
      let m = document.querySelector(
        `meta[property="${property}"]`,
      ) as HTMLMetaElement | null;
      if (!m) {
        m = document.createElement("meta");
        m.setAttribute("property", property);
        document.head.appendChild(m);
        createdMetas.push(m);
      }
      m.content = content;
    });

    return () => {
      document.title = prevTitle;
      if (created && canonical) canonical.remove();
      createdMetas.forEach((m) => m.remove());
    };
  }, []);

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: "#000", color: "oklch(0.95 0.004 75)" }}
    >
      {/* Nav */}
      <nav className="relative z-30 px-6 md:px-12 lg:px-20 py-5 flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-2.5 hover:opacity-90 transition-opacity"
        >
          <Logo size={26} showWordmark={false} className="text-white" />
          <span className="text-lg font-semibold tracking-tight text-white">
            Manthan
          </span>
        </Link>
        <div className="flex items-center gap-5">
          <Link
            to="/blog"
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              fontSize: 11,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "oklch(0.65 0.006 75)",
            }}
          >
            ← Blog
          </Link>
          <Link to="/login">
            <button
              className="rounded-lg text-sm font-semibold px-4 py-2 hover:opacity-90 transition-opacity"
              style={{ background: "#fff", color: "#000" }}
            >
              Sign in
            </button>
          </Link>
        </div>
      </nav>

      <main className="flex-1 w-full px-6 md:px-12 lg:px-20 pt-10 md:pt-16 pb-24 md:pb-32">
        <motion.article
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
          className="max-w-3xl mx-auto"
          style={{ position: "relative" }}
        >
          {/* Eyebrow */}
          <div
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              fontSize: 11,
              color: "oklch(0.55 0.006 75)",
              letterSpacing: "0.20em",
              textTransform: "uppercase",
              marginBottom: 20,
            }}
          >
            Captain's Log · June 2026
          </div>

          {/* Title */}
          <h1
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              fontSize: "clamp(44px, 5.6vw, 76px)",
              lineHeight: 1.02,
              color: "oklch(0.98 0.003 75)",
              letterSpacing: "-0.018em",
              fontWeight: 400,
            }}
          >
            Tokens are the new salary.
          </h1>

          {/* Subtitle */}
          <p
            style={{
              fontFamily: "Spectral, serif",
              fontSize: "clamp(20px, 2.2vw, 26px)",
              lineHeight: 1.4,
              color: "oklch(0.78 0.006 75)",
              marginTop: 22,
              letterSpacing: "-0.005em",
            }}
          >
            Uber burned its 2026 AI budget in four months. The next hundred
            AI-native service companies will hit the same wall. Here is the
            bet we made on Coral that we think survives it.
          </p>

          {/* Byline */}
          <div
            style={{
              marginTop: 28,
              display: "flex",
              alignItems: "center",
              gap: 14,
              fontFamily: "Geist Mono, ui-monospace, monospace",
              fontSize: 12,
              color: "oklch(0.62 0.006 75)",
              letterSpacing: "0.06em",
            }}
          >
            <span>By Akash Mondal</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>June 4, 2026</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>11 minute read</span>
          </div>

          <div
            style={{
              marginTop: 36,
              height: 1,
              background: "rgba(255,255,255,0.10)",
            }}
          />

          {/* COVER IMAGE */}
          <Figure
            src="/blog/01-cover-many-to-one.webp"
            alt="Editorial illustration: vendor-shaped translucent ribbons collapsing through a coral-shaped lens into one clean amber line"
            caption="Many systems in. One structured query out."
          />

          {/* BODY */}
          <Para>
            In April, Uber's CTO admitted to <em>The Information</em> that
            the company had burned through its entire 2026 AI coding tools
            budget in four months. Engineering leaderboards. Public ranking
            of who used the tools most. The tools worked. Then the bill
            came in.
          </Para>

          <Para>
            I read that piece in the back of a Bangalore Uber, which felt
            about right.
          </Para>

          <Para>
            Microsoft is scaling back internal AI use over the same
            surprise. ServiceNow flagged AI cost-of-revenue compression on
            its January call, first time the company has used that phrase.
            Deloitte's Q4 2025 enterprise report found teams discovering
            "tens of millions" of monthly bills from agentic loops they
            had quietly shipped six months earlier. Gartner says forty
            percent of agentic projects will be killed by 2027. Not
            because the AI is bad. Because the unit economics inverted
            before the founder had time to refactor.
          </Para>

          <PullQuote>The industry has a name for this now. Token tsunamis.</PullQuote>

          <Para>
            That is the room in which Y Combinator's Gustaf Alströmer
            dropped his Summer 2026 Request for Startups, where{" "}
            <strong>"AI-Native Service Companies"</strong> sits at category
            number one of fifteen. The argument is short and obviously
            right. Global spend on services is much larger than software.
            Most of those services are already outsourced. AI agents can
            do the actual work, not assist it. Insurance brokerage.
            Accounting. Audit. Healthcare admin. Compliance. Replace the
            service. Sell the outcome. Stop shipping tools.
          </Para>

          <Para>
            Every founder reading that RFS understood the opportunity.
          </Para>

          <Para>
            Far fewer noticed what it requires you to survive.
          </Para>

          {/* SECTION 2 */}
          <Figure
            src="/blog/02-the-bill.webp"
            alt="Amber coins spilling off the edge of a bone-colored desk into deep navy shadow, a single teal thread catching one coin mid-fall"
            caption="The bill arrives. Discipline catches the few that matter."
          />

          <H2>The economics of doing the work yourself.</H2>

          <Para>
            We build Manthan, which sits in one of those YC-shaped corners:
            revenue disputes. A typical investigation crosses six to eight
            systems. Stripe for the charge. HubSpot for the customer.
            Notion for whichever refund policy somebody wrote in 2024 and
            forgot. Datadog for the outage timeline. Intercom for the
            email the customer sent before they filed the dispute. Slack
            for the engineer who admitted in #incidents that yeah we did
            have a bad afternoon. PostHog for whether the customer
            actually used the feature they say was broken. Zendesk for the
            ticket nobody answered.
          </Para>

          <Para>
            Each system holds one piece. The agent has to read all of them
            to write something a finance lead would sign off on. That is
            the work. That is what a senior controller did before. That is
            what an AI-native company has to do faster and cheaper without
            lying about evidence.
          </Para>

          <Para>
            The lazy build is straightforward. An LLM. A set of tools, one
            per source. A planner. Each turn the model decides which tool
            to call, calls it, reads the result, appends it to context,
            picks the next tool.
          </Para>

          <Para>Here is the part that surprised me.</Para>

          <Para>
            A guy named Tianpan walked the math in April. Ten-step agent
            loop on Claude Sonnet, naively appending tool results,
            accumulates roughly{" "}
            <strong>472,000 input tokens</strong> by the final turn. That
            is a 43x multiplier on a single-call cost estimate. The growth
            is quadratic. Every tool call inflates the context that every
            later call has to pay to read again. It looks linear on the
            whiteboard and is not.
          </Para>

          <Para>
            Plug in Sonnet pricing at $3.30 per million input. A
            medium-complexity case. Forty thousand input tokens of
            replayed context across the loop plus prompts plus reasoning
            plus the final brief. Roughly thirty cents per investigation,
            just at the model.
          </Para>

          <Para>
            At ten thousand disputes a month (a small fintech), $3,000 of
            pure inference. At a hundred thousand, $30,000. Before
            infrastructure. Before the human reviewers we still need on
            the high-stakes cases. Before salaries. Before margin.
          </Para>

          <Para>
            The first AI-native services companies were sold on
            capability. The second wave gets sold on outcomes. The wave
            that survives is the one that has solved the token cost
            problem at the architecture, not at the model.
          </Para>

          <Para>
            This is the part demos never show. The models are fine. They
            were fine in 2024. The agents work. The infrastructure under
            them was designed for chatbots that took one turn and forgot,
            and we are running services on it.
          </Para>

          {/* SECTION 3 */}
          <Figure
            src="/blog/03-substrate.webp"
            alt="Editorial illustration: a coral-tree structure at center, six muted earth-tone ribbons feeding in from the left, a single clean amber line exiting to the right"
            caption="One query language. Provenance baked in. Tokens spent on reasoning, not protocol."
          />

          <H2>Why we bet on Coral, and not on better tool wiring.</H2>

          <Para>
            When we started Manthan I almost did exactly what every team
            in this category does. Wire up Stripe through the SDK. Wire
            up HubSpot through the SDK. Wire up Notion. Wire up Slack.
            Give each tool to the model. Let the planner figure it out.
          </Para>

          <Para>
            We did the back-of-envelope cost math one Sunday in March and
            stopped.
          </Para>

          <Para>
            The path we took instead is built on{" "}
            <a
              href="https://coralprotocol.org"
              target="_blank"
              rel="noreferrer"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              Coral Protocol
            </a>
            . The piece that matters: Coral exposes every connected source
            through a single SQL-shaped MCP layer. Stripe is a table.
            HubSpot is a table. Notion pages are a table. The agent does
            not have to learn three vocabularies and remember which API
            takes a <code>customer_id</code> and which takes an{" "}
            <code>account.id</code>. It learns one query language.
          </Para>

          <Para>
            In the language of someone reading their P&L: instead of eight
            tool calls, each carrying the full prior context, the agent
            issues four joins. Instead of forty thousand input tokens of
            replayed context, it gets back typed rows with provenance
            attached. Every claim in the final brief cites a real source
            record. A Stripe dispute id. A HubSpot company id. A Notion
            page id. Click the citation, the underlying record opens in a
            new tab. Nothing gets fabricated because nothing leaves the
            data store as prose.
          </Para>

          <PullQuote>
            Most of what people say about Coral on Twitter sounds like an
            MCP registry pitch and undersells the architectural part.
          </PullQuote>

          <Para>
            The architectural part is a discipline. Agents communicate in
            structured queries and typed results. Tokens get spent on the
            reasoning, not on the protocol. The Coral team published
            their Anemoi reference implementation against GAIA last year
            and beat the OWL baseline by nine points by specifically
            cutting redundant token passing between planner and worker.
            The benchmark number is interesting. The architectural
            pattern matters more.
          </Para>

          <Para>
            You can see the same idea converging from a half-dozen other
            places this year. Bijit Ghosh's November piece on Medium
            framed it as "stop dumping every tool definition into the
            agent's memory like a messy desk drawer." Apollo's GraphQL
            MCP team titled their writeup "Every Token Counts." The
            CodeAgents paper out of arxiv this summer proposed typed
            variables and reusable subroutines as the unlock. The field
            has decided. The next decade of agentic systems will be won
            by the teams that stop treating tokens as free.
          </Para>

          <Para>
            Coral is the most production-ready substrate for that posture
            today. It is not the only path. The moment you decide your
            AI-native service company has to live longer than its seed
            round, you need an answer of this shape, and Coral is
            shipping one.
          </Para>

          {/* SECTION 4 */}
          <H2>How we actually built Manthan on top of it.</H2>

          <Para>
            The code is open at{" "}
            <a
              href="https://github.com/akash-mondal/manthan"
              target="_blank"
              rel="noreferrer"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              github.com/akash-mondal/manthan
            </a>
            . The deployed product is{" "}
            <Link
              to="/"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              manthan.quest
            </Link>
            . Below is the engineering rationale, no code. If you want
            the receipts they are in the repo.
          </Para>

          <H3>Evidence over strings.</H3>
          <Para>
            Every tool call we make returns an Evidence object. Source.
            Table. Record id. Fields. The SQL that produced it. A
            timestamp. The model never sees a raw row as prose. It sees a
            typed wrapper with provenance baked in. When the agent
            records a finding, the finding cites Evidence by index. The
            model never has to remember which Stripe charge it was,
            because the citation is structural. No second tool call to
            recover what was already retrieved. No prose "Stripe says…"
            the model has to disambiguate. Across a typical investigation
            that saves two or three turns.
          </Para>

          <H3>One Coral session per case.</H3>
          <Para>
            The Coral MCP context binds to the case at the start of the
            agent loop and tears down at the end. Tools are not redefined
            turn to turn. The agent does not pay tokens to re-read the
            catalogue every step. We did this even though it is more
            plumbing than the obvious approach, because the alternative
            is a flat 5k token tax per turn for a meaningful tool
            surface. Times ten thousand cases a month.
          </Para>

          <H3>Citations resolved at emit time, not at render time.</H3>
          <Para>
            When the agent records a finding, the Evidence index it cites
            is resolved to its full structured shape inside the agent
            loop. The brief PDF, the Slack card, the email body, all
            three downstream surfaces, never need to re-query Coral to
            assemble the brief. The data they need is already on the
            event. One write, many reads, zero additional model spend.
          </Para>

          <H3>The HITL gate is policy, not prompt.</H3>
          <Para>
            Whether a case auto-fires, needs one click, or requires
            two-person approval is a deterministic function of the typed
            decision payload. Computed by Python. The model never burns
            tokens deciding "is this a $50 case or a $50,000 case." It
            writes a typed decision. The gate evaluates it. Sounds boring
            until you realise a 5,000 token reasoning chain about HITL
            thresholds was happening before, on every case.
          </Para>

          <H3>The event log is the source of truth, state is derived.</H3>
          <Para>
            This is the 12-Factor Agents pattern. Every meaningful change
            is an event. The case row, the findings table, the actions
            table, all projections of events. We never ask the model to
            reconstruct what happened by replaying its context. The state
            is queryable in SQL, by humans, after the fact, without an
            LLM in the loop. Auditors love it. Token bills love it more.
          </Para>

          <Para>
            Each of those choices is the same choice in different
            clothing. Do not let the model do work the architecture
            should do. Let it reason. Let infrastructure handle
            communication. Let policy handle decision gates. Let the
            database hold history.
          </Para>

          <Para>
            This is what building for an AI-native service company
            actually means in 2026. Not "use the best model." Build an
            architecture that earns its margin back from communication
            discipline. Coral makes that posture tractable today.
          </Para>

          {/* SECTION 5 */}
          <Figure
            src="/blog/04-conviction.webp"
            alt="A single silhouetted figure on a vast bone-colored plain at dusk, looking toward a horizon scattered with small amber lantern glows"
            caption="There will be a hundred Manthans. Each one a distant light."
          />

          <H2>The conviction.</H2>

          <Para>
            There are going to be a hundred Manthans. One per service
            vertical. Insurance claims investigations. Tax filing review.
            Vendor onboarding. KYC. Regulatory submissions. Healthcare
            prior authorization. Audit packet assembly. Compliance
            attestation. Vendor due diligence. The economics will look
            identical to ours. Cross-system investigation. Typed
            verdict. Structured action. Human attestation on the
            high-stakes ones, autonomous on the obvious ones.
          </Para>

          <Para>The category is real. Gustaf is loud about it for a reason.</Para>

          <Para>
            The companies that win this category will not be the ones
            with the cleverest agents. The model is already a commodity.
            They will be the ones with the leanest communication. The
            ones who can deliver $50 of human work for thirty cents of
            inference, reliably, with citations a CFO can defend.
          </Para>

          <Para>
            If you are building one of these companies right now, my
            unsolicited advice is the same advice we gave ourselves four
            weeks ago when we tore down the first version and started
            over.
          </Para>

          <Para>
            Do not start with the agent loop. Start with the data layer.
            Make every source look like one query language. Make every
            fact carry its own provenance. Make the model the brain, not
            the bus. Keep the human in the gate, not in the loop.
          </Para>

          <Para>
            Coral is the easiest way to do this today. If you are
            building in this category and you have not looked at it
            seriously, you are leaving margin on the table you will not
            get back later.
          </Para>

          <PullQuote>
            The category is here. The architecture is the moat.
          </PullQuote>

          <Para>
            We are at{" "}
            <Link
              to="/"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              manthan.quest
            </Link>
            . The code is at{" "}
            <a
              href="https://github.com/akash-mondal/manthan"
              target="_blank"
              rel="noreferrer"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              github.com/akash-mondal/manthan
            </a>
            . The dispute Manthan was built to handle is one of a hundred
            problems shaped like this. Pick yours. Use Coral. Earn the
            margin.
          </Para>

          {/* Author / about block */}
          <div
            style={{
              marginTop: 64,
              paddingTop: 32,
              borderTop: "1px solid rgba(255,255,255,0.10)",
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              fontSize: 16,
              lineHeight: 1.6,
              color: "oklch(0.65 0.006 75)",
              letterSpacing: "-0.002em",
            }}
          >
            Akash Mondal builds Manthan, an AI-native operations layer
            for revenue disputes. Coral Protocol is at coralprotocol.org.
            If you read this far and want to argue,{" "}
            <a
              href="mailto:akash@manthan.quest"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
                fontStyle: "normal",
              }}
            >
              akash@manthan.quest
            </a>
            .
          </div>

          {/* Bottom nav */}
          <div
            style={{
              marginTop: 56,
              display: "flex",
              flexDirection: "row",
              flexWrap: "wrap",
              gap: 14,
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <Link
              to="/blog"
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 11,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "oklch(0.65 0.006 75)",
                textDecoration: "none",
              }}
            >
              ← Back to blog
            </Link>
            <a
              href="https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fmanthan.quest%2Fblog%2Ftokens-are-the-new-salary"
              target="_blank"
              rel="noreferrer"
              style={{
                fontFamily: "Geist Mono, ui-monospace, monospace",
                fontSize: 11,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "oklch(0.65 0.006 75)",
                textDecoration: "none",
              }}
            >
              Share on LinkedIn →
            </a>
          </div>
        </motion.article>
      </main>

      {/* Footer */}
      <footer
        className="px-6 md:px-12 lg:px-20 py-10 border-t flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
        style={{ borderColor: "rgba(255,255,255,0.08)" }}
      >
        <div className="flex items-center gap-2.5">
          <Logo size={20} showWordmark={false} className="text-white" />
          <span
            className="font-mono"
            style={{ fontSize: 12, color: "oklch(0.55 0.006 75)" }}
          >
            © {new Date().getFullYear()} Manthan. All rights reserved.
          </span>
        </div>
        <div className="flex items-center gap-5 text-sm">
          {[
            { label: "Blog", to: "/blog" },
            { label: "Privacy", to: "/privacy" },
            { label: "Terms", to: "/terms" },
            { label: "Contact", to: "/contact" },
          ].map((l) => (
            <Link
              key={l.to}
              to={l.to}
              style={{ color: "oklch(0.65 0.006 75)" }}
            >
              {l.label}
            </Link>
          ))}
        </div>
      </footer>
    </div>
  );
}
