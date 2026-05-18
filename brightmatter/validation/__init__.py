"""Disconfirmation harness for detector signals.

Each detector produces signals that are *claims* about the data. The harness
treats each claim as a hypothesis and runs independent tests against adjacent
data to confirm, disconfirm, or mark inconclusive — surfacing where a theory
breaks down rather than only where it works.
"""

from brightmatter.validation.auto_applied import audit_auto_applied_signals
from brightmatter.validation.brand_nonbrand import audit_brand_nonbrand_signals
from brightmatter.validation.budget_capped import audit_budget_capped_signals
from brightmatter.validation.budget_capped_change import audit_budget_capped_change_signals
from brightmatter.validation.budget_limited import audit_budget_limited_signals
from brightmatter.validation.budget_limited_is_change import (
    audit_budget_limited_is_change_signals,
)
from brightmatter.validation.cpa_change import audit_cpa_change_signals
from brightmatter.validation.cpa_spike import audit_cpa_spike_signals
from brightmatter.validation.cvr_change import audit_cvr_change_signals
from brightmatter.validation.cvr_drop import audit_cvr_drop_signals
from brightmatter.validation.duplicate_primary_conversions import (
    audit_duplicate_primary_conversions_signals,
)
from brightmatter.validation.insufficient_conversions import (
    audit_insufficient_conversions_signals,
)
from brightmatter.validation.over_segmentation import audit_over_segmentation_signals
from brightmatter.validation.pmax_low_conv_volume_change import (
    audit_pmax_low_conv_volume_change_signals,
)
from brightmatter.validation.pmax_low_volume import audit_pmax_low_volume_signals

# Map detector key → audit function. Each function returns a list of audit
# objects with a uniform interface: .signal_id, .account_id, .account_name,
# .detector_message, .test_results (list of TestResult), .verdict_counts, .overall.
AUDITS = {
    "brand_nonbrand":               audit_brand_nonbrand_signals,
    "budget_limited":               audit_budget_limited_signals,
    "budget_limited_is_change":     audit_budget_limited_is_change_signals,
    "cvr_drop":                     audit_cvr_drop_signals,
    "cvr_change":                   audit_cvr_change_signals,
    "cpa_spike":                    audit_cpa_spike_signals,
    "cpa_change":                   audit_cpa_change_signals,
    "budget_capped":                audit_budget_capped_signals,
    "budget_capped_change":         audit_budget_capped_change_signals,
    "auto_applied":                 audit_auto_applied_signals,
    "duplicate_conversions":        audit_duplicate_primary_conversions_signals,
    "over_segmentation":            audit_over_segmentation_signals,
    "insufficient_conv":            audit_insufficient_conversions_signals,
    "pmax_low_volume":              audit_pmax_low_volume_signals,
    "pmax_low_conv_volume_change":  audit_pmax_low_conv_volume_change_signals,
}

__all__ = ["AUDITS"]
