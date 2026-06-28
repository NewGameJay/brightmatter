# GA4 Expert Frameworks

*5 practitioners whose work directly informs how BrightMatter should use GA4 data.*

---

## Tier 1: Measurement Architecture

### Simo Ahava — GTM/Measurement Architect
**Background:** The most referenced GA4 implementation expert globally. Founder of Simmer (GA4 debugger). Former Google Developer Expert.
**Key frameworks:**
- **Server-side tagging architecture** — moving measurement from the browser to a server container for accuracy and privacy compliance. Relevant to BrightMatter because consent mode and ad blockers affect GA4 data quality; understanding the measurement architecture helps assess how much GA4 data to trust.
- **Enhanced measurement audit** — GA4 auto-tracks scrolls, outbound clicks, site search, form interactions, and video engagement. But enhanced measurement can be noisy — it fires events broadly, not precisely. Ahava's recommendation: audit enhanced measurement against your actual conversion events and disable events that create noise.
- **Custom event design** — for ecommerce funnel tracking to be accurate, events (view_item, add_to_cart, begin_checkout, purchase) must carry consistent parameters. Many implementations fire purchase events without item-level data, making funnel analysis meaningless.

**BrightMatter implication:** Before trusting GA4 engagement or funnel data from any property, verify the implementation quality. A property with broken enhanced measurement or incomplete ecommerce tracking will produce misleading signals. Discovery phase (GA4 1.0) should include an implementation quality check.

### Krista Seiden — GA4 Strategy
**Background:** Former Google Analytics Advocate, now independent consultant. Led the GA4 migration playbook used by thousands of organizations.
**Key frameworks:**
- **Engagement-first measurement** — stop optimizing for session count, start optimizing for engaged sessions. The shift from UA's "how many visits?" to GA4's "how many quality visits?" changes which campaigns look good.
- **Key event hierarchy** — not all conversions are equal. GA4 allows marking any event as a "key event." Seiden's framework: define a hierarchy (primary = purchase/lead form, secondary = add_to_cart/begin_checkout, micro = scroll/video play) and only use primary key events for campaign optimization.
- **Attribution model education** — data-driven attribution in GA4 redistributes credit from last-click channels (brand search, email) to awareness channels (display, social, video). Most organizations don't understand this shift and make wrong budget decisions.

**BrightMatter implication:** The key event hierarchy matters for interpreting GA4 session conversion rates. A property where "page_view" is marked as a key event will show inflated engagement rates and conversion rates. Check key event configuration before using session_cvr as a diagnostic metric.

---

## Tier 2: Applied Analytics

### Charles Farina — GA4 Data API Expert
**Background:** Data analytics lead, former Google consultant. Most detailed published documentation on GA4 API scope rules and query patterns.
**Key frameworks:**
- **Scope-aware querying** — the most common API mistake: mixing scopes. Session-scoped dimensions with event-scoped metrics produce numbers that look right but aren't. Farina's rule: "before you write a query, decide what question you're answering and lead with the appropriate scope."
- **Quota management** — with 25,000 tokens/day on Standard properties, high-cardinality queries (full URLs as dimensions) can burn through quotas in a few requests. Batch requests, reduce cardinality, cache results.
- **BigQuery export as escape hatch** — when the Data API's aggregated reports aren't granular enough, BigQuery export provides raw event-level data. Free up to 1M events/day on Standard.

**BrightMatter implication:** The API doc in this research package incorporates Farina's scope rules. For BrightMatter's use case (landing page performance by device by day), the scope is consistently session-level — which is the safest scope to query because landing page is inherently session-scoped.

### Julius Fedorovicius — Analytics Mania
**Background:** Runs the most-visited GA4 tutorial site. 500+ detailed implementation guides. Practical, implementation-focused.
**Key frameworks:**
- **GA4 debugging methodology** — when numbers don't match expectations, systematic approach: check the tag firing, check the event parameters, check the scope, check the date range, check the filter. Most GA4 "bugs" are configuration issues.
- **Core Web Vitals in GA4** — detailed implementation guide for sending LCP/CLS/INP to GA4 via GTM + web-vitals library. Critical takeaway: this is custom implementation that most properties don't have. Default GA4 does NOT track page speed.
- **Ecommerce tracking validation** — step-by-step verification that view_item, add_to_cart, begin_checkout, and purchase events are firing correctly with the right parameters. A broken purchase event (firing without transaction_id) inflates conversion counts.

**BrightMatter implication:** Before ingesting ecommerce funnel data from any property, run Fedorovicius's validation checklist. Properties with broken ecommerce tracking produce misleading funnel analysis.

### Dana DiTomaso — Kick Point Analytics
**Background:** Analytics strategist focused on connecting GA4 to business outcomes, not just web metrics.
**Key frameworks:**
- **Measurement plan before implementation** — define what business questions you need answered BEFORE configuring GA4. Most GA4 setups collect everything and answer nothing. BrightMatter has a defined set of questions (did the landing page degrade? where in the funnel did conversion break? is mobile UX the problem?) — the measurement plan is already clear.
- **Traffic quality scoring** — engagement rate alone doesn't capture quality. DiTomaso recommends combining engagement rate + session conversion rate + scroll depth into a composite traffic quality score per source. A high-engagement, low-converting source is entertaining but not valuable.
- **The "so what" test** — every metric you track should answer "so what do I do differently based on this number?" If the answer is "nothing," stop tracking it. For BrightMatter: every GA4 signal ingested should change a recommendation or upgrade a confidence level. If it doesn't, it's noise.

**BrightMatter implication:** The "so what" test applies directly to the signal ranking. Engagement rate passes ("if it drops, check the landing page"). Session duration probably fails ("if it drops from 2:30 to 2:15... so what?"). Apply the test before adding Tier 3 signals.

---

## What GA4 Experts Agree On

1. **GA4's engagement rate is genuinely better than UA's bounce rate** — it measures actual user value rather than single-pageview visits.
2. **The mobile gap is structural, not fixable** — optimize mobile UX to reduce it, but don't expect parity with desktop.
3. **Attribution shifted credit from last-click channels to awareness channels** — budgets based on last-click attribution are misallocated.
4. **Most GA4 implementations are broken** — missing events, wrong parameters, misconfigured key events. Verify before trusting.
5. **The Data API has real limitations** — quotas, scope rules, cardinality, no page speed. Work within them, don't fight them.
