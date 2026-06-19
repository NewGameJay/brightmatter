"""Change-bundle signatures (Phase 1.75).

A "bundle" is the set of change categories applied to one campaign on one day
by one actor. Google's auto-apply system applies eligible recommendations
together, so a recurring multi-category set (e.g. budget + campaign_setting) is
ONE coordinated action, not several independent confounding changes. Treating
known bundles as a single action recovers episodes that the naive per-category
view marks confounded.

Signatures validated on the 2026-06-14 snapshot (131,434 change events,
5,946 auto-applied campaign-days, 1,408 human). The doc that proposed these
used the pre-re-ingest 18,530-event set — same signatures, different counts;
these are keyed off the validated current shapes.
"""

from __future__ import annotations

# frozenset(categories) -> bundle name. Coordinated Google auto-apply actions.
AUTO_BUNDLE_SIGNATURES = {
    frozenset(["budget", "campaign_setting"]): "auto_budget_optimization",
    frozenset(["budget", "targeting_keyword"]): "auto_budget_expand",
    frozenset(["campaign_setting", "targeting_keyword"]): "auto_targeting_restructure",
    frozenset(["asset", "budget"]): "auto_creative_budget",
    frozenset(["asset", "budget", "campaign_setting"]): "auto_campaign_refresh",
    frozenset(["budget", "campaign_setting", "targeting_keyword"]): "auto_comprehensive_optimization",
    frozenset(["asset", "campaign_setting", "targeting_keyword"]): "auto_targeting_creative",
    frozenset(["asset", "budget", "campaign_setting", "targeting_keyword"]): "auto_full_optimization",
}

# Human strategic actions — distinct shape (structural/creative build-outs).
HUMAN_BUNDLE_SIGNATURES = {
    frozenset(["structure", "targeting_keyword"]): "human_campaign_restructure",
    frozenset(["ad_creative", "structure", "targeting_keyword"]): "human_campaign_overhaul",
    frozenset(["ad_creative", "asset", "campaign_setting", "structure", "targeting_keyword"]):
        "human_full_campaign_build",
}


def classify_bundle(categories: frozenset[str], actor: str) -> tuple[str, bool]:
    """Classify a campaign-day's category set into an episode category.

    Returns (label, is_known) where:
      - single category   -> (that category, True)          e.g. ("budget", True)
      - known signature   -> (bundle name, True)            e.g. ("auto_budget_expand", True)
      - unknown multi-set -> ("<actor>_unknown_bundle", False) — stays confounded-eligible
    """
    if len(categories) == 1:
        return next(iter(categories)), True
    table = AUTO_BUNDLE_SIGNATURES if actor == "auto_applied" else HUMAN_BUNDLE_SIGNATURES
    name = table.get(categories)
    if name:
        return name, True
    prefix = "auto" if actor == "auto_applied" else "human" if actor == "human" else "mixed"
    return f"{prefix}_unknown_bundle", False


def is_bundle(label: str) -> bool:
    """True if the label is a named multi-category bundle (not a single category)."""
    return label in set(AUTO_BUNDLE_SIGNATURES.values()) | set(HUMAN_BUNDLE_SIGNATURES.values())
