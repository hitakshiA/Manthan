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
            <span>By Hitakshi</span>
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
            I read that piece in the back of an Uber, which felt about
            right.
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
            Plug in Claude Sonnet 4.6 at the current $3.00 per million
            input. That ten-step naive loop is{" "}
            <strong>$1.42 per investigation</strong> on inference alone.
            On Opus 4.7 (the model most teams default to for agentic
            work) it is closer to $2.40. At a small fintech doing ten
            thousand disputes a month that is fourteen to twenty-four
            thousand dollars of inference. At a hundred thousand it is
            a hundred and forty to two hundred and forty thousand.
            Before infrastructure. Before the human reviewers we still
            need on the high-stakes cases. Before salaries. Before
            margin.
          </Para>

          <Para>
            The same case on a disciplined build (Coral-shaped, what
            we'll get to in a second) lands at roughly forty cents
            instead of $1.42. Not because the model is cheaper. Because
            the architecture spends fewer tokens on the protocol and
            more on the reasoning.
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
            In the language of someone reading their P&L: instead of
            eight tool calls each carrying the full prior context, the
            agent issues a handful of focused queries (one within-Stripe
            JOIN, one per other connected source) and gets back typed
            rows with provenance attached. Every claim in the final
            brief cites a real source record. A Stripe dispute id. A
            HubSpot company id. A Notion page id. Click the citation,
            the underlying record opens in a new tab. Nothing gets
            fabricated because nothing leaves the data store as prose.
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
              href="https://github.com/hitakshiA/Manthan"
              target="_blank"
              rel="noreferrer"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              github.com/hitakshiA/Manthan
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
            . Below is the engineering rationale. No code. If you want
            the receipts they are in the repo, file paths and all.
          </Para>

          <H3>One Coral session per case, spawned as a stdio subprocess.</H3>
          <Para>
            The Coral integration is sixty lines in{" "}
            <code>agent/coral_session.py</code>. It spawns{" "}
            <code>coral mcp-stdio</code> as a subprocess for the case,
            yields an MCP ClientSession, binds it to a Python{" "}
            <code>contextvars.ContextVar</code>, then resets the
            contextvar when the case ends. The per-tool handlers in{" "}
            <code>agent/tools.py</code> dispatch through that contextvar
            instead of being passed the session as an argument. The
            subprocess dies with the session. No pool. No warm-up cache.
            No shared-session optimisation. The simplicity is the
            feature.
          </Para>

          <H3>Six tools. Three of them write. That is the entire agent surface.</H3>
          <Para>
            Read-only:{" "}
            <code>coral_sql</code>, <code>coral_list_catalog</code>,{" "}
            <code>coral_describe_table</code>. State-changing or
            terminal: <code>record_finding</code>,{" "}
            <code>ask_human</code>, <code>conclude</code>. There is no{" "}
            <code>stripe_get_charge</code>, no{" "}
            <code>hubspot_search_company</code>, no{" "}
            <code>notion_fetch_page</code>. The agent reaches all thirty
            connected sources through one call:{" "}
            <code>coral_sql</code>. It learns Stripe, HubSpot, Notion,
            Datadog as schemas in a catalog. The mental load on the
            model is one query language, not thirty REST APIs.
          </Para>

          <H3>Discover, then query.</H3>
          <Para>
            The catalog is not baked into the system prompt. The first
            thing the agent does on a new case is{" "}
            <code>coral_list_catalog()</code> to see which schemas are
            present for that org's connections, then{" "}
            <code>coral_describe_table()</code> only for tables whose
            columns it does not already know. That is how we keep the
            system prompt from carrying thirty source-schemas worth of
            dead context every turn. The agent reads what it needs.
          </Para>

          <H3>Evidence wraps every read.</H3>
          <Para>
            Each <code>coral_sql</code> call returns rows wrapped in an
            Evidence object: source, table, record_id, fields, query,
            retrieved_at. The Python handler parses the MCP JSON once,
            normalises into rows + columns, and tags the Evidence with
            which sources the SQL touched (one regex in tools.py finds{" "}
            <code>schema.table</code> patterns). The LLM never sees the
            raw row as prose. It sees a typed ToolResult whose data
            payload includes an <code>evidence_indices</code> array
            pointing into the Evidence pool. That pool is what citations
            resolve against.
          </Para>

          <H3>Findings cite Evidence by index, resolved at emit time.</H3>
          <Para>
            When the agent calls{" "}
            <code>record_finding(citations=[1, 3, 5])</code>, the loop
            in <code>agent/loop.py</code> resolves those indices to{" "}
            <code>{`{source, table, record_id}`}</code> dicts inside the
            same turn, using <code>executor.evidence[idx]</code>. The
            brief PDF, the Slack card, and the case-detail UI all read
            the resolved citations from the finding event. Three
            downstream surfaces, zero additional Coral queries to
            assemble the brief.
          </Para>

          <H3>Tools are exposed with constrained decoding.</H3>
          <Para>
            <code>_enforce_strict()</code> in tools.py walks every
            Pydantic JSON schema and adds{" "}
            <code>additionalProperties: false</code> to every nested
            object, marks every property required, uses null unions for
            optionals. The OpenRouter client carries the{" "}
            <code>structured-outputs-2025-11-13</code> header. The model
            literally cannot emit a malformed tool call. Sounds small.
            Most teams I have talked to are still burning turns on
            retry-bad-JSON loops. We just stopped paying for that.
          </Para>

          <H3>Reflexion every three steps, anti-padding.</H3>
          <Para>
            Defined in <code>prompts.REFLEXION</code>. Every third ReAct
            step the model classifies the run as one of CONVERGING /
            GAP / CONTRADICTION / THIN_FINDINGS / SATURATED / STUCK. The
            branch that saves the most tokens is THIN_FINDINGS:{" "}
            <em>
              "if you have a fat row but only 2 findings recorded, walk
              the column groups and emit one Finding per group from the
              row you already have. Do NOT issue a new coral_sql."
            </em>{" "}
            The agent's natural failure mode is shallow extraction and
            over-querying to compensate. Reflexion catches it before
            the bill does.
          </Para>

          <H3>The HITL gate is a JSON DSL evaluated in Python.</H3>
          <Para>
            <code>services/policy.py:evaluate_for_case()</code> pulls
            enabled rules in priority order and evaluates conditions
            against a flat context dict. Conditions are{" "}
            <code>{`{"all": [...], "any": [...], "not": ...}`}</code>{" "}
            with leaf clauses like{" "}
            <code>
              {`{"case.amount_minor": {"lte": 20000}}`}
            </code>
            . Pure Python. No LLM. The model emits a typed decision
            payload at <code>conclude()</code>; the gate evaluates it;
            the case routes to auto / one-click / two-person. The model
            never burns tokens deciding whether a $50 case auto-fires
            or a $50K case needs a second signer.
          </Para>

          <H3>The event log is the source of truth.</H3>
          <Para>
            This is the 12-Factor Agents pattern. The agent loop yields
            Event objects from <code>run_case()</code>; the investigate
            worker in{" "}
            <code>manthan-api/workers/investigate.py</code> mirrors
            every event into the Postgres <code>events</code> table,
            then projects into <code>cases</code>,{" "}
            <code>findings</code>, <code>actions</code>. Nothing about
            case state is reconstructed by the LLM. The audit trail is
            queryable in SQL by humans. The brief PDF is generated from
            events. The Slack card is generated from events. A case can
            be replayed by reading its event log without re-running the
            agent.
          </Para>

          <Para>
            Each one of those choices is the same choice in different
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
              href="https://github.com/hitakshiA/Manthan"
              target="_blank"
              rel="noreferrer"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              github.com/hitakshiA/Manthan
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
            Hitakshi builds Manthan, an AI-native operations layer for
            revenue disputes. Coral Protocol is at coralprotocol.org. If
            you read this far and want to argue,{" "}
            <a
              href="mailto:hitakshi220@gmail.com"
              style={{
                color: "#C97B2A",
                textDecoration: "underline",
                textUnderlineOffset: 3,
                fontStyle: "normal",
              }}
            >
              hitakshi220@gmail.com
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
