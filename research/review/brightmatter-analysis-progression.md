# BrightMatter Analysis Progression

*Three phases, in order. Each one depends on the one before it being locked in.*

---

## Phase 1: Point-in-Time Analysis (CURRENT)

**The question:** "Right now, what does this account look like?"

This is a snapshot. No history, no trends, no "it used to be." Just: today, what is the state of this account, and does that state have problems?

### What Phase 1 Analyzes

**Structural health** — Is the account configured correctly?
- Campaign types present (Search, PMax, Shopping, Display, Video)
- Brand vs. non-brand separation
- Bidding strategy selection per campaign type
- Match type distribution (broad/phrase/exact ratios)
- Negative keyword coverage
- Conversion action setup (primary/secondary, types, attribution model)
- Extension/asset coverage
- Campaign count relative to conversion volume (over-segmentation)
- Network settings (Search Partners, Display expansion)
- Auto-applied recommendations status

**Performance snapshot** — Against benchmarks, right now, how is this account doing?
- CPA, ROAS, CVR, CTR vs. vertical benchmarks
- Quality Score distribution vs. expectations
- Impression share and competitive position
- Budget utilization (capped vs. uncapped)
- Cross-account comparison (is this account an outlier among its peers?)

**Configuration red flags** — Things that are objectively misconfigured
- Broad match + manual bidding
- Page views as primary conversion
- Duplicate primary conversion actions
- PMax without merchant feed (for ecommerce)
- No brand campaign with brand terms in non-brand campaigns
- Missing key extension types

### What Phase 1 CANNOT Do

- Cannot tell you if things are getting better or worse (no trend)
- Cannot tell you if a current CPA is normal for this time of year (no seasonal baseline)
- Cannot tell you what caused a current state (no before/after)
- Cannot tell you if a metric is anomalous vs. typical for this account (no history)
- Cannot tell you if a change helped or hurt (no action → outcome linkage)

### When Phase 1 Is Locked In

- Every detector is at KEEP or MONITOR with documented limitations
- REVISE detectors are either fixed or shelved with explanation
- Every signal has a confidence tier (CONFIRMED / LIKELY / SUGGESTIVE)
- Every signal has the "what we know / believe / can't rule out / check next" frame
- Vertical classification is complete for all active accounts
- Harness false positive rate is <5% for all KEEP detectors
- The system produces signals a 20-year marketer would look at and say "yes, that's real, and the caveats are honest"

---

## Phase 2: Time Series & Historical Analysis (NEXT)

**The question:** "How has this account been performing over time, and what's normal?"

This is where trends, baselines, and temporal context enter. Phase 1 tells you "CPA is $45." Phase 2 tells you "CPA is $45, which is up from $32 three weeks ago, but this same time last year it was $48, so this might be seasonal."

### What Phase 2 Adds

**Trend detection** — Is performance improving, declining, stable, or volatile?
- Rolling 7-day, 14-day, 30-day trends for core metrics (CPA, ROAS, CVR, CTR, impression share)
- Trend classification: improving / declining / stable / volatile (based on slope + variance)
- Trend acceleration: is the decline speeding up or slowing down?
- Per-campaign and per-account trends

**Seasonal baselines** — What's normal for this account at this time?
- Year-over-year comparison (same week last year)
- Vertical-specific seasonal curves (built from cross-account data across 500 accounts)
- Day-of-week patterns (B2B weekday vs. ecommerce weekend patterns)
- Expected ranges: "for a skincare ecommerce brand spending $25-100K/month, CPA in April is typically $X-$Y"

**Regime change detection** — When did things shift?
- Statistical changepoint detection: "CPA was stable at $30 from Jan-Mar, then shifted to $45 in April"
- This is different from a spike (temporary) — it's a new normal
- Regime changes are the most actionable historical signal because they indicate something structural changed

**Anomaly detection with temporal context**
- Phase 1 says "CPA is high." Phase 2 says "CPA is high relative to this account's own history" or "CPA is high but it's always high in Q1"
- Removes false alarms from seasonal patterns
- Adds true alarms for subtle degradation that's within benchmark range but abnormal for this specific account

