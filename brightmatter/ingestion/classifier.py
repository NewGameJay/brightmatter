"""Account classifier — derives business_type and vertical from inputs.

Replaces the previous bare-substring heuristic in pipeline._classify_account.
Three structural bugs the old approach had:

  1. Substring matching on 3-letter tokens (`pet`, `cat`, `car`, `app`) was
     greedy and produced absurd matches (`competitor` → pets, `MCAT` → pets,
     `AddToCart` → automotive).
  2. The account name itself was never consulted — by far the strongest
     available signal ("Binance.US", "LOCKLY", "Prep For Success Tutors",
     "MacKenzie-Childs" all carry direct vertical information).
  3. Business-type priority short-circuited on any `purchase` substring, so
     Binance.US (an app/fintech) and Prep-For-Success (a lead-gen tutoring
     service) both landed as `ecommerce`.

The new classifier is score-based with full trace per account:
  - Account-name regex rules carry the heaviest weight (word-boundary).
  - Conversion-category counts (not name substring) drive business_type.
  - Campaign-name rules also use word boundaries, lighter weight.
  - Campaign-type signals (SHOPPING, APP) nudge business_type.

Each rule that fires is recorded in `ClassificationResult.rule_trace`, so
misclassifications can be diagnosed without re-running the data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from brightmatter.models.account import BusinessType


_OVERRIDES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "account_overrides.yaml"


@lru_cache(maxsize=1)
def _load_overrides() -> dict[str, dict]:
    if not _OVERRIDES_PATH.exists():
        return {}
    with _OVERRIDES_PATH.open() as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("overrides", {}) or {}

# ── Rule tables ──
# Tuples: (regex_pattern, business_type, vertical, weight)
# Use word boundaries `\b` to avoid substring contamination. Patterns are
# tested in order; multiple may fire and contribute to the score.

_NAME_RULES: list[tuple[str, BusinessType, str, float]] = [
    # Known specific brands / strong identifiers
    (r"\bbinance\b",                    BusinessType.APP,        "fintech_crypto",         1.0),
    (r"\b(coinbase|kraken|gemini)\b",   BusinessType.APP,        "fintech_crypto",         1.0),
    (r"\blockly\b",                     BusinessType.ECOMMERCE,  "smart_home",             1.0),
    (r"\bfunko\b",                      BusinessType.ECOMMERCE,  "collectibles",           1.0),
    (r"\bmackenzie[- ]?childs\b",       BusinessType.ECOMMERCE,  "home_goods",             1.0),
    (r"\bhoney birdette\b",             BusinessType.ECOMMERCE,  "apparel",                1.0),
    (r"\broots\b",                      BusinessType.ECOMMERCE,  "apparel",                0.8),
    (r"\b(loungefly|disney|marvel)\b",  BusinessType.ECOMMERCE,  "collectibles",           0.8),
    # Hospitality / clubs
    (r"\b(country club|golf club|invited usa|membership club)\b",
                                        BusinessType.LEAD_GEN,   "hospitality_country_club", 0.9),
    # Education / test prep / tutoring
    (r"\b(tutors?|tutoring|test prep|lsat|mcat|gmat|gre|sat prep|prep for success)\b",
                                        BusinessType.LEAD_GEN,   "education_test_prep",    0.9),
    (r"\b(academy|school|college|university|learning center)\b",
                                        BusinessType.LEAD_GEN,   "education",              0.7),
    # Medical / cosmetic (handle plurals via `s?`)
    (r"\b(plastic surgeons?|cosmetic surger(?:y|ies)|surgeons?|dermatology|dermatologist|medspa|aesthetic[s ]+)\b",
                                        BusinessType.LOCAL,      "medical_cosmetic",       0.9),
    (r"\b(dental|dentists?|orthodontics?|orthodontists?)\b",
                                        BusinessType.LOCAL,      "dental",                 0.9),
    (r"\b(medical|clinics?|telehealth|virtual healthcare|aba|therapy|physical therapy|chiropracti[cor]+|wellness|hbot|hospice)\b",
                                        BusinessType.LOCAL,      "healthcare",             0.7),
    # Pool / spa cluster (17+ accounts per audit)
    (r"\b(pool|spa|spas|hot tub|swim spa|sauna)\b",
                                        BusinessType.LEAD_GEN,   "pool_spa",               0.8),
    # Legal (handle plurals)
    (r"\b(law offices?|law firms?|attorneys?|lawyers?|legal|esq)\b",
                                        BusinessType.LEAD_GEN,   "legal",                  0.85),
    # Nonprofit / grants (operating constraints are dramatically different)
    (r"\b(grant|nonprofit|non[- ]?profit|501c3|charity|foundation|temple|museum|cultural center|public broadcasting|google ad grant)\b",
                                        BusinessType.NONPROFIT,  "nonprofit",              0.9),
    # Home services / contractors
    (r"\b(roofing|hvac|plumbing|electrician|contractor|movers?|moving|storage|construction|garage)\b",
                                        BusinessType.LEAD_GEN,   "home_services",          0.8),
    # Real estate
    (r"\b(real estate|realtor|residences|apartments|housing)\b",
                                        BusinessType.LEAD_GEN,   "real_estate",            0.8),
    # Beauty / skincare
    (r"\b(beauty|skincare|skin care|cosmetic|hair care|salon)\b",
                                        BusinessType.ECOMMERCE,  "beauty",                 0.7),
    # Apparel / fashion
    (r"\b(fashion|apparel|clothing|jeans|outerwear|shoes?|footwear|denim|jewel)\b",
                                        BusinessType.ECOMMERCE,  "apparel",                0.7),
    # Food / beverage
    (r"\b(snacks?|coffee|tea|nutrition|supplements?|chicken|candy|bakery|chocolate|cookware)\b",
                                        BusinessType.ECOMMERCE,  "food_beverage",          0.6),
    # Toys / collectibles
    (r"\b(toys?|figure|collectible|hobby)\b",
                                        BusinessType.ECOMMERCE,  "collectibles",           0.7),
    # Home goods (including wallpaper, tile, etc.)
    (r"\b(furniture|decor|home decor|home goods|rugs?|lighting|kitchen|wallpaper|wallcoverings?|hygge)\b",
                                        BusinessType.ECOMMERCE,  "home_goods",             0.6),
    # Home improvement (tile, plumbing supplies, contractor materials)
    (r"\b(tile|plumbing supply|electrical supply|hardware|paint|drywall|flooring)\b",
                                        BusinessType.ECOMMERCE,  "home_improvement",       0.7),
    # Automotive (word-boundary so "AddToCart" stays safe; require specific words)
    (r"\b(motorcycle|motorcycles?|auto parts?|car parts?|automotive|moped|scooter|seat|seats|mustang)\b",
                                        BusinessType.ECOMMERCE,  "automotive",             0.6),
    # Baby / kids / children
    (r"\b(baby|babies|infant|toddler|kids?|children|nursery)\b",
                                        BusinessType.ECOMMERCE,  "baby_kids",              0.7),
    # Fashion brands (known names)
    (r"\b(vici|vavé|vetta|brax|lily|denim)\b",
                                        BusinessType.ECOMMERCE,  "apparel",                0.7),
    # Ear / hearing protection (use prefix-only boundary to catch Earmuffz, earplugs etc.)
    (r"\b(earmuff|earplug|hearing protection|fall protection|safety equipment)",
                                        BusinessType.ECOMMERCE,  "safety_gear",            0.7),
    # Appliances (Coway, etc.)
    (r"\b(air purifier|water filter|appliance|coway|water purifier)\b",
                                        BusinessType.ECOMMERCE,  "appliances",             0.7),
    # Pets (strict word boundary now — no substring contamination)
    (r"\b(pet|pets|petcare|pet food|petsmart|veterinary|kennel)\b",
                                        BusinessType.ECOMMERCE,  "pets",                   0.7),
    # Finance / insurance
    (r"\b(insurance|insure|bank|banking|loan|credit|mortgage|investment)\b",
                                        BusinessType.LEAD_GEN,   "finance",                0.7),
    # Energy / EV
    (r"\b(ev[- ]?charging|ev[- ]?bike|solar|battery|sustainability)\b",
                                        BusinessType.LEAD_GEN,   "energy",                 0.6),
    # Tax services
    (r"\b(tax helpers?|tax services?|tax preparation|tax pros?|h&r block)\b",
                                        BusinessType.LEAD_GEN,   "tax_services",           0.85),
    # Supplements / health nutrition (when name signals nutrition / mercola etc.)
    (r"\b(supplements?|nutrition|mercola|vitamin|wellness brand)\b",
                                        BusinessType.ECOMMERCE,  "supplements",            0.7),
    # Time tracking / productivity SaaS
    (r"\b(toggl|asana|monday\.com|productivity)\b",
                                        BusinessType.SAAS,       "software",               0.8),
    # Sporting goods / outdoor
    (r"\b(rugby|hockey|football|baseball|basketball|outdoor gear|camping|fishing)\b",
                                        BusinessType.ECOMMERCE,  "sporting_goods",         0.7),
    # Tactical / firearm accessories / sports retail (sporting goods).
    # NOTE: "golf" is intentionally NOT a name keyword — it's ambiguous between
    # golf retailers (ecommerce) and golf-course/club operators (hospitality).
    # Golf RETAILERS are caught precisely by the "golf" URL substring instead.
    (r"\b(holster|tactical|firearm|concealed carry|sports)\b",
                                        BusinessType.ECOMMERCE,  "sporting_goods",         0.7),
    # Fitness (gyms, methods, events)
    (r"\b(gym|fitness|crossfit|pilates|yoga|workout|spartan race)\b",
                                        BusinessType.ECOMMERCE,  "fitness",                0.6),
    # Fragrance / hair color (beauty — extends the beauty rule)
    (r"\b(fragrance|perfume|cologne|parfum|hair color|haircolor)\b",
                                        BusinessType.ECOMMERCE,  "beauty",                 0.7),
    # Apparel — knitwear / activewear / swimwear
    (r"\b(knit|knitwear|wool|sweater|activewear|swimwear|swimsuit)\b",
                                        BusinessType.ECOMMERCE,  "apparel",                0.7),
    # Food / beverage — matcha, olive oil, prepared meals
    (r"\b(matcha|olive oil|meal kit|meals to go|granola)\b",
                                        BusinessType.ECOMMERCE,  "food_beverage",          0.6),
    # Pets — cats/dogs as standalone words (run-together handled via URL rules)
    (r"\b(cat|cats|dog|dogs|feline|canine)\b",
                                        BusinessType.ECOMMERCE,  "pets",                   0.6),
    # SaaS / software
    (r"\b(saas|software|platform|analytics|crm|api|ai[- ]?platform|developer tools)\b",
                                        BusinessType.SAAS,       "software",               0.6),
    # B2B explicit
    (r"\b(b2b|enterprise|commercial services)\b",
                                        BusinessType.B2B,        "b2b_other",              0.5),
]

# Campaign-name patterns: lighter weight, more permissive (campaigns names are
# often messy with codes, geos, etc.).
_CAMPAIGN_RULES: list[tuple[str, BusinessType, str, float]] = [
    (r"\b(country club|tee time|membership)\b",
                                        BusinessType.LEAD_GEN,   "hospitality_country_club", 0.6),
    (r"\b(lsat|mcat|gmat|sat prep|tutor)\b",
                                        BusinessType.LEAD_GEN,   "education_test_prep",    0.7),
    (r"\b(crypto|btc|bitcoin|trading fee|deposit|first[- ]?deposit)\b",
                                        BusinessType.APP,        "fintech_crypto",         0.6),
    (r"\b(smart lock|smart home|wifi lock|iot)\b",
                                        BusinessType.ECOMMERCE,  "smart_home",             0.6),
    (r"\b(pmax|search|shopping|display|youtube)\b",
                                        # Don't add a vertical — these just nudge presence
                                        BusinessType.UNKNOWN,    "",                        0.0),
]

# URL/title substring rules for runtogether brand text where word boundaries
# don't work (`airelleskin.com`, brand titles like `Airelle Skincare Premium…`).
# These are LONGER tokens with low false-positive risk inside a domain or
# title — a brand that puts `skincare` in either is almost always beauty.
_URL_SUBSTRINGS: list[tuple[str, BusinessType, str, float]] = [
    ("skincare",     BusinessType.ECOMMERCE,  "beauty",                    0.6),
    ("skinc",        BusinessType.ECOMMERCE,  "beauty",                    0.5),
    ("beauty",       BusinessType.ECOMMERCE,  "beauty",                    0.6),
    ("cosmetic",     BusinessType.ECOMMERCE,  "beauty",                    0.6),
    ("dental",       BusinessType.LOCAL,      "dental",                    0.7),
    ("dentist",      BusinessType.LOCAL,      "dental",                    0.7),
    ("orthod",       BusinessType.LOCAL,      "dental",                    0.7),
    ("dermat",       BusinessType.LOCAL,      "medical_cosmetic",          0.7),
    ("surgeon",      BusinessType.LOCAL,      "medical_cosmetic",          0.7),
    ("plasticsurg",  BusinessType.LOCAL,      "medical_cosmetic",          0.7),
    ("medspa",       BusinessType.LOCAL,      "medical_cosmetic",          0.7),
    ("hottub",       BusinessType.LEAD_GEN,   "pool_spa",                  0.7),
    ("swimspa",      BusinessType.LEAD_GEN,   "pool_spa",                  0.7),
    ("hotspring",    BusinessType.LEAD_GEN,   "pool_spa",                  0.6),
    ("apparel",      BusinessType.ECOMMERCE,  "apparel",                   0.6),
    ("clothing",     BusinessType.ECOMMERCE,  "apparel",                   0.6),
    ("fashion",      BusinessType.ECOMMERCE,  "apparel",                   0.5),
    ("nutrition",    BusinessType.ECOMMERCE,  "supplements",               0.6),
    ("supplement",   BusinessType.ECOMMERCE,  "supplements",               0.6),
    ("vitamin",      BusinessType.ECOMMERCE,  "supplements",               0.6),
    ("attorney",     BusinessType.LEAD_GEN,   "legal",                     0.7),
    ("lawfirm",      BusinessType.LEAD_GEN,   "legal",                     0.7),
    ("lawyers",      BusinessType.LEAD_GEN,   "legal",                     0.7),
    ("realestate",   BusinessType.LEAD_GEN,   "real_estate",               0.6),
    ("realtor",      BusinessType.LEAD_GEN,   "real_estate",               0.6),
    ("roofing",      BusinessType.LEAD_GEN,   "home_services",             0.7),
    ("plumbing",     BusinessType.LEAD_GEN,   "home_services",             0.7),
    ("hvac",         BusinessType.LEAD_GEN,   "home_services",             0.7),
    ("solar",        BusinessType.LEAD_GEN,   "energy",                    0.6),
    ("insurance",    BusinessType.LEAD_GEN,   "finance",                   0.6),
    ("crypto",       BusinessType.APP,        "fintech_crypto",            0.6),
    ("trading",      BusinessType.APP,        "fintech_crypto",            0.4),
    ("software",     BusinessType.SAAS,       "software",                  0.5),
    ("furniture",    BusinessType.ECOMMERCE,  "furniture",                 0.6),
    ("homedecor",    BusinessType.ECOMMERCE,  "home_goods",                0.6),
    ("cookware",     BusinessType.ECOMMERCE,  "home_goods",                0.5),
    ("propertyman",  BusinessType.LEAD_GEN,   "real_estate",               0.6),
    ("apartment",    BusinessType.LEAD_GEN,   "real_estate",               0.6),
    ("therapy",      BusinessType.LOCAL,      "healthcare",                0.5),
    ("clinic",       BusinessType.LOCAL,      "healthcare",                0.5),
    ("wellness",     BusinessType.LOCAL,      "healthcare",                0.4),
    ("museum",       BusinessType.NONPROFIT,  "nonprofit",                 0.7),
    ("foundation",   BusinessType.NONPROFIT,  "nonprofit",                 0.5),
    ("tutor",        BusinessType.LEAD_GEN,   "education_test_prep",       0.7),
    ("academy",      BusinessType.LEAD_GEN,   "education",                 0.5),
    ("learning",     BusinessType.LEAD_GEN,   "education",                 0.4),
    ("recovery",     BusinessType.LOCAL,      "healthcare",                0.6),
    ("rehab",        BusinessType.LOCAL,      "healthcare",                0.7),
    # Run-together brand domains the word-boundary name rules can't catch
    ("golf",         BusinessType.ECOMMERCE,  "sporting_goods",            0.6),
    ("holster",      BusinessType.ECOMMERCE,  "sporting_goods",            0.6),
    ("fragrance",    BusinessType.ECOMMERCE,  "beauty",                    0.6),
    ("fragflex",     BusinessType.ECOMMERCE,  "beauty",                    0.6),
    ("haircolor",    BusinessType.ECOMMERCE,  "beauty",                    0.6),
    ("matcha",       BusinessType.ECOMMERCE,  "food_beverage",             0.6),
    ("gymtonic",     BusinessType.ECOMMERCE,  "fitness",                   0.6),
    ("meltmethod",   BusinessType.ECOMMERCE,  "fitness",                   0.6),
    ("petpad",       BusinessType.ECOMMERCE,  "pets",                      0.6),
    ("kneadcat",     BusinessType.ECOMMERCE,  "pets",                      0.6),
    ("wool",         BusinessType.ECOMMERCE,  "apparel",                   0.5),
    ("knit",         BusinessType.ECOMMERCE,  "apparel",                   0.5),
]


# Conversion category → (business_type, optional vertical, weight).
# These are official Google Ads ConversionAction categories.
_CATEGORY_TO_BIZTYPE: dict[str, tuple[BusinessType, str, float]] = {
    "PURCHASE":            (BusinessType.ECOMMERCE, "",                  0.6),
    "STORE_SALE":          (BusinessType.LOCAL,     "",                  0.7),
    "SUBMIT_LEAD_FORM":    (BusinessType.LEAD_GEN,  "",                  0.7),
    "BOOK_APPOINTMENT":    (BusinessType.LEAD_GEN,  "",                  0.7),
    "PHONE_CALL_LEAD":     (BusinessType.LEAD_GEN,  "",                  0.6),
    "IMPORTED_LEAD":       (BusinessType.LEAD_GEN,  "",                  0.6),
    "REQUEST_QUOTE":       (BusinessType.LEAD_GEN,  "",                  0.6),
    "GET_DIRECTIONS":      (BusinessType.LOCAL,     "",                  0.7),
    "CONTACT":             (BusinessType.LEAD_GEN,  "",                  0.4),
    # DOWNLOAD signals business_type=APP but the *vertical* must come from
    # the account/campaign rules — supplement brands, medspas, tax services
    # all have app DOWNLOAD conversions and none of them are "vertical=app".
    "DOWNLOAD":            (BusinessType.APP,       "",                  0.7),
    "STORE_VISIT":         (BusinessType.LOCAL,     "",                  0.7),
    "SUBSCRIBE_PAID":      (BusinessType.SAAS,      "",                  0.5),
    "SIGNUP":              (BusinessType.SAAS,      "",                  0.5),
    "BEGIN_CHECKOUT":      (BusinessType.ECOMMERCE, "",                  0.3),
    "ADD_TO_CART":         (BusinessType.ECOMMERCE, "",                  0.3),
}


# ── Inputs / Outputs ──

@dataclass
class ClassificationInputs:
    account_id: str
    account_name: str = ""
    website_url: str = ""
    # Optional fetched-from-the-web metadata. When populated, these are the
    # richest signal — natural language with proper word boundaries.
    title_text: str = ""
    description_text: str = ""
    campaign_names: list[str] = field(default_factory=list)
    campaign_types: dict[str, int] = field(default_factory=dict)
    # List of (action_name, category). Category is the Google Ads enum value.
    conversions: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ClassificationResult:
    business_type: BusinessType
    vertical: str
    confidence: float        # 0..1 — top business_type score / sum of all bt scores
    rule_trace: list[str] = field(default_factory=list)
    business_type_scores: dict[str, float] = field(default_factory=dict)
    vertical_scores: dict[str, float] = field(default_factory=dict)


# ── Core classifier ──

def classify(inputs: ClassificationInputs) -> ClassificationResult:
    # ── Step 0: Manual overrides win over rule output ──
    overrides = _load_overrides()
    if inputs.account_id in overrides:
        o = overrides[inputs.account_id]
        bt_str = (o.get("business_type") or "unknown").lower()
        try:
            bt = BusinessType(bt_str)
        except ValueError:
            bt = BusinessType.UNKNOWN
        vert = o.get("vertical") or ""
        return ClassificationResult(
            business_type=bt,
            vertical=vert,
            confidence=1.0,
            rule_trace=[f"OVERRIDE[{inputs.account_id}] source={o.get('source', 'manual')}"],
            business_type_scores={bt.value: 1.0} if bt != BusinessType.UNKNOWN else {},
            vertical_scores={vert: 1.0} if vert else {},
        )

    bt_scores: dict[BusinessType, float] = {}
    vert_scores: dict[str, float] = {}
    trace: list[str] = []

    def _add(bt: BusinessType, vert: str, weight: float, reason: str) -> None:
        if bt != BusinessType.UNKNOWN and weight > 0:
            bt_scores[bt] = bt_scores.get(bt, 0.0) + weight
        if vert and weight > 0:
            vert_scores[vert] = vert_scores.get(vert, 0.0) + weight
        if weight > 0:
            trace.append(f"{reason}  → btype={bt.value} vert={vert or '-'} w={weight:.2f}")

    # Normalize: lower-case, treat underscores, hyphens, dots, commas as word
    # separators so `country club_id:01401` matches `\bcountry club\b`
    # (underscore is a word char in regex, which silently breaks word
    # boundaries). For domains, `betterlifepartners.com` becomes
    # `betterlifepartners com` and `better-life-partners.com` becomes
    # `better life partners com`.
    def _norm(s: str) -> str:
        return re.sub(r"[._,\-]+", " ", (s or "").lower())

    # ── 1a. Account-name rules (heaviest signal, weight ×2) ──
    name = _norm(inputs.account_name)
    if name:
        for pattern, bt, vert, weight in _NAME_RULES:
            if re.search(pattern, name):
                _add(bt, vert, weight * 2.0, f"NAME[{pattern}]")

    # ── 1b. Website-URL rules ──
    # Domains carry brand/vertical signal: `binance.us`, `lockly.com`,
    # `*-law.com`, `betterlifepartners.com` all classify themselves.
    domain_raw = (inputs.website_url or "").lower()
    domain = _norm(inputs.website_url)

    # 1b-i. TLD-based signals (high precision)
    if domain_raw.endswith(".org") or ".org/" in domain_raw or ".org," in domain_raw:
        _add(BusinessType.NONPROFIT, "nonprofit", 0.7, f"URL_TLD[.org]")
    if domain_raw.endswith(".edu") or ".edu/" in domain_raw:
        _add(BusinessType.NONPROFIT, "education", 0.7, f"URL_TLD[.edu]")
    if domain_raw.endswith(".gov") or ".gov/" in domain_raw:
        _add(BusinessType.NONPROFIT, "government", 0.9, f"URL_TLD[.gov]")

    # 1b-ii. Word-boundary rules on the normalized domain
    if domain:
        for pattern, bt, vert, weight in _NAME_RULES:
            if re.search(pattern, domain):
                _add(bt, vert, weight * 1.5, f"URL[{pattern}]")

    # 1b-iii. Substring rules for runtogether brand domains (see module-level
    # _URL_SUBSTRINGS). Lower threshold than word-boundary rules because
    # `airelleskin.com` legitimately matches `skin` without a word boundary.
    if domain_raw:
        for substr, bt, vert, weight in _URL_SUBSTRINGS:
            if substr in domain_raw:
                _add(bt, vert, weight, f"URL_SUB[{substr}]")

    # ── 1c. Website title + meta description (highest non-name signal) ──
    # When we've fetched the homepage, the title is natural language with
    # proper word boundaries — `<title>Airelle Skincare | Premium Anti-Aging
    # Serums</title>` → `\bskincare\b` matches cleanly. Weight slightly above
    # campaign rules because titles describe the brand directly.
    web_text = _norm(f"{inputs.title_text} {inputs.description_text}")
    if web_text.strip():
        for pattern, bt, vert, weight in _NAME_RULES:
            if re.search(pattern, web_text):
                _add(bt, vert, weight * 1.5, f"WEB[{pattern}]")
        # Also apply the URL substring rules — they're industry tokens that
        # often appear in titles even without word boundaries (e.g. brand
        # name "Skincare" prefix).
        for substr, bt, vert, weight in _URL_SUBSTRINGS:
            if substr in web_text:
                _add(bt, vert, weight * 0.8, f"WEB_SUB[{substr}]")

    # ── 2. Conversion-category dominance (uses counts, not substring) ──
    if inputs.conversions:
        cat_counts: dict[str, int] = {}
        for _name, cat in inputs.conversions:
            if cat:
                cat_counts[cat.upper()] = cat_counts.get(cat.upper(), 0) + 1
        total = sum(cat_counts.values()) or 1
        for cat, count in cat_counts.items():
            share = count / total
            if cat in _CATEGORY_TO_BIZTYPE:
                bt, vert, weight = _CATEGORY_TO_BIZTYPE[cat]
                score = weight * share
                _add(bt, vert, score, f"CONV[{cat}={count}/{total}]")

    # ── 3. Campaign-name rules (word-boundary, lighter weight) ──
    camp_text = _norm(" ".join(inputs.campaign_names))
    if camp_text:
        for pattern, bt, vert, weight in _CAMPAIGN_RULES:
            if weight == 0:
                continue
            if re.search(pattern, camp_text):
                _add(bt, vert, weight, f"CAMP[{pattern}]")

    # ── 4. Campaign-type presence ──
    if inputs.campaign_types.get("SHOPPING", 0) > 0:
        _add(BusinessType.ECOMMERCE, "", 0.5, "CAMP_TYPE[SHOPPING>0]")
    if inputs.campaign_types.get("APP", 0) > 0:
        # APP campaign type indicates business_type=APP but vertical comes from elsewhere.
        _add(BusinessType.APP, "", 0.5, "CAMP_TYPE[APP>0]")

    # ── Decide ──
    if not bt_scores:
        return ClassificationResult(BusinessType.UNKNOWN, "", 0.0, trace,
                                     business_type_scores={}, vertical_scores={})

    best_bt = max(bt_scores.items(), key=lambda x: x[1])
    best_vert = max(vert_scores.items(), key=lambda x: x[1])[0] if vert_scores else ""
    total = sum(bt_scores.values())
    confidence = best_bt[1] / total if total else 0.0

    return ClassificationResult(
        business_type=best_bt[0],
        vertical=best_vert,
        confidence=round(confidence, 3),
        rule_trace=trace,
        business_type_scores={k.value: round(v, 3) for k, v in bt_scores.items()},
        vertical_scores={k: round(v, 3) for k, v in vert_scores.items()},
    )
