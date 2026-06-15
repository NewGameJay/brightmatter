"""Campaign-name heuristics shared by detectors and their harnesses.

Single source of truth: the over_segmentation detector uses these to avoid
firing on intentional geo / type / brand splits, and its disconfirmation
harness uses the same patterns to test for exactly that. Keeping them here
prevents the detector and harness from drifting apart.
"""

from __future__ import annotations

import re

GEO_HINTS = re.compile(
    r"\b(usa|us|uk|ca|eu|au|de|fr|es|it|nl|jp|kr|"
    r"ny|ca|tx|fl|wa|or|ma|il|nj|geo|state|city|local|region|"
    r"new[-_ ]york|los[-_ ]angeles|chicago|boston|miami|seattle|austin|dallas|denver)\b",
    re.IGNORECASE,
)
BRAND_HINTS = re.compile(r"\bbrand|nonbrand|non[-_ ]brand|generic|competitor\b", re.IGNORECASE)
TYPE_HINTS = re.compile(
    r"\bpmax|shopping|search|display|video|youtube|discovery|demand[-_ ]gen\b", re.IGNORECASE
)


def split_fractions(names: list[str]) -> tuple[float, float]:
    """Return (geo_fraction, type_or_brand_fraction) over the given names.

    Mirrors the over_segmentation harness's T1 (geo) and T2 (type/brand)
    tests so the detector can suppress signals the harness would disconfirm.
    """
    if not names:
        return 0.0, 0.0
    geo = sum(1 for n in names if n and GEO_HINTS.search(n))
    type_brand = sum(1 for n in names if n and (TYPE_HINTS.search(n) or BRAND_HINTS.search(n)))
    n = len(names)
    return geo / n, type_brand / n
