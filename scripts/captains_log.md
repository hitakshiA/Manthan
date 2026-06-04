# Tokens are the new salary.

### Uber burned its 2026 AI budget in four months. The next hundred AI-native service companies will hit the same wall. Here is the bet we made on Coral that we think survives it.

---

> Cover image: `manthan-ui/public/blog/01-cover-many-to-one.webp`

---

In April, Uber's CTO admitted to *The Information* that the company had burned through its entire 2026 AI coding tools budget in four months. Engineering leaderboards. Public ranking of who used the tools most. The tools worked. Then the bill came in.

I read that piece in the back of a Bangalore Uber, which felt about right.

Microsoft is scaling back internal AI use over the same surprise. ServiceNow flagged AI cost-of-revenue compression on its January call, first time the company has used that phrase. Deloitte's Q4 2025 enterprise report found teams discovering "tens of millions" of monthly bills from agentic loops they had quietly shipped six months earlier. Gartner says forty percent of agentic projects will be killed by 2027. Not because the AI is bad. Because the unit economics inverted before the founder had time to refactor.

The industry has a name for this now. Token tsunamis.

That is the room in which Y Combinator's Gustaf Alströmer dropped his Summer 2026 Request for Startups, where "AI-Native Service Companies" sits at category number one of fifteen. The argument is short and obviously right. Global spend on services is much larger than software. Most of those services are already outsourced. AI agents can do the actual work, not assist it. Insurance brokerage. Accounting. Audit. Healthcare admin. Compliance. Replace the service. Sell the outcome. Stop shipping tools.

Every founder reading that RFS understood the opportunity.

Far fewer noticed what it requires you to survive.

---

> Inline image: `manthan-ui/public/blog/02-the-bill.webp`

### The economics of doing the work yourself

We build Manthan, which sits in one of those YC-shaped corners: revenue disputes. A typical investigation crosses six to eight systems. Stripe for the charge. HubSpot for the customer. Notion for whichever refund policy somebody wrote in 2024 and forgot. Datadog for the outage timeline. Intercom for the email the customer sent before they filed the dispute. Slack for the engineer who admitted in #incidents that yeah we did have a bad afternoon. PostHog for whether the customer actually used the feature they say was broken. Zendesk for the ticket nobody answered.

Each system holds one piece. The agent has to read all of them to write something a finance lead would sign off on. That is the work. That is what a senior controller did before. That is what an AI-native company has to do faster and cheaper without lying about evidence.

The lazy build is straightforward. An LLM. A set of tools, one per source. A planner. Each turn the model decides which tool to call, calls it, reads the result, appends it to context, picks the next tool.

Here is the part that surprised me.

A guy named Tianpan walked the math in April. Ten-step agent loop on Claude Sonnet, naively appending tool results, accumulates roughly 472,000 input tokens by the final turn. That is a 43x multiplier on a single-call cost estimate. The growth is quadratic. Every tool call inflates the context that every later call has to pay to read again. It looks linear on the whiteboard and is not.

Plug in Sonnet pricing at $3.30 per million input. A medium-complexity case. Forty thousand input tokens of replayed context across the loop plus prompts plus reasoning plus the final brief. Roughly thirty cents per investigation, just at the model.

At ten thousand disputes a month (a small fintech), $3,000 of pure inference. At a hundred thousand, $30,000. Before infrastructure. Before the human reviewers we still need on the high-stakes cases. Before salaries. Before margin.

The first AI-native services companies were sold on capability. The second wave gets sold on outcomes. The wave that survives is the one that has solved the token cost problem at the architecture, not at the model.

This is the part demos never show. The models are fine. They were fine in 2024. The agents work. The infrastructure under them was designed for chatbots that took one turn and forgot, and we are running services on it.

---

> Inline image: `manthan-ui/public/blog/03-substrate.webp`

### Why we bet on Coral, and not on better tool wiring

When we started Manthan I almost did exactly what every team in this category does. Wire up Stripe through the SDK. Wire up HubSpot through the SDK. Wire up Notion. Wire up Slack. Give each tool to the model. Let the planner figure it out.

We did the back-of-envelope cost math one Sunday in March and stopped.

The path we took instead is built on Coral Protocol. The piece that matters: Coral exposes every connected source through a single SQL-shaped MCP layer. Stripe is a table. HubSpot is a table. Notion pages are a table. The agent does not have to learn three vocabularies and remember which API takes a `customer_id` and which takes an `account.id`. It learns one query language.

In the language of someone reading their P&L: instead of eight tool calls, each carrying the full prior context, the agent issues four joins. Instead of forty thousand input tokens of replayed context, it gets back typed rows with provenance attached. Every claim in the final brief cites a real source record. A Stripe dispute id. A HubSpot company id. A Notion page id. Click the citation, the underlying record opens in a new tab. Nothing gets fabricated because nothing leaves the data store as prose.

