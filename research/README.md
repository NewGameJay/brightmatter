# BrightMatter Research

Structured research output that informs the BrightMatter engine architecture.
All findings here feed into `architecture-decisions.md` (the synthesis doc).

## Directory Structure

```
research/
├── README.md                     ← you are here
├── architecture-decisions.md     ← synthesis: taxonomy, schema, thresholds (Phase 5)
├── experts/
│   ├── tier1-expert-frameworks.md   ← Geddes, Kirk Williams, Vallaeys, McNair, Rhodes, Lolk
│   └── tier2-expert-insights.md     ← Jyll, Navah, Ameet, Reva, Amy, Chris
├── patterns/
│   └── pattern-detection-logic.md   ← 12 pattern domains with thresholds + pseudocode
├── causal_chains/
│   └── causal-chain-signatures.md   ← 12 external cause → Google Ads effect chains
├── benchmarks/
│   └── industry-benchmarks.md       ← CPC/CTR/CVR/CPA/ROAS by vertical + audit frameworks
├── api/
│   └── google-ads-api-capabilities.md ← GAQL, ChangeEvent, rate limits, field mapping
└── reference/
    ├── signal-map.md                ← features, configurations, ingestion tiers
    ├── pattern-research-map.md      ← 12 pattern domains with known patterns + sources
    └── research-brief.md            ← 16 experts, 12 causal chains
```

## How Research Flows Into Engineering

```
Expert Frameworks (A1)
  → Which API fields matter most
  → Account taxonomy dimensions

Pattern Detection (A2)
  → Detection logic to implement
  → Data granularity requirements

Causal Chains (A3)
  → Diagnostic hierarchy
  → External data sources for later phases

API Capabilities (A4)
  → What's actually queryable
  → Rate limit constraints
  → Feasibility assessment

Benchmarks (A3/Tier 3)
  → Baseline "normal" ranges by segment
  → Anomaly detection thresholds

Synthesis → architecture-decisions.md
  → Account taxonomy spec
  → Ingestion schema
  → Episode format
  → Baseline thresholds
```
