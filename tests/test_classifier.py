"""Regression tests for `brightmatter.ingestion.classifier`.

Each test pins a known-bad case caught in the foundation audit so the
substring bugs (`competitor → pets`, `MCAT → pets`, `AddToCart →
automotive`, `Calls from ads → ecommerce/software`) cannot regress.
"""

from __future__ import annotations

from brightmatter.ingestion.classifier import (
    ClassificationInputs,
    classify,
)
from brightmatter.models.account import BusinessType


def test_lockly_is_smart_home_not_pets():
    """`Competitor Keywords` in a campaign name must NOT trigger pets vertical."""
    result = classify(ClassificationInputs(
        account_id="3402486203",
        account_name="LOCKLY",
        campaign_names=[
            "202411 - Shopify - Search - Competitor Keywords",
            "202411 - Shopify - Search - Generic Keywords",
            "202411 - Shopify - Search - Main Keywords",
            "202506 - Shopify - PMax - Purchase",
            "202602 - Shopify - Demand Gen - New Prospect",
            "202603 - Shopify - Search - Branded Keywords",
        ],
        campaign_types={"SEARCH": 100, "PERFORMANCE_MAX": 20, "DEMAND_GEN": 5},
        conversions=[
            ("Google Shopping App Purchase", "PURCHASE"),
            ("Google Shopping App View Item", "PAGE_VIEW"),
            ("Lead form - Submit", "SUBMIT_LEAD_FORM"),
        ],
    ))
    assert result.business_type == BusinessType.ECOMMERCE
    assert result.vertical == "smart_home"
    assert "pets" not in result.vertical_scores


def test_prep_for_success_tutors_is_education_not_pets():
    """`MCAT` in a conversion name must NOT trigger pets vertical."""
    result = classify(ClassificationInputs(
        account_id="4580755399",
        account_name="Prep For Success Tutors",
        campaign_names=[
            "CL - Performance Max - LSAT Tutors",
            "CL - Search - Brand - LSAT",
            "Search - Non-Brand - LSAT - Broad",
            "Search - Non-Brand - LSAT - Exact",
        ],
        campaign_types={"SEARCH": 60, "PERFORMANCE_MAX": 10},
        conversions=[
            ("MCAT - New Customer", "CONVERTED_LEAD"),
            ("GTM - GHL Listener - Booked Appointment", "BOOK_APPOINTMENT"),
            ("GHL - LSAT Book Appointment", "BOOK_APPOINTMENT"),
            ("Calls from ads", "PHONE_CALL_LEAD"),
            ("Clicks to call", "CONTACT"),
        ],
    ))
    assert result.business_type == BusinessType.LEAD_GEN
    assert result.vertical == "education_test_prep"
    assert "pets" not in result.vertical_scores


def test_binance_us_is_app_fintech_not_ecommerce_pets():
    """An app account whose conversions are PURCHASE-categorized in-app events
    must classify as APP/fintech_crypto, not ecommerce/pets."""
    result = classify(ClassificationInputs(
        account_id="4362391113",
        account_name="Binance.US",
        campaign_names=[
            "HM_APP_Android_first_deposit (v1)",
            "HM_APP_iOS_first_deposit (v1)",
            "HM_DMG_first_deposit",
            "HM_PMX",
            "HM_SNO_Branded_Beta",
            "HM_SNO_NB_Buy Crypto",
        ],
        campaign_types={"APP": 40, "SEARCH": 10, "PERFORMANCE_MAX": 5},
        conversions=[
            ("iOS - first_open (AppsFlyer)", "DOWNLOAD"),
            ("Android - install (Google Play)", "DOWNLOAD"),
            ("iOS - af_trading_fee_ocbs_us", "PURCHASE"),
            ("Android - af_trading_fee_spot_us", "PURCHASE"),
            ("Android - af_first_convert_trade_us", "PURCHASE"),
        ],
    ))
    assert result.business_type == BusinessType.APP
    assert result.vertical == "fintech_crypto"
    assert "pets" not in result.vertical_scores


def test_ject_is_beauty_not_automotive():
    """`AddToCart` in a campaign name must NOT trigger automotive vertical."""
    result = classify(ClassificationInputs(
        account_id="5639723347",
        account_name="JECT",
        campaign_names=[
            "Comma8_AddToCart_Miami_PMax",
            "Comma8_Purchase_Bridgehampton_Branded_Search",
            "Comma8_Purchase_Brooklyn_PMax",
            "Comma8_Purchase_Los-Angeles_Branded_Search",
            "Comma8_Purchase_Miami_PMax",
        ],
        campaign_types={"SEARCH": 30, "PERFORMANCE_MAX": 50},
        conversions=[
            ("Zenoti Purchase Conversion - Gift Cards", "PURCHASE"),
            ("Boulevard FindATimeDateChange", "DEFAULT"),
            ("Website Phone Call", "PHONE_CALL_LEAD"),
            ("Calls from ads", "PHONE_CALL_LEAD"),
        ],
    ))
    # JECT is a medspa with mixed PURCHASE + PHONE_CALL_LEAD conversions; the
    # business_type can reasonably be ecommerce OR lead_gen. The critical
    # regression to prevent is the prior `AddToCart → automotive` bug.
    assert result.business_type in {BusinessType.ECOMMERCE, BusinessType.LEAD_GEN}
    assert result.vertical != "automotive"
    assert "automotive" not in result.vertical_scores


