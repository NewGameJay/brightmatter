# GA4 Research

Structured research output for GA4 as both a standalone platform (193 accounts) and a cross-reference layer (15 accounts with Google Ads overlap).

Mirrors the Google Ads research structure at ~40% depth — scoped to GA4's role as an observation/diagnostic layer, not an optimization layer.

---

## Structure

```
api/                  GA4 Data API capabilities, scope rules, quotas, gotchas
benchmarks/           Engagement rate, bounce rate, funnel conversion by vertical
causal_chains/        6 cross-platform diagnostic patterns (GA4 × Google Ads)
experts/              4-5 GA4 measurement experts and their frameworks
patterns/             5 GA4 detection domains with specific detector logic
reference/            Signal map: what to ingest, ranked by BrightMatter impact
```

## Key Differences from Google Ads Research

- Google Ads has 12 pattern domains (12 categories of levers). GA4 has 5 (observation-only, no levers).
- Google Ads has 16 named experts (optimization strategy). GA4 has ~5 (measurement methodology).
- Google Ads causal chains are internal (change → outcome). GA4 causal chains are cross-platform (GA4 observation explains Google Ads outcome).
- GA4 adds a unique challenge: scope rules. Session-scoped data joined to event-scoped data produces wrong numbers silently. The API doc covers this in detail.