Most of what people say about Coral on Twitter sounds like an MCP registry pitch and undersells the architectural part. The architectural part is a discipline. Agents communicate in structured queries and typed results. Tokens get spent on the reasoning, not on the protocol. The Coral team published their Anemoi reference implementation against GAIA last year and beat the OWL baseline by nine points by specifically cutting redundant token passing between planner and worker. The benchmark number is interesting. The architectural pattern matters more.

You can see the same idea converging from a half-dozen other places this year. Bijit Ghosh's November piece on Medium framed it as "stop dumping every tool definition into the agent's memory like a messy desk drawer." Apollo's GraphQL MCP team titled their writeup "Every Token Counts." The CodeAgents paper out of arxiv this summer proposed typed variables and reusable subroutines as the unlock. The field has decided. The next decade of agentic systems will be won by the teams that stop treating tokens as free.

Coral is the most production-ready substrate for that posture today. It is not the only path. The moment you decide your AI-native service company has to live longer than its seed round, you need an answer of this shape, and Coral is shipping one.

---

### How we actually built Manthan on top of it

The code is open at github.com/akash-mondal/manthan. The deployed product is manthan.quest. Below is the engineering rationale, no code. If you want the receipts they are in the repo.

**Evidence over strings.** Every tool call we make returns an Evidence object. Source. Table. Record id. Fields. The SQL that produced it. A timestamp. The model never sees a raw row as prose. It sees a typed wrapper with provenance baked in. When the agent records a finding, the finding cites Evidence by index. The model never has to remember which Stripe charge it was, because the citation is structural. No second tool call to recover what was already retrieved. No prose "Stripe says…" the model has to disambiguate. Across a typical investigation that saves two or three turns.

**One Coral session per case.** The Coral MCP context binds to the case at the start of the agent loop and tears down at the end. Tools are not redefined turn to turn. The agent does not pay tokens to re-read the catalogue every step. We did this even though it is more plumbing than the obvious approach, because the alternative is a flat 5k token tax per turn for a meaningful tool surface. Times ten thousand cases a month.

**Citations resolved at emit time, not at render time.** When the agent records a finding, the Evidence index it cites is resolved to its full structured shape inside the agent loop. The brief PDF, the Slack card, the email body, all three downstream surfaces, never need to re-query Coral to assemble the brief. The data they need is already on the event. One write, many reads, zero additional model spend.

**The HITL gate is policy, not prompt.** Whether a case auto-fires, needs one click, or requires two-person approval is a deterministic function of the typed decision payload. Computed by Python. The model never burns tokens deciding "is this a $50 case or a $50,000 case." It writes a typed decision. The gate evaluates it. Sounds boring until you realise a 5,000 token reasoning chain about HITL thresholds was happening before, on every case.

**The event log is the source of truth, state is derived.** This is the 12-Factor Agents pattern. Every meaningful change is an event. The case row, the findings table, the actions table, all projections of events. We never ask the model to reconstruct what happened by replaying its context. The state is queryable in SQL, by humans, after the fact, without an LLM in the loop. Auditors love it. Token bills love it more.

Each of those choices is the same choice in different clothing. Do not let the model do work the architecture should do. Let it reason. Let infrastructure handle communication. Let policy handle decision gates. Let the database hold history.

This is what building for an AI-native service company actually means in 2026. Not "use the best model." Build an architecture that earns its margin back from communication discipline. Coral makes that posture tractable today.

---

> Inline image: `manthan-ui/public/blog/04-conviction.webp`

### The conviction

There are going to be a hundred Manthans. One per service vertical. Insurance claims investigations. Tax filing review. Vendor onboarding. KYC. Regulatory submissions. Healthcare prior authorization. Audit packet assembly. Compliance attestation. Vendor due diligence. The economics will look identical to ours. Cross-system investigation. Typed verdict. Structured action. Human attestation on the high-stakes ones, autonomous on the obvious ones.

The category is real. Gustaf is loud about it for a reason.

The companies that win this category will not be the ones with the cleverest agents. The model is already a commodity. They will be the ones with the leanest communication. The ones who can deliver $50 of human work for thirty cents of inference, reliably, with citations a CFO can defend.

If you are building one of these companies right now, my unsolicited advice is the same advice we gave ourselves four weeks ago when we tore down the first version and started over.

Do not start with the agent loop. Start with the data layer. Make every source look like one query language. Make every fact carry its own provenance. Make the model the brain, not the bus. Keep the human in the gate, not in the loop.

Coral is the easiest way to do this today. If you are building in this category and you have not looked at it seriously, you are leaving margin on the table you will not get back later.

We are at manthan.quest. The code is at github.com/akash-mondal/manthan. The dispute Manthan was built to handle is one of a hundred problems shaped like this. Pick yours. Use Coral. Earn the margin.

The category is here. The architecture is the moat.

---