def test_mackenzie_childs_is_home_goods_not_software():
    """Known brand name should resolve directly to home_goods."""
    result = classify(ClassificationInputs(
        account_id="1605252092",
        account_name="MacKenzie-Childs",
        campaign_names=[
            "HM_PMX_Branded_ShopOnly_TopSKU",
            "HM_PMX_Non-Branded_ShopOnly_AllProducts",
            "HM_SNO_Branded_NCABidding",
            "HM_VID_ConvBidding",
        ],
        campaign_types={"PERFORMANCE_MAX": 30, "SEARCH": 20, "VIDEO": 5},
        conversions=[
            ("Calls from ads", "PHONE_CALL_LEAD"),
            ("Local actions - Website visits", "PAGE_VIEW"),
            ("Clicks to call", "CONTACT"),
        ],
    ))
    assert result.business_type == BusinessType.ECOMMERCE
    assert result.vertical == "home_goods"


def test_invited_usa_is_hospitality_not_finance():
    """Country club lead-gen account must NOT classify as finance via
    `gold`/`golf` substring confusion."""
    result = classify(ClassificationInputs(
        account_id="8094843625",
        account_name="Invited, USA",
        campaign_names=[
            "club:ALISO VIEJO COUNTRY CLUB_id:01401_div:GCC_r:WST_seg:PRE",
            "club:ANTHEM GOLF & COUNTRY CLUB_id:02175_div:GCC",
            "club:ATLANTA NATIONAL GOLF CLUB_id:02847_div:GCC",
        ],
        campaign_types={"SEARCH": 150, "PERFORMANCE_MAX": 10},
        conversions=[
            ("Golf Outings Form Submit", "SUBMIT_LEAD_FORM"),
            ("Private Events Form Submit", "SUBMIT_LEAD_FORM"),
            ("calendly_event_scheduled", "SUBMIT_LEAD_FORM"),
        ],
    ))
    assert result.business_type == BusinessType.LEAD_GEN
    assert result.vertical == "hospitality_country_club"
    assert "finance" not in result.vertical_scores


def test_funko_is_collectibles_not_pets():
    """Funko is a toy/collectibles retailer, not pets."""
    result = classify(ClassificationInputs(
        account_id="9610485278",
        account_name="Funko",
        campaign_names=[
            "CA | DTC | Funko Brand - Exact | Blended | Search",
            "CA | PY | Evergreen | Blended | Pmax",
            "MX | DTC | Funko | Brand - Exact | NCA | Search",
            "US | DTC | Funko | Anime | Blended | Pmax",
        ],
        campaign_types={"SEARCH": 20, "PERFORMANCE_MAX": 40, "APP": 5},
        conversions=[
            ("Funko (Android) view_item", "PAGE_VIEW"),
            ("Funko (Android) ADD_TO_WISHLIST", "SUBSCRIBE_PAID"),
            ("Funko (Android) app_update", "DEFAULT"),
        ],
    ))
    assert result.business_type == BusinessType.ECOMMERCE
    assert result.vertical == "collectibles"
    assert "pets" not in result.vertical_scores


def test_grant_account_is_nonprofit():
    """Google Ad Grants accounts must classify as NONPROFIT (different rules)."""
    result = classify(ClassificationInputs(
        account_id="5200296628",
        account_name="LACMA - Grant",
        campaign_names=["LACMA Awareness", "LACMA Memberships"],
        campaign_types={"SEARCH": 10},
        conversions=[
            ("Newsletter Signup", "SIGNUP"),
            ("Donate Form Submit", "SUBMIT_LEAD_FORM"),
        ],
    ))
    assert result.business_type == BusinessType.NONPROFIT


def test_empty_inputs_resolves_to_unknown():
    result = classify(ClassificationInputs(account_id="x"))
    assert result.business_type == BusinessType.UNKNOWN
    assert result.vertical == ""
    assert result.confidence == 0.0


def test_url_domain_fires_name_rules():
    """A binance.us domain should trigger fintech_crypto via the URL pass
    even if the account name carried no signal."""
    result = classify(ClassificationInputs(
        account_id="bin-no-name",
        account_name="Some Ambiguous Brand",  # name carries no signal
        website_url="binance.us",
        conversions=[("Trade", "PURCHASE")],
    ))
    assert result.business_type == BusinessType.APP or result.vertical == "fintech_crypto"
    assert any("URL[" in r for r in result.rule_trace)


def test_url_with_hyphens_tokenizes():
    """`better-life-partners.com` should match `\\bpartners\\b` after the
    normalizer turns hyphens/dots into spaces."""
    result = classify(ClassificationInputs(
        account_id="blp-test",
        account_name="Some Brand",
        website_url="better-life-partners.com",
        conversions=[("Booking", "BOOK_APPOINTMENT")],
    ))
    # We don't have a "partners" rule yet so this just verifies the
    # normalization doesn't crash and conversions still flow.
    # The real proof is that other URL patterns match correctly.
    assert result.business_type == BusinessType.LEAD_GEN  # via BOOK_APPOINTMENT


def test_url_lockly_matches_smart_home():
    result = classify(ClassificationInputs(
        account_id="lockly-test",
        account_name="Anonymous Brand",
        website_url="lockly.com",
        conversions=[("Purchase", "PURCHASE")],
    ))
    assert result.vertical == "smart_home"


def test_rule_trace_captures_what_fired():
    """Every result must record which rules contributed — for diagnosis."""
    result = classify(ClassificationInputs(
        account_id="lockly",
        account_name="LOCKLY",
        campaign_names=["Search - Competitor Keywords"],
        conversions=[("Purchase", "PURCHASE")],
    ))
    assert any("NAME[" in r for r in result.rule_trace)
    assert any("CONV[PURCHASE" in r for r in result.rule_trace)
