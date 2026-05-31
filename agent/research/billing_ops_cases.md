# Manthan Eval Scenario Research: 20 Real Billing-Ops Pain Points

Research synthesis grounded in Hacker News, Stripe / Visa / Mastercard official
documentation, RevOps and CS practitioner publications, and 2025–2026 SaaS
billing benchmarks.

This file is the **scenario-design source of truth** for the Manthan agent.
Each case below maps to one or more eval scenarios under `eval/scenarios/`.
Don't paraphrase the public sources when seeding source data - quote or use
the patterns described so the scenarios stay grounded.

---

## CHARGEBACKS (4)

### 1. friendly-fraud-saas-annual-non-refundable

**Public source:** [Terms.Law forum thread](https://terms.law/forum/thread/saas-refund-policy-chargebacks.html) - vendor lost a chargeback on a $2,400/year SaaS subscription despite providing "email confirmation, login history, actual usage data" because annual subscription disputes filed mid-term are notoriously hard to defend; settled out-of-band for $1,200.
**Concrete scenario:** Series B horizontal-SaaS vendor; mid-market customer ($2,400/year self-serve annual plan) renews automatically in January, uses the product for 90 days (~40 logins, exported 3 reports), then files a Visa 13.2 "Cancelled Recurring" chargeback claiming they "never agreed to the annual renewal." Customer has a CSM-less account; the only signup record is a Terms checkbox click 13 months ago.
**Why hard:** No human-touch record to anchor authorization. Stripe's automated evidence packet (TOS PDF + login history) is sub-threshold for issuers under Visa 13.2 - they want a renewal-notice email that the customer actually opened, plus the original click-wrap with IP/device match to the disputing card.
**Cross-source evidence required:** `stripe.disputes` JOIN `stripe.customers.metadata` JOIN auth-system (Auth0/WorkOS) device-fingerprint at signup JOIN email-platform (Customer.io/Postmark) renewal-reminder open/click logs JOIN product-DB usage events keyed to the same user_id JOIN the click-wrapped TOS version snapshot.
**Stakes:** $1k–$5k per case, ~50% of disputes lost at this profile, plus the $15 Stripe dispute fee. Counts against the merchant's dispute ratio toward Stripe's 0.75% danger zone ([Chargeblast on 0.75% threshold](https://www.chargeblast.com/blog/stripe-dispute-rate-the-0-75-danger-zone/), [Chargebacks911 SaaS](https://chargebacks911.com/saas-chargebacks/)).
**Existing tool gap:** Stripe Smart Disputes pulls only Stripe-side data - it cannot reach into the email-platform "opened renewal reminder" event or the product's last-30-day usage log, which are the load-bearing pieces of CE3.0 evidence ([Visa CE3.0 docs](https://docs.stripe.com/disputes/api/visa-ce3)).

---

### 2. chargeback-after-platform-outage

**Public source:** [SLA Enforcement (JChangLaw)](https://www.jchanglaw.com/post/sla-enforcement-making-saas-providers-accountable-for-downtime) - describes a recurring pattern where customers experiencing a 6-hour outage during a high-value window receive only a 5% SLA credit but feel entitled to a full refund; chargeback follows. Confirmed in [Stripe status history](https://statusgator.com/services/stripe): 708 Stripe-impacting outages logged in 11 years.
**Concrete scenario:** A mid-market e-commerce platform ($18K ACV, billed quarterly $4,500) experiences a 4hr 12m API outage on Black Friday. The customer's CFO files a Stripe `product_unacceptable` dispute on the most recent quarterly invoice citing "service was unavailable when most needed." Internal evidence is contradictory: Statuspage shows partial outage; PagerDuty shows full P0 for 2h17m; CS already negotiated a 10% SLA credit via Intercom that the CFO didn't see.
**Why hard:** The defense requires reconciling four sources of truth (Statuspage, PagerDuty, internal Slack incident channel, Intercom credit thread), and there's a credit issued - which means a counter-chargeback under Visa 13.6 "Credit Not Processed" can be triggered if the credit hasn't posted yet.
**Cross-source evidence required:** `pagerduty.incidents` JOIN `statuspage.incidents` JOIN `slack.#inc-<id>` resolution-timeline JOIN `intercom.conversations` SLA-credit thread JOIN `stripe.credit_notes` JOIN contract MSA SLA-credit cap clause.
**Stakes:** $1k–$50k per case. Rare (~quarterly for a fast-growing SaaS) but high-NPS-damage; the customer telling other prospects about it is the bigger loss.
**Existing tool gap:** Chargeflow / Justt operate on Stripe + a single dataset. They can't programmatically read PagerDuty incident severity to argue "the outage was on a non-paid SKU" or correlate a Slack post-mortem to the affected customer's specific feature usage.

---

### 3. cancel-attempted-still-charged

**Public source:** [Visa 13.2 reference + Stripe categories doc](https://docs.stripe.com/disputes/categories) and the [HN "madness of SaaS chargebacks" thread](https://news.ycombinator.com/item?id=45248446) - author notes a $10 charge resulted in $43.95 of total cost after fees, with "chances of winning are basically zero" because the customer claims they cancelled.
**Concrete scenario:** SMB SaaS ($79/mo), customer DM's the company's Twitter account on day 12 saying "cancel me," CSM never sees it. Customer assumes cancelled, gets charged on day 30 ($79), then on day 60 ($79), files Visa 13.2 for both. The in-app "Cancel" button works but customer never reached it.
**Why hard:** The off-channel cancellation request (Twitter DM, support email to wrong inbox, in-app chat that escalated then died) doesn't show up in any cancellation-events table. Defending requires proving no cancellation request existed - a negative - across every comms surface the customer might have used.
**Cross-source evidence required:** `app.cancellation_requests` LEFT JOIN `intercom.conversations` LEFT JOIN `twitter.dms` LEFT JOIN `zendesk.tickets` LEFT JOIN `slack-connect.messages` LEFT JOIN `support@.gmail.threads` LEFT JOIN sales/CSM personal-inbox logs. Has to enumerate every possible cancellation surface.
**Stakes:** $79–$2k per case, very common (Code 13.2 is one of the top three SaaS chargeback reasons per [Chargebacks911](https://chargebacks911.com/saas-chargebacks/)). Per-instance loss small; ratio damage is the real cost.
**Existing tool gap:** Stripe Radar can't audit non-Stripe surfaces. Chargebee Retain captures in-app cancellation flow only. Neither can prove a Twitter DM or Slack-Connect cancellation request did or didn't exist.

---

### 4. trial-to-paid-conversion-shock

**Public source:** [Chargebacks911 SaaS](https://chargebacks911.com/saas-chargebacks/) explicitly names "Trial-to-Paid Conversion - Highest risk point in subscription lifecycle"; reinforced by [Paddle's fraud guide](https://www.paddle.com/resources/fraud-in-saas) and [Sixteen Ventures' free trial abuse guide](https://www.sixteenventures.com/free-trial-abuse/).
**Concrete scenario:** Marketing-automation SaaS, $300/mo plan. User signs up for 14-day free trial with card-on-file, abandons after day 3 (1 login), gets converted on day 15. Day 22 they notice the charge, file a Visa 10.4 "Fraud - CNP" claiming unauthorized. Product team's only signup data: email + first-name + the click on a tiny "Start trial - card required" disclosure.
**Why hard:** Win requires CE3.0 evidence: two prior matching transactions 120-365 days old with shared IP/device/email - but a 22-day-old account has zero qualifying history. Defender falls back to the click-wrap, which most issuers under-weight for $300+ amounts.
**Cross-source evidence required:** `stripe.checkout_sessions` JOIN clickwrap version + IP + user-agent JOIN trial-conversion email open/click JOIN product login events JOIN marketing-site capture (Wayback / Heap) of the trial-disclosure copy at the moment of signup.
**Stakes:** $50–$500 per case, very common - represents the largest share of SaaS friendly fraud. Aggregates to high % of total dispute volume and is the #1 dispute-ratio killer for PLG SaaS.
**Existing tool gap:** Stripe Smart Disputes can package the click-wrap but cannot reach into an analytics tool like Heap or a marketing-site CMS like Webflow to retrieve the *exact* trial-disclosure copy in production on the signup date.

---

## FAILED PAYMENTS (4)

### 5. expired-card-on-high-ARR-renewal

**Public source:** [Slicker 2025 benchmarks](https://www.slickerhq.com/resources/blog/2025-failed-payment-recovery-benchmarks-saas-median-47-percent) - "Expired cards: 80-90% recovery potential" but ~3% of any active customer base has a card expire monthly; [Mastercard ABU docs](https://developer.mastercard.com/product/automatic-billing-updater-abu/) note "you can only send one request a day."
**Concrete scenario:** Enterprise SaaS ($48K annual, billed annually upfront). Stripe attempts renewal charge January 12; card expired December 31. Visa Account Updater pushed an update on Jan 4 but the merchant's daily ABU pull failed silently due to a hash-calculation mismatch (LF vs CRLF in the request payload). The renewal fails for "expired_card." First retry is Jan 14 - still failing because the local card-on-file is stale.
**Why hard:** Three different systems disagree about whether the card is current: Stripe (stale), VAU/ABU (updated), issuing bank (live new card). No "this card was updated but the merchant didn't pull it" alert. Customer's CFO is on PTO and won't approve a re-entry.
**Cross-source evidence required:** `stripe.payment_intents.last_payment_error` JOIN ABU/VAU sync logs JOIN customer billing-contact email engagement JOIN Salesforce contact owner JOIN renewal-date in CRM JOIN CSM Slack channel ping history.
**Stakes:** $10k–$250k per renewal, high-MRR concentration risk. Median 52-58% enterprise recovery rate means roughly half of expired-card enterprise renewals require human-touch save.
**Existing tool gap:** Recurly/Maxio retry logic doesn't surface "your ABU sync is broken" as a first-class signal; engineering treats it as cron-job noise, finance never hears about it until renewal day.

---

### 6. insufficient-funds-mid-market-cascade

**Public source:** [Gravy Solutions / Recover Payments](https://recoverpayments.com/involuntary-churn-prevention/) - "approximately 60% of failed recurring payments globally are due to customers not having enough balance"; [Slicker benchmarks](https://www.slickerhq.com/resources/blog/2025-failed-payment-recovery-benchmarks-saas-median-47-percent) confirms insufficient-funds recovery sits at 60-70%.
**Concrete scenario:** SaaS finance tool, $2,400/mo charged 1st of month to a small-agency client. October 1 - insufficient funds (card declined `insufficient_funds`). Default Chargebee retry: T+3, T+5, T+7, T+10. Each retry: another "Sorry, your payment failed" email. By retry #3 the agency owner's CTO replies on Twitter publicly: "stop spamming me, I'm paying you on the 15th when I get paid." 4th retry email goes anyway.
**Why hard:** Tuning the retry cadence to the customer's *actual* payday pattern (which would have recovered the payment on Oct 15 retry #1) requires correlating prior successful-payment timestamps with the current decline. No retry engine examines historical-recovery-day distribution per customer.
**Cross-source evidence required:** Historical `stripe.charges` success timestamps for this customer JOIN bank-decline-reason JOIN customer's prior Intercom comms about cash flow JOIN dunning-email send/open log JOIN any public-mention monitoring (Twitter/LinkedIn).
**Stakes:** $500–$10K MRR per case, very common. Real damage is reputational - these are the customers who tweet about you.
**Existing tool gap:** Chargebee/Recurly retry engines use static cadence + light AI; they can't ingest "the customer publicly complained on Twitter" and pause the dunning sequence, nor reason from prior-cycle paid-on-the-15th history ([Beancount.io on dunning signals](https://beancount.io/blog/2026/04/25/dunning-email-signals-decoding-payment-replies-cash-flow-guide)).

---

### 7. 3ds-sca-challenge-failure-eu

**Public source:** [Chargebee PSD2 docs](https://www.chargebee.com/docs/payments/2.0/others/psd2-sca) - renewals are "exempted from SCA because no customer is present" BUT "issuing bank may demand customer authentication in certain scenarios"; [Maxio's PSD2 guide](https://maxio-chargify.zendesk.com/hc/en-us/articles/5405426338957-PSD2-SCA-and-3DS) confirms this happens unpredictably.
**Concrete scenario:** UK enterprise customer, €15,000 annual renewal on Stripe. Charge processed as MIT (Merchant-Initiated), expecting SCA exemption. Issuer (Barclays) decides to challenge despite the exemption flag; returns `authentication_required`. No customer present to complete the 3DS challenge. Stripe surfaces this as a generic decline; the AR clerk treats it like a normal card failure and resends an invoice email.
**Why hard:** The decline reason hides the structural problem - this requires switching to an on-session re-authentication flow, not a retry. Defaulting to retry produces zero recoveries; calling the customer fixes it in one minute. But triaging which declines need re-auth vs. retry vs. ABU update requires reading Stripe's `next_action` + decline-reason + issuer history together.
**Cross-source evidence required:** `stripe.payment_intents.next_action` JOIN issuer-country JOIN customer-region JOIN prior-SCA-challenge history JOIN MIT/CIT flag JOIN CRM contact mobile-phone availability for live re-auth call.
**Stakes:** $5k–$100k per case, common in EU (rough estimate 5-12% of EU recurring charges per [Payrails](https://www.payrails.com/blog/3ds-friction-vs-security-and-the-customer-experience-trade-off)). High concentration in regulated industries.
**Existing tool gap:** Stripe Billing surfaces "payment failed" with `authentication_required`, but neither Recurly nor Chargebee routes this to a "call the customer for live re-auth" workflow - they retry as if it were a soft decline.

---

### 8. bank-decline-no-customer-notification

**Public source:** [Paddle's payments guide](https://www.paddle.com/blog/6-reasons-for-low-payment-acceptance-in-saas) - "Customers affected by involuntary churn from payment failures may not even be aware there's a problem until services are interrupted." [Visa/Mastercard data](https://www.kaplancollectionagency.com/news/subscription-facts-55-saas-and-b2b-payment-statistics-for-2025/): 15% of recurring payments decline; for every $1 of real fraud, $25 of legitimate payments are wrongly declined.
**Concrete scenario:** B2B HR-tech SaaS, $890/mo charged to a mid-market customer. Charge declines with `do_not_honor` - a generic fraud flag from Chase. Stripe sends merchant a webhook; merchant's dunning engine sends a dunning email to the customer's primary billing contact. That contact is on parental leave; auto-reply goes nowhere. Account suspends on day 18. Customer's HR director discovers it Monday morning when payroll integration breaks.
**Why hard:** Defense requires noticing "primary billing contact email is auto-replying" and rerouting to a backup contact - info that lives in OOO auto-reply parsing or HRIS-detected leave status, not the billing system. Default dunning engines pretend the email was delivered.
**Cross-source evidence required:** Dunning-email bounce/auto-reply parsing JOIN Salesforce backup-billing-contact field JOIN CSM Slack channel last-active JOIN product admin-user list (who else has billing-admin role) JOIN HRIS public-leave signal.
**Stakes:** $1k–$25k MRR per case, uncommon-but-acute. NPS hit is severe - the suspension itself becomes the churn trigger.
**Existing tool gap:** Chargebee's dunning sequence treats "email sent" as success. It cannot parse OOO auto-replies and reroute, nor does it know that the same customer has 4 admin users it could escalate to.

---

## REFUND DISPUTES (3)

### 9. refund-after-policy-window

**Public source:** [Stripe's `credit_not_processed` category](https://docs.stripe.com/disputes/categories) plus [Terms.Law SaaS demand-letter guide](https://terms.law/2025/10/04/saas-demand-letter-guide/) - vendors describe customers demanding refunds outside the stated window then threatening chargeback as leverage.
**Concrete scenario:** Project-management SaaS, $4,800 annual paid upfront on Jan 5. Customer requests full refund on April 18 (day 103) citing "we never really used it." Refund policy: 30-day money-back, then no refund. Usage logs show: 47 logins, 12 projects created, 3 invitations sent - light but not zero usage. CSM, sales rep, and finance disagree on whether to grant the refund. Customer hints at chargeback if denied.
**Why hard:** This is a judgment call requiring synthesis of: (a) what the contract actually says, (b) usage evidence, (c) competitive risk (is this customer about to switch?), (d) financial impact (write-off vs. dispute cost), (e) precedent (what have we done for similar accounts?). No tool surfaces all five together.
**Cross-source evidence required:** Signed order form / clickwrap JOIN product-usage telemetry JOIN CRM competitive-risk notes JOIN CSM Slack thread JOIN prior refund decisions for similar ARR/tenure JOIN finance write-off thresholds.
**Stakes:** $2k–$50k per case, uncommon individually but high decision-fatigue cost. Wrong call = chargeback hit OR setting a precedent that erodes refund policy.
**Existing tool gap:** Chargebee, Maxio, and Stripe Billing all execute refunds - they don't *recommend* whether to grant one given a holistic risk profile. CS teams do this in Slack ad hoc.

---

### 10. multi-seat-partial-refund-mid-cycle

**Public source:** [Ordway proration deep-dive](https://ordwaylabs.com/resources/glossary/what-is-proration/) and [Recurly proration blog](https://recurly.com/blog/prorated-billing-101-what-it-is-and-how-it-works/) - "proration creates some of the most confusing line items in SaaS billing"; both note multi-seat downgrade disputes are common.
**Concrete scenario:** 120-seat SaaS deployment, $15/seat/month = $1,800/mo. Customer rolls off 35 seats on day 14 of a 30-day cycle, expects a $262.50 credit (35 × $15 × 16/30). Billing engine generates a $187.50 credit because it accidentally prorated on 31-day calendar. Customer AP team disputes the next invoice. To make it worse: 3 of the 35 seats were re-added by their admin on day 22 - but those re-additions don't appear in the credit reconciliation.
**Why hard:** Resolving requires reconstructing every seat-event in the cycle (add, remove, re-add) with timestamps, recomputing proration, and explaining each line item back to the AP clerk. The audit trail spans Stripe + the product's admin events + the customer's procurement spreadsheet.
**Cross-source evidence required:** `subscription_items.events` JOIN `stripe.invoice_items.proration` JOIN product admin-event log JOIN customer-side PO/AP context JOIN MSA terms on rolling vs. flat proration.
**Stakes:** $200–$5k per dispute, common in growing B2B SaaS. Cost is mostly AR team time (avg 2–4 hours per disputed invoice).
**Existing tool gap:** Stripe Billing produces line items; it doesn't generate the *narrative* explanation for AP. Maxio's prorated-credit reports require finance to write the email manually.

---

### 11. refund-during-active-trial-extension

**Public source:** [Sixteen Ventures free-trial abuse](https://www.sixteenventures.com/free-trial-abuse/), [2Checkout trial-to-paid conversion guide](https://blog.2checkout.com/the-secret-to-trial-to-paid-conversion-in-saas/) - trial extensions are documented as a high-risk variant where customers' expectations diverge from system state.
**Concrete scenario:** PLG SaaS. Customer's 14-day trial ends; sales extends it by 7 days verbally in a Zoom call. Sales rep updates HubSpot but not the billing system. Day 15: card charged $499. Customer demands refund + extension; sales agrees but rep doesn't process the refund - just extends the trial in admin. Day 22: another $499 charged for the "next month." Customer files chargeback.
**Why hard:** Three systems hold different truths - HubSpot says "trial extended 7 days," Stripe says "active subscription billed monthly," product admin says "trial extended manually." No system records *whose verbal promise* created the discrepancy.
**Cross-source evidence required:** Gong/Zoom call transcript with promise timestamp JOIN HubSpot deal-note JOIN Stripe subscription anchor JOIN product trial-end-date JOIN sales-team Slack #deals channel for context.
**Stakes:** $200–$2k per case, uncommon but corrosive to sales-CS trust. Real cost: account exits angry, badmouths on G2.
**Existing tool gap:** No billing tool reconciles sales-verbal-commitments against the subscription state. Gong has the transcript; Chargebee has the subscription; nothing bridges them.

---

## DUNNING ESCALATIONS (3)

### 12. high-mrr-30-days-past-due-no-csm

**Public source:** [Ledgerup B2B dunning playbook](https://www.ledgerup.ai/resources/dunning-automation-for-b2b-saas-the-2026-playbook) - recommends "for enterprise accounts, the handoff from automation to human outreach happens at day 7." [Quora enterprise late-payments thread](https://www.quora.com/How-do-enterprise-SaaS-companies-deal-with-late-payments) cites $200K outstanding from one mid-sized SaaS analytics firm at any time.
**Concrete scenario:** $9,000/mo enterprise customer ($108K ARR), Net 30, invoice issued March 1, due April 1. April 8: still unpaid. CSM doesn't know - AR clerk has been emailing `ap@customer.com` (a shared inbox); customer's AP is short-staffed and hasn't routed. Day 30 past due: account is auto-flagged for suspension. Suspension would tank an integration the customer's own customers depend on.
**Why hard:** The dunning automation has no awareness that this is a $108K ARR account where suspension causes contagion. AR doesn't know to ping CSM; CSM doesn't know AR is escalating. The decision to suspend vs. wait requires reading ARR + integration-importance + CSM relationship + prior payment history.
**Cross-source evidence required:** `stripe.invoices.status='open'` aged JOIN Salesforce ARR + renewal-date JOIN CSM-owned-accounts JOIN Slack channel for the account JOIN product critical-integration flag JOIN prior-cycle days-to-pay distribution for this customer.
**Stakes:** $50K–$500K ARR exposure per case, common in B2B SaaS (10-15% of enterprise invoices go 30+ days past due per [Ledgerup](https://www.ledgerup.ai/resources/dunning-automation-for-b2b-saas-the-2026-playbook)).
**Existing tool gap:** Chargebee dunning sequences fire by age-only, not by ARR weight or integration-criticality. AR and CS see different dashboards.

---

### 13. customer-ghosted-after-3-emails

**Public source:** [FreshBooks "Ghosted" guide](https://www.freshbooks.com/hub/business-management/client-doesnt-pay), [Mondu B2B unpaid invoice guide](https://www.mondu.ai/blog/b2b-customer-does-not-pay-invoice-tips/) - "half the time that non-responsive contact has moved on or moved to a new role"; ~50% of B2B invoices in the US are overdue with 8% written off.
**Concrete scenario:** Marketing-SaaS, $2,200/mo customer. Dunning emails 1, 2, 3 sent to billing contact - all "delivered" per SendGrid, zero opens. CSM checks LinkedIn: contact left the company 6 weeks ago. Customer's HR didn't update billing-contact in the product admin. Account at day 42 past due. Who's the new contact? No one knows.
**Why hard:** Detecting "this contact left" requires LinkedIn signal correlation, email-engagement zero-open detection, and reverse-lookup of who else at the company has admin access. None of that lives in the billing tool.
**Cross-source evidence required:** Email engagement (zero opens × 3) JOIN LinkedIn job-change signal JOIN product admin-users list at this customer JOIN Apollo/ZoomInfo current-employee lookup JOIN any existing CRM contacts at the same company JOIN Slack-Connect history for related contacts.
**Stakes:** $500–$10K MRR per case, common (per ChurnZero champion-departure data, [51% churn within 12 months](https://churnzero.com/blog/customer-champion-playbook/) when contact leaves). Loss compounds if not caught in 48 hours (only [33% renewal lift](https://churnzero.com/blog/customer-champion-playbook/) if acted on within 48h).
**Existing tool gap:** Chargebee/Recurly assume the billing contact is reachable. Nothing in their stack correlates email-engagement decay × LinkedIn departure × alternate-admin-user availability.

---

### 14. finance-contact-changed-no-handoff

**Public source:** [Ordway "5 dunning mistakes"](https://ordwaylabs.com/blog/mistakes-with-dunning-emails/), [getMaxiq renewal-risk indicators](https://www.getmaxiq.com/blog/renewal-risk-indicators) #5 (Champion Disengagement) and #8 (Billing Friction).
**Concrete scenario:** $35K ARR customer. Their controller leaves end of Q2. New controller starts in July; June invoice sent to old controller's `@customer.com` email - still routes (forwarding rule), but new controller doesn't see it. July invoice also generated, also routed wrong. By August both invoices are 30+ and 60+ days past due. The new controller, when contacted via LinkedIn, says "I never received these - please re-issue with my email."
**Why hard:** Defense involves detecting role change *upstream* of any payment failure: a LinkedIn signal + an email-routing anomaly (delivered but never opened) + a missing replacement in the customer admin. Dunning runs on schedule and doesn't pause for "let me figure out who the new contact is."
**Cross-source evidence required:** LinkedIn role-change feed JOIN email open/engagement decay JOIN Salesforce contact-owner JOIN customer admin list JOIN CRM "champion change" alert JOIN prior 6 months billing-contact stability.
**Stakes:** $20K–$200K ARR per case, common in mid-market. Direct AR delay + indirect renewal risk (compound effect).
**Existing tool gap:** Most billing systems' "customer contacts" field is set-and-forget. No tool detects "this contact has changed roles" automatically.

---

## RENEWAL RISK (4)

### 15. champion-left-no-replacement

**Public source:** [ChurnZero champion playbook](https://churnzero.com/blog/customer-champion-playbook/) - 51% churn risk in 12 months after champion departure, 65% if it's executive-level, 33% renewal lift if acted on within 48 hours.
**Concrete scenario:** $84K ARR SaaS, 18 months of healthy usage. The VP-Marketing who championed the original purchase leaves; their replacement starts 4 weeks later. CSM only discovers this in QBR prep when prepping a slide. Usage in last 30 days has dropped 22%; one power-user account is now inactive (the old VP's). Renewal date is 90 days away.
**Why hard:** Detecting the departure at the right moment requires fusing: LinkedIn change, drop in primary-user activity, fewer logins from leadership-tier seats, drop in feature-X usage (their pet feature), and no replacement-user invite. Single signals fire constantly and are easy to dismiss; the *combination* is the alert.
**Cross-source evidence required:** LinkedIn change feed JOIN product-usage telemetry for the specific user_id JOIN seat-level activity grouped by role JOIN CRM contact-active flag JOIN Slack-Connect engagement decline JOIN email open-rate decline.
**Stakes:** $50K–$1M ARR per case, common. The most leveraged save in B2B SaaS - 48-hour SLA mentioned by ChurnZero.
**Existing tool gap:** Gainsight ingests product data; doesn't ingest LinkedIn. ChartMogul tracks revenue but not stakeholder identity. Most CS tools alert on usage drops but can't say "this drop is because the champion left, not because the team is busy."

---

### 16. product-underutilization-flagged-too-late

**Public source:** [getMaxiq renewal indicators](https://www.getmaxiq.com/blog/renewal-risk-indicators) #1; [SaaSCity Churn Playbook](https://saascity.io/blog/saas-churn-playbook-2026-15-tactics-guide) - "Customer usage typically drops by 41% in the quarter leading up to cancellation"; "High logins, zero outcomes is the most underrated churn signal."
**Concrete scenario:** $40K ARR analytics SaaS. Customer logs in 200+ times/month for 8 months but has produced only 3 dashboards (vs. cohort median of 22). CSM's health-score is "green" because login count is high. T-90 days from renewal: usage dashboard finally shows the "low outcome density" - too late to drive a 90-day adoption push.
**Why hard:** Detecting "alive but valueless" requires defining outcome-events per product feature, benchmarking against cohort, AND being patient enough to flag at 4-6 months out (not 90 days out). Most CS tools optimize the wrong proxy.
**Cross-source evidence required:** Product analytics event-stream (PostHog/Heap/Amplitude) JOIN customer cohort definition JOIN outcome-event taxonomy JOIN CSM QBR notes JOIN renewal-date JOIN contract MSA SLA on adoption commitments.
**Stakes:** $20K–$500K ARR per case, common. The intervention window matters - at T-90 days a save attempt is ~30% successful; at T-180 days it's ~60%.
**Existing tool gap:** Gainsight/Catalyst show usage trend but rarely outcome-event density per feature. ChartMogul doesn't touch product events.

---

### 17. competitor-displacement-attempt

**Public source:** [SaaSCity 2026 playbook](https://saascity.io/blog/saas-churn-playbook-2026-15-tactics-guide), [Dock at-risk customers guide](https://www.dock.us/library/at-risk-customers) - competitor mentions in CRM notes, alternative-vendor security reviews, and RFP language are the leading non-usage churn signal.
**Concrete scenario:** Mid-market customer, $24K ARR sales tool. Their Slack DM history with the AE includes "we're evaluating [Competitor X] for our outbound team" 11 weeks ago. Gong call from 6 weeks ago has competitor name mentioned 4×. Security team at customer requested a SOC 2 from [Competitor X] yesterday (visible in a public LinkedIn post from their VP-IT). No one on the SaaS company's side has connected these dots.
**Why hard:** Each signal is weak alone. Together they're a near-certainty of evaluation. Connecting them requires: Gong transcript NLP, Slack-Connect text-mining, LinkedIn-monitoring of customer's security team, CRM-notes correlation, and inference of competitor identity across all four sources (they may use code names or different phrasings).
**Cross-source evidence required:** Gong calls JOIN Slack-Connect messages JOIN CRM notes JOIN LinkedIn activity from customer-employee accounts JOIN security-questionnaire portal JOIN AE email threads JOIN any G2/TrustRadius review activity from the customer domain.
**Stakes:** $10K–$2M ARR per case, common during procurement-cycle quarters. Window to act: ~30-60 days before renewal.
**Existing tool gap:** Gong does call-side competitor detection. ChartMogul/Gainsight don't ingest LinkedIn or security-portal events. No tool fuses Slack-Connect with CRM notes.

---

### 18. contract-negotiation-paralysis

**Public source:** [TermScout "5 hidden risks"](https://blog.termscout.com/5-hidden-risks-in-saas-contracts-that-can-delay-your-deals), [NatLaw Review SaaS contract trends](https://natlawreview.com/article/trends-negotiating-software-service-providers), [Tropic guide](https://www.tropicapp.io/glossary/negotiating-saas-contracts) - "Negotiation back-and-forth can take several weeks, with delays increasing when more people are involved on both sides, such as legal and sales teams"; "auto-renewal with price hikes" and "one-sided price increase clauses" trigger procurement-legal escalation.
**Concrete scenario:** $180K ARR customer, renewal date Jun 30. May 15: vendor proposes 12% price increase. Customer's procurement requests a 60-day review window. Legal flags the data-use clause as overreaching. Sales offers a 6% increase to close. Customer's CFO requests benchmark comparables. By Jun 25 nothing is signed; auto-renewal clause would extend at the original price but only if no party objects (and procurement has objected verbally on a call, not in writing). Vendor doesn't know if they're in an auto-renew state or not.
**Why hard:** Resolution requires reading the contract clauses against the actual sequence of communications across email, DocuSign redlines, Gong calls, Slack - and inferring whether the customer's verbal objection meets the contract's "written notice" standard.
**Cross-source evidence required:** Signed MSA + auto-renewal clause JOIN DocuSign/Ironclad redline history JOIN email threads with procurement JOIN Gong calls with the customer JOIN Slack-Connect channel JOIN renewal-date in CRM JOIN finance forecast (is this in committed pipeline?).
**Stakes:** $50K–$5M ARR per case, common in enterprise renewals. The non-decision is itself the loss - DSO bloats, forecast slips, sales-cycle compresses for next year.
**Existing tool gap:** Ironclad shows redlines. Salesforce shows the deal. Gong has the calls. No single tool reads them together to answer "are we contractually auto-renewed right now, or not?"

---

## INVOICE DISPUTES (2)

### 19. po-mismatch-large-enterprise

**Public source:** [NetSuite invoice-dispute guide](https://www.netsuite.com/portal/resource/articles/accounting/invoice-dispute.shtml), [Ordway SaaS payment-mismatch guide](https://ordwaylabs.com/blog/reasons-payments-dont-match-invoices-causes-examples-and-fixes/) - quotes: "Even a large payment, like a $100K annual invoice, can clear but fail to sync into the ERP"; "Customer withholds $600 of a $1,200 invoice until usage overage is resolved."
**Concrete scenario:** $120K annual contract. Customer requires PO on every invoice; PO has fixed amount $120K. Mid-year, customer adds 25 seats - automatic prorated invoice for $4,800 is generated *without* a referencing PO. Customer's AP automatically rejects the invoice ("no PO match"). 60 days pass. Sales doesn't know; CSM doesn't know; finance only knows the original $120K was paid.
**Why hard:** Detecting the rejection requires reading the customer's AP-portal status (often Coupa or Ariba), correlating it with the prorated invoice ID, and routing back to the AE to get a PO amendment. Most SaaS finance teams discover this at quarter close.
**Cross-source evidence required:** Stripe/billing invoice JOIN customer PO field JOIN AP-portal status (Coupa/Ariba) JOIN MSA-terms on PO-required-per-invoice JOIN sales rep responsible for PO amendment JOIN CRM amendment in flight.
**Stakes:** $1K–$50K per disputed invoice, common in enterprise (a [single mid-sized analytics SaaS reported $200K outstanding](https://www.maxio.com/use-cases/never-miss-an-invoice) attributable to this class). DSO impact is the silent killer.
**Existing tool gap:** Stripe/Maxio generate the invoice. Coupa/Ariba accept it. Nothing reconciles "invoice issued without a PO" before sending - and nothing alerts when AP rejects it silently.

---

### 20. contracted-vs-invoiced-price-mismatch

**Public source:** [Ramp invoice discrepancies](https://ramp.com/blog/accounts-payable/invoice-discrepancies), [Ordway mismatches](https://ordwaylabs.com/blog/reasons-payments-dont-match-invoices-causes-examples-and-fixes/) - "Customer deducts $200 from a $2,000 invoice for an SLA credit sales promised, but finance never logged."
**Concrete scenario:** $48K annual contract. Order form specifies $4,000/mo flat. Customer added a 5%-discount addendum in month 4 via DocuSign that Sales filed but Finance never updated in Maxio. Month 5 onward, customer is billed $4,000 but pays $3,800 with a remit note: "per signed addendum dated [date]." Finance treats it as short-pay; AR sends a dunning email; customer escalates angrily.
**Why hard:** Reconciling contracted price vs. invoiced price requires reading the canonical contract (Ironclad/DocuSign), all signed addenda, the order form, and the actual billing-system rate - and detecting drift. Most disputes are 1-2 line items in a multi-line invoice, easy to miss.
**Cross-source evidence required:** Ironclad/DocuSign signed-contract + addenda repository JOIN billing-system rate JOIN AR cash-application notes JOIN remit-advice from customer JOIN Salesforce price-book entry JOIN sales-rep email confirming the discount.
**Stakes:** $200–$10K per disputed invoice, common. Long-tail of small disputes compounds into significant DSO drag.
**Existing tool gap:** Maxio/Chargebee bill from their rate table. Ironclad stores the contract. Nothing automatically reconciles "the rate in the billing system matches the rate in the latest signed addendum."

---

## Synthesis: The Common Thread

What unites these 20 cases is **dispersed truth**. The factual answer - was
this customer really overcharged, did this contact really leave, did the
customer really cancel, was this invoice really past-due - almost never
lives in one system. It is reconstructed by a human investigator joining 3
to 8 different sources at irregular cardinality: a Slack message, a Gong
transcript snippet, a Stripe webhook, a Salesforce field that was updated
last Tuesday, a LinkedIn signal from a person nobody internally has met, a
clause in a PDF that was signed 14 months ago. The current toolchain
(Chargebee, Recurly, Maxio, Stripe Smart Disputes, Gainsight, Chargeflow)
each owns one system perfectly and reasons across systems poorly or not at
all.

For Manthan this implies three design principles.

**First, the agent must be retrieval-first across heterogeneous sources** -
not just SQL over a single warehouse, but free-text retrieval over
Slack / Intercom / Gong, structured retrieval over Stripe / Salesforce,
and clause-level retrieval over signed contracts.

**Second, every case should produce an auditable evidence chain**, because
the deliverable (chargeback response, refund decision, renewal-save play,
dunning routing) must hold up to a CFO, a card-network arbitrator, or a
procurement counterparty.

**Third, the agent should reason about absence as primary evidence** -
no cancellation request found across every channel, no LinkedIn change
detected, no PO present - because the highest-stakes billing-ops
conclusions are negative ones.

---

## Source-set coverage check (vs. Manthan's 13 wired sources)

| Source | Cases that need it |
|---|---|
| stripe | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 19, 20 (almost every case) |
| chargebee | 6, 7, 8, 11, 12 (alt-billing variants) |
| razorpay | India-localized variants of 5–8 (not in the core 20 but realistic) |
| hubspot | 4, 11, 14, 17, 18 |
| salesforce | 5, 8, 12, 14, 18, 19 |
| intercom | 2, 3, 6, 9, 11 (customer voice) |
| zendesk | 3, 9, 11 (alt customer voice) |
| slack | 2, 9, 12, 17 (internal voice) |
| notion | 9, 18 (runbooks, account memos, MSA snippets) |
| linear | 2 (engineering issues / outage post-mortems) |
| github | 2 (deploy correlation), 5 (ABU sync code) |
| sentry | 2, 5, 8 (error spikes during outages, payment-failure backtraces) |
| posthog | 4, 9, 15, 16, 17 (usage telemetry, feature-density signals) |

Sources we **don't** have wired that cases 17, 18, 19, 20 reference:
**Gong** (call transcripts), **Ironclad / DocuSign** (contract clauses),
**LinkedIn signals**, **Coupa / Ariba** (AP portals), **Heap / Amplitude**
(alt product analytics - PostHog mostly covers). These are out-of-scope for
phase 1 but flagged for phase 2 expansion.