*Akash Mondal builds Manthan, an AI-native operations layer for revenue disputes. Coral Protocol is at coralprotocol.org. If you read this far and want to argue, akash@manthan.quest.*

---

## ─────────────────────────────────────────
## Companion atomic posts (pillar-to-post strategy)
## ─────────────────────────────────────────

The article above is the pillar. Once you publish it, run five short native LinkedIn posts over two weeks. Each one pulls one strong point and links back in the first comment. LinkedIn penalises outbound links in the body. First-comment is the workaround.

### Post 1 (T+0). The Uber hook.

> Uber burned its entire 2026 AI tools budget in four months.
>
> The CTO confirmed it to The Information in April.
>
> Microsoft is scaling back internal AI use over the same surprise. ServiceNow flagged AI cost-of-revenue compression on its January earnings call, first time the company has used that phrase. Gartner says forty percent of agentic AI projects will be killed by 2027 because of cost overruns alone.
>
> I just wrote up what we think the next wave of AI-native services companies (the YC Summer 2026 RFS category number one) actually need to survive this.
>
> Spoiler: not a better model.
>
> Link in first comment.

### Post 2 (T+2). The quadratic math.

> Ten-step agent loop on Claude Sonnet equals 472,000 input tokens.
>
> That is a 43x cost multiplier over a single-call estimate.
>
> Quadratic, not linear. Every tool call inflates the context that every later call has to pay to read again.
>
> Most teams I know building agents this year have the same story. The demo works. The unit economics invert. They run out of runway before they can refactor.
>
> The fix is not inside the agent loop. The fix is the substrate underneath. Full write-up in the first comment.

### Post 3 (T+4). The 8-slide carousel.

A portrait carousel (1080x1350) using the four blog illustrations as anchors. Eight slides total.

> Slide 1: Title card. "Tokens are the new salary." Use the cover illustration as the background.
> Slide 2: The numbers. Uber, ServiceNow, Klarna, Gartner.
> Slide 3: The quadratic curve. Words, not a chart.
> Slide 4: The YC RFS. "AI has stopped being a feature."
> Slide 5: The naive build. What every team does wrong on the first try.
> Slide 6: Coral as substrate. Use the substrate illustration here.
> Slide 7: The five engineering choices that compound (one bullet each).
> Slide 8: Closer. Link in comments. Use the conviction illustration.

### Post 4 (T+7). The contrarian opinion.

> Most AI-native services companies are going to fail.
>
> Not because the AI is not good enough. The AI is fine.
>
> They will fail because they shipped an agent loop on top of a stack designed for chatbots and went to production before doing the unit economics math.
>
> Then the bill comes in.
>
> The win condition for this category is not the smartest agent. It is the cheapest one to run per case, at scale, on real traffic, with audit-grade citations.
>
> Manthan has been built that way since day one. The long-form on how is in the first comment.

### Post 5 (T+11). The personal receipt.

> We sat down one Sunday in March and did the back-of-envelope cost math on what we had built so far.
>
> What we had: an agent loop wired to Stripe, HubSpot, Notion, and three other vendors via SDKs. It worked on demos. Production cost model: a $30,000-a-month inference bill at our target customer scale.
>
> Inference. Not infrastructure. Not salaries. Just talking to the model.
>
> We started over on Coral the following Monday. The rewrite took two weeks. The per-investigation token spend dropped 70 to 80 percent. The brief got cleaner because every claim now cites a real record. The audit story got real because the event log became the source of truth.
>
> If you are building in the AI-native services category, this is the bet to make right now. The model is the commodity. The substrate is the moat.
>
> Full essay: link in comments.

---

## ─────────────────────────────────────────
## Pre-publish checklist
## ─────────────────────────────────────────

1. Cover image at `manthan-ui/public/blog/01-cover-many-to-one.webp`. Three inline images in the same folder. All four 1600x894 WebP, total 138 KB. Locked-style-anchor pipeline at `scripts/gen_blog_images.py` if any need re-generating.

2. Canonical URL on the product: stand up `/blog/tokens-are-the-new-salary` on manthan.quest so we own the SEO before LinkedIn indexes the Article. Cross-link both ways.

3. Cross-publish: LinkedIn Article uses the same body. Substack mirror if Akash wants newsletter momentum.

4. Image dimensions: cover renders at 1200x630 in LinkedIn's Article preview. Our 1600x894 is generously oversized which is fine. The central 1200x630 region of every image holds the moral subject already.

5. First-comment link strategy is non-optional on every native post. LinkedIn explicitly penalises outbound links in the post body.

6. Tag with intent, not as lottery. Coral Protocol's official account. Y Combinator. Gustaf Alströmer (he engages with real RFS responses). Authors of cited sources where you can find them.

7. Time of post matters more than people admit. Tuesday-Thursday morning Pacific is the standard window for B2B founder content. Friday afternoon is the graveyard.
