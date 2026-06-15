"""Per-signal confidence framework (roadmap 1.5).

Encodes research/review/brightmatter-signal-confidence-framework.md as a map
from signal_type -> (tier, what_we_cant_rule_out, check_next). Every signal is
annotated so the output is never "CPA spiked" but the honest full frame:

  - confidence_tier:      CONFIRMED / LIKELY / SUGGESTIVE
  - what_we_know:         the factual finding (the signal's own message)
  - what_we_cant_rule_out: alternative explanations the data can't eliminate
  - check_next:           the specific thing the marketer should verify

Tiers (from the framework):
  CONFIRMED  — provable from Google Ads data alone; structural/config facts.
  LIKELY     — the pattern is real, the most-probable cause is clear, but
               alternatives can't be ruled out from Google Ads data.
  SUGGESTIVE — a real anomaly, but the data can't even rank the likely causes.
"""

from __future__ import annotations

CONFIRMED = "CONFIRMED"
LIKELY = "LIKELY"
SUGGESTIVE = "SUGGESTIVE"

# signal_type -> (tier, what_we_cant_rule_out, check_next)
_PROFILES: dict[str, tuple[str, str, str]] = {
    # ── CONFIRMED — structural / configuration facts, directly measured ──
    "tracking_break": (
        CONFIRMED,
        "Whether it's a GTM tag, a website change, a payment-gateway break, or a consent-mode misconfig — the data shows the break, not its cause.",
        "Verify GTM tags fire, conversion-page URLs are unchanged, and consent mode is configured; do not change campaigns until tracking is verified.",
    ),
    "auto_applied_changes": (
        CONFIRMED,
        "Whether the auto-applied changes helped or hurt — episode correlation is not causation.",
        "Review the change log and opt out of recommendation types that don't fit the campaign strategy.",
    ),
    "suspicious_primary_conversion": (
        CONFIRMED,
        "Whether the micro-conversion was set as primary intentionally (some accounts do this when macro-conversion volume is too low).",
        "Confirm whether the action is a true business outcome; if not, move it to secondary so Smart Bidding stops optimizing for it.",
    ),
    "duplicate_primary_conversions": (
        CONFIRMED,
        "Whether the same-category duplication is intentional multi-source tracking rather than double-counting.",
        "Audit the primary conversion actions in that category and move duplicates to secondary.",
    ),
    "missing_conversion_value": (
        CONFIRMED,
        "Whether the business genuinely has no per-conversion value (some lead-gen legitimately doesn't).",
        "If this is value-based/ecommerce, configure conversion values so tROAS can run.",
    ),
    "low_quality_score": (
        CONFIRMED,
        "Exactly how many dollars the low QS costs, or what specifically on the landing page to change (LPE is a rating, not a diagnostic).",
        "Fix the component rated Below Average first — expected CTR, ad relevance, or landing-page experience.",
    ),
    "over_segmentation": (
        CONFIRMED,
        "Whether consolidation would actually improve performance — some splits serve genuinely different audiences or geos.",
        "Consolidate campaigns targeting similar audiences/products; keep splits that serve distinct geos, languages, or business lines.",
    ),
    "missing_brand_separation": (
        CONFIRMED,
        "Whether separating would help — for low-spend accounts it can fragment an already-thin conversion signal.",
        "Separate brand and non-brand into dedicated campaigns if monthly volume supports it (30+ conv each).",
    ),
    "missing_extensions": (
        CONFIRMED,
        "Whether the missing assets materially affect this account's CTR.",
        "Add the missing sitelink, callout, and structured-snippet assets.",
    ),
    "low_negative_ratio": (
        CONFIRMED,
        "Whether the thin negative-keyword list is actually causing waste — only the search-terms report confirms irrelevant spend.",
        "Pull the search-terms report and add negatives for irrelevant queries.",
    ),
    "broad_without_smart_bidding": (
        CONFIRMED,
        "Whether the broad-match keywords are actually wasting spend (needs search-terms and conversion-quality review).",
        "Switch to a conversion-based bid strategy, or tighten match types to exact/phrase.",
    ),
    "budget_capped": (
        CONFIRMED,
        "Whether the uncaptured impressions would convert profitably — budget-lost IS shows demand, not marginal CPA.",
        "Run a controlled ~20% budget increase for two weeks and measure marginal CPA before committing.",
    ),
    "budget_limited_is": (
        CONFIRMED,
        "Whether capturing the lost impressions would be profitable at the margin.",
        "Test a controlled budget increase and watch marginal CPA before scaling.",
    ),
    "no_pmax_campaigns": (
        CONFIRMED,
        "Whether PMax fits this account's goals and feed.",
        "Evaluate whether a PMax campaign fits — ecommerce with a healthy product feed usually benefits.",
    ),
    "no_search_campaigns": (
        CONFIRMED,
        "Whether running without Search is intentional (some feed-only/PMax-only accounts are).",
        "Confirm whether branded and non-brand Search should be capturing high-intent queries.",
    ),

    # ── LIKELY — real pattern, most-probable cause clear, alternatives remain ──
    "cpa_spike": (
        LIKELY,
        "Seasonal demand contraction, competitor entry raising CPCs, landing-page degradation, or cross-channel effects.",
        "Check Auction Insights for new competitors, confirm the landing page/page-speed is unchanged, and compare keyword search-volume trends.",
    ),
    "cpa_change": (
        LIKELY,
        "Seasonal shifts, competitor pressure, landing-page changes, or cross-channel effects driving the move.",
        "Check Auction Insights, the landing page, and search-volume trends before attributing the change.",
    ),
    "cvr_drop": (
        LIKELY,
        "Landing-page or pricing changes, audience-mix shift from broad match, or a seasonal intent shift.",
        "Check whether the landing page/site changed, review the search-terms report for query expansion, and (for PMax) whether channel mix shifted.",
    ),
    "cvr_change": (
        LIKELY,
        "Landing-page/pricing changes, query-mix shift, or seasonal intent — either direction can be non-structural.",
        "Confirm the landing page and search-terms mix over both windows before treating it as a real trend.",
    ),
    "budget_capped_change": (
        LIKELY,
        "Whether the week-over-week shift is structural or normal auction volatility.",
        "Confirm the budget and competition context across the two windows before acting.",
    ),
    "budget_limited_is_change": (
        LIKELY,
        "Whether the IS-loss movement reflects a real budget shift or auction-level noise.",
        "Confirm the budget context across both windows before acting.",
    ),
    "roas_contamination": (
        LIKELY,
        "Whether non-brand is an upper-funnel pipeline builder that converts through brand later — an attribution question last-click can't answer.",
        "Pull cross-channel/assisted-conversion paths from GA4: does non-brand Search precede brand conversions?",
    ),
    "roas_contamination_unsafe": (
        LIKELY,
        "Whether non-brand assists brand conversions later, and whether the blended ROAS is distorted by value artifacts.",
        "Validate brand vs non-brand volume and pull assisted-conversion paths before reallocating budget.",
    ),
    "cross_account_cpa_outlier": (
        LIKELY,
        "Different conversion types, geographic markets, product price points, or account maturity vs peers.",
        "Compare conversion-action types and geo targeting to peers, and weigh conversion value, not just CPA.",
    ),
    "pmax_conversion_inflation": (
        LIKELY,
        "Whether PMax's higher CVR reflects genuine shopping/retargeting intent rather than counting different conversion actions.",
        "Compare PMax vs Search conversion-action settings and value-per-conversion; check whether PMax inherited all primaries by default.",
    ),
    "search_terms_waste": (
        LIKELY,
        "Whether the 'wasted' terms assisted conversions credited elsewhere (last-click blind spot).",
        "Review the flagged terms for assisted value and sufficient clicks before adding negatives.",
    ),

    # ── SUGGESTIVE — real anomaly, causes can't be ranked from the data ──
    "pmax_dominance_no_shopping": (
        SUGGESTIVE,
        "PMax channel allocation is opaque; a Display-heavy PMax may still prospect effectively.",
        "Check product-feed health and asset-group search themes; consider a PMax uplift experiment.",
    ),
    "pmax_low_conv_volume": (
        SUGGESTIVE,
        "A clean low-volume signal can still optimize; new campaigns are expected to be low during learning.",
        "Check campaign age; if it's been months below 30 conv, pool with similar campaigns or switch bidding temporarily.",
    ),
    "pmax_low_conv_volume_change": (
        SUGGESTIVE,
        "Volume swings during the ~6-week PMax learning phase are expected and not yet structural.",
        "Wait for the campaign to clear the learning phase before treating the movement as a real trend.",
    ),
    "insufficient_conversions_for_strategy": (
        SUGGESTIVE,
        "Some campaigns optimize fine below 30/month, and new campaigns are expected to be low during learning.",
        "Check campaign age; if mature and still low, switch to Maximize Clicks to build volume or consolidate.",
    ),
}

# Any signal_type without an explicit profile is treated as SUGGESTIVE so we
# never over-claim confidence — and the missing profile is easy to spot.
_DEFAULT = (
    SUGGESTIVE,
    "No confidence profile is defined for this signal type yet, so its cause can't be ranked.",
    "Investigate manually and add a confidence profile for this detector.",
)


def profile_for(signal_type: str) -> tuple[str, str, str]:
    """Return (tier, what_we_cant_rule_out, check_next) for a signal type."""
    return _PROFILES.get(signal_type, _DEFAULT)


def annotate(signal) -> None:
    """Populate a Signal's confidence fields in place.

    `what_we_know` is the signal's own message — the factual finding — so the
    three fields together read as: here's what we measured, here's what we
    can't rule out, here's what to check.
    """
    tier, cant_rule_out, check_next = profile_for(signal.signal_type)
    signal.confidence_tier = tier
    signal.what_we_know = signal.message
    signal.what_we_cant_rule_out = cant_rule_out
    signal.check_next = check_next