**Volatility profiling** — How noisy is this account?
- High-volatility accounts need wider thresholds (don't alert on every fluctuation)
- Low-volatility accounts should alert on smaller changes (any movement is unusual)
- Volatility differs by campaign type: PMax is inherently more volatile than exact-match brand Search

### What Phase 2 Requires from Phase 1

- Reliable metrics (if Phase 1 tracking break detection isn't working, historical data is contaminated)
- Account classification (seasonal baselines are vertical-specific)
- Clean ingestion (consistent data quality over time — gaps or schema changes break trend analysis)
- Sufficient history (need 60-90 days minimum for trends, 12+ months for seasonal baselines)

### What Phase 2 CANNOT Do

- Cannot tell you WHY a trend changed (only that it did)
- Cannot tell you if a specific action caused a trend shift (that's Phase 3)
- Cannot tell you if a trend will continue (that requires predictive modeling, which comes later)
- Cannot distinguish "CPA rose because we expanded to broad match" from "CPA rose because the market got more expensive" — both look identical in the time series

### Why Phase 2 Before Phase 3

This is the critical ordering. Without Phase 2, Phase 3 (action → outcome) produces misleading results. Here's why:

The episode system (Phase 3) compares 7-day pre-change metrics to 7-day post-change metrics. But if CPA was already trending up before the change, the post-change CPA increase isn't caused by the change — it's a continuation of an existing trend.

Phase 2 gives you the baseline trend. Phase 3 measures the deviation from that trend after a change. Without Phase 2, Phase 3 attributes trend continuation to the most recent change, which is exactly the kind of false learning that makes the system worse over time, not better.

Example:
- Phase 3 alone: "Budget was increased on April 10. CPA went from $30 (pre) to $40 (post). Budget increase degraded CPA." 
- Phase 2 + 3: "CPA was trending up at $2/week since March 15 (Phase 2 baseline). Budget was increased on April 10. Expected CPA without change would have been $38. Actual post-change CPA was $40. The budget increase may have added $2 of CPA degradation, not $10. Most of the increase was pre-existing trend."

This is why the episodes we generated (100 of them) should be treated as preliminary. They're real data, but the outcome attribution doesn't account for pre-existing trends. Phase 2 retroactively improves Phase 3's accuracy.

---

## Phase 3: Action → Outcome Analysis (AFTER)

**The question:** "Someone changed something. Did it help or hurt, and by how much?"

This is the learning loop — the core of what makes BrightMatter compound in intelligence over time. Phase 1 tells you what's wrong. Phase 2 tells you how things are trending. Phase 3 tells you which interventions actually work.

### What Phase 3 Adds

**Change → outcome linkage**
- Every change in the Change History API becomes a potential episode
- Pre-change baseline (from Phase 2 trend, not just a snapshot)
- Post-change performance measured against the projected trend (not just against the pre-change level)
- Outcome classified: improved / degraded / neutral / too early to tell

**Change type taxonomy**
- Budget changes (increase / decrease / new shared budget)
- Bidding strategy changes (switch type, adjust target)
- Keyword changes (add / remove / match type change)
- Ad copy changes (new RSA, headline changes, description changes)
- Targeting changes (geographic, audience, schedule)
- Structural changes (new campaign, campaign pause, ad group restructure)
- Conversion tracking changes (new action, primary/secondary switch)
- Auto-applied changes (Google's recommendations applied automatically)

**What worked for whom**
- "Budget increases on PMax campaigns for ecommerce accounts in the $25-100K tier improved ROAS by an average of 18% across 12 episodes with a 75% success rate"
- "RSA refreshes on non-brand Search campaigns for lead gen accounts had a 40% improvement rate, 35% degradation rate, and 25% neutral — too noisy to recommend without A/B testing"
- "tCPA target reductions of >20% degraded CPA in 80% of episodes within the first 2 weeks — the algorithm needs time to adjust"

**Auto-applied change impact**
- With 87% of changes being auto-applied, this becomes the most important analysis
- "Auto-applied keyword additions in non-brand Search campaigns degraded CPA in 60% of episodes — opt out of this recommendation type"
- "Auto-applied bid adjustments had neutral impact in 70% of episodes — Google's automation is generally reasonable on bids"

**Confidence scoring that improves over time**
- An episode with 3 similar precedents has higher confidence than a novel change type
- Cross-account evidence: "This type of change worked in 8 out of 10 similar accounts" is stronger than "This worked once in this account"
- Confidence degrades with age: a pattern from 6 months ago matters less than one from last month

### What Phase 3 Requires from Phase 2

- Trend baselines (to separate change impact from pre-existing trends)
- Seasonal context (to separate change impact from seasonal effects)
- Volatility profiling (to set appropriate thresholds for "significant" change)
- Regime change detection (to avoid attributing a regime shift to the most recent change)

### What Phase 3 CANNOT Do

- Cannot prove causation (only correlation with temporal precedence)
- Cannot account for simultaneous changes (if budget AND ad copy changed the same week, can't isolate which one caused the outcome)
- Cannot account for external factors (competitor entry, website changes, cross-channel effects)
- Cannot predict future outcomes from past patterns with certainty (the market changes)

### What Phase 3 Eventually Enables

Once the learn loop has enough episodes with validated outcomes:

- **Prediction before action:** "Based on 15 similar episodes across accounts like yours, this type of change has a 70% chance of improving CPA by 15-25% and a 20% chance of degrading it by 5-10%."
- **Recommendation generation:** "Three changes have >75% success rate for your account profile: [specific, ranked recommendations with expected outcomes and confidence levels]."
- **Risk assessment:** "This change has worked in ecommerce but has a 60% failure rate in lead gen accounts your size. Proceed with caution."

But those are future capabilities that depend on the learn loop having accumulated enough validated episodes. The foundation comes first.

---

## Summary: The Build Sequence

```
Phase 1: Point-in-Time (NOW)
├── What does the account look like today?
├── What's misconfigured?
├── How does it compare to benchmarks?
├── Confidence framework: what we know / believe / can't confirm
├── LOCK IN before proceeding
│
Phase 2: Time Series (NEXT)
├── How has performance been trending?
├── What's the seasonal baseline?
├── Where did regime changes happen?
├── Volatility profiling per account
├── Retroactively improves Phase 1 (adds "...and this is unusual" or "...and this is normal")
│
Phase 3: Action → Outcome (AFTER)
├── What changed and what happened?
├── Pre-existing trend separation (requires Phase 2)
├── Cross-account pattern learning
├── Auto-applied change impact analysis
├── Eventually: predictions and recommendations
```

Each phase is useful on its own. But each phase also retroactively improves the previous one. Phase 2 makes Phase 1 smarter (seasonal context). Phase 3 makes Phase 2 actionable (which trends to intervene on and how). The foundation has to be right because everything builds on it.
