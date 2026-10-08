"""Deterministic mock data fixtures for the V3 Amazon workflow.

All functions here are pure: same input produces the same output, no
randomness, no time-dependent values, no network calls. The mock data
centres on the "chicken coop door" product line on Amazon US, matching
``config/amazon_workflow.json:mock_data_settings`` and
``profit_cost_defaults``.

Per architecture decision #7, every value sourced from this module
carries ``source="mock_data"`` and ``confidence="low"`` (mock data is
never high-confidence). The merge layer in :mod:`input_loader` decides
when mock data fills gaps versus when user input wins.

The mock data is intentionally small but realistic enough to exercise
every agent: 4 competitors, 12 reviews spanning 5 pain categories, a
keyword cluster, and qualitative market values. Profit inputs come
from ``config.profit_cost_defaults`` so the numbers stay in sync with
the validated config.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from .models import (
    CompetitorRow,
    KeywordOutput,
    MarketOutput,
    ReviewRow,
    AmazonProfitInput,
)


# ---------------------------------------------------------------------------
# Keyword mock
# ---------------------------------------------------------------------------


def get_mock_keyword() -> KeywordOutput:
    """Return the deterministic mock keyword analysis for "chicken coop door".

    Same call always returns the same object (dataclass equality).
    Confidence is ``low`` because this is mock data, not real search
    volume data.
    """
    return KeywordOutput(
        normalized_keyword="chicken coop door",
        related_keywords=[
            "automatic chicken coop door",
            "poultry house door opener",
            "chicken coop door opener",
            "auto coop door",
            "solar chicken coop door",
        ],
        keyword_intent="commercial",
        keyword_type="product",
        competition="medium",
        trend="stable",
        search_volume=None,  # mock data: real volume requires an API
        source="mock_data",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Market mock
# ---------------------------------------------------------------------------


def get_mock_market(marketplace: str = "amazon_us") -> MarketOutput:
    """Return the deterministic mock market analysis.

    The opportunity score is a qualitative 1-100 value derived from the
    chicken coop door niche: moderate competition, growing backyard
    poultry trend, clear price band.
    """
    return MarketOutput(
        marketplace=marketplace,
        category="Pet Supplies > Livestock Supplies > Poultry",
        product_line="Chicken Coop Accessories",
        consumption_scenario=(
            "Backyard poultry keeping; predator protection at night; "
            "automated dawn/dusk door control"
        ),
        target_customer=(
            "Backyard chicken keepers, hobby farmers, small-scale "
            "poultry owners in suburban and rural areas"
        ),
        market_capacity="qualitative",
        growth_trend="growing",
        price_range="$20 - $50",
        competition_level="medium",
        opportunity_score=75,
        market_assumptions=[
            "Backyard poultry trend is growing post-2020",
            "Solar-powered and light-sensor models are mainstream",
            "Predator protection (raccoons, foxes) is the primary pain point",
            "Amazon US is the dominant channel for this niche",
            "Price sensitivity increases above $40",
        ],
        source="mock_data",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Competitor mock
# ---------------------------------------------------------------------------


def get_mock_competitors() -> List[CompetitorRow]:
    """Return 4 deterministic mock competitors (MOCK-ASIN-001..004).

    Each row carries ``source="mock_data"`` so downstream agents can
    distinguish mock from user-provided CSV competitors.
    """
    return [
        CompetitorRow(
            brand="PetsFit",
            asin="MOCK-ASIN-001",
            product_name="PetsFit Automatic Chicken Coop Door",
            price=Decimal("32.99"),
            rating=Decimal("4.2"),
            review_count=856,
            selling_points="Solar powered; waterproof; light sensor",
            negative_points="Hard to install; instructions unclear; motor noise",
            source="mock_data",
        ),
        CompetitorRow(
            brand="RentACoop",
            asin="MOCK-ASIN-002",
            product_name="RentACoop Auto Chicken Coop Door Kit",
            price=Decimal("39.99"),
            rating=Decimal("4.5"),
            review_count=1240,
            selling_points="Easy setup; reliable timer; sturdy frame",
            negative_points="Motor fails after 6 months; expensive; heavy",
            source="mock_data",
        ),
        CompetitorRow(
            brand="Manna Pro",
            asin="MOCK-ASIN-003",
            product_name="Manna Pro Digital Chicken Coop Door",
            price=Decimal("28.99"),
            rating=Decimal("3.8"),
            review_count=420,
            selling_points="Affordable; light sensor; compact design",
            negative_points="Flimsy packaging; door jams; weak motor",
            source="mock_data",
        ),
        CompetitorRow(
            brand="Hooyon",
            asin="MOCK-ASIN-004",
            product_name="Hooyon Poultry House Door Opener",
            price=Decimal("45.99"),
            rating=Decimal("4.0"),
            review_count=680,
            selling_points="Heavy duty; predator proof; dual power (solar + plug)",
            negative_points="Complex wiring; missing parts; long shipping",
            source="mock_data",
        ),
    ]


# ---------------------------------------------------------------------------
# Review mock
# ---------------------------------------------------------------------------


def get_mock_reviews() -> List[ReviewRow]:
    """Return 12 deterministic mock reviews.

    Reviews span 5 of the 7 configured pain categories:
    installation, quality, packaging, feature_request, price, shipping.
    Ratings and text are fixed so :mod:`review_agent` classification is
    deterministic and reproducible across runs.
    """
    return [
        # --- installation ---
        ReviewRow(
            review_id="MOCK-REV-001",
            asin="MOCK-ASIN-001",
            rating=2,
            review_text=(
                "Installation was a nightmare. The instructions made no "
                "sense and I had to drill extra holes to mount it."
            ),
            review_date="2026-08-15",
            source="mock_data",
        ),
        ReviewRow(
            review_id="MOCK-REV-002",
            asin="MOCK-ASIN-002",
            rating=5,
            review_text=(
                "Easy to install with clear instructions. Timer works "
                "great and my chickens are safe at night."
            ),
            review_date="2026-08-20",
            source="mock_data",
        ),
        ReviewRow(
            review_id="MOCK-REV-003",
            asin="MOCK-ASIN-004",
            rating=3,
            review_text=(
                "Complex wiring, took me 3 hours to install. Works ok "
                "now but setup was frustrating."
            ),
            review_date="2026-09-01",
            source="mock_data",
        ),
        # --- quality ---
        ReviewRow(
            review_id="MOCK-REV-004",
            asin="MOCK-ASIN-001",
            rating=3,
            review_text=(
                "Door works but the motor failed after 6 months. "
                "Quality is questionable for the price."
            ),
            review_date="2026-07-10",
            source="mock_data",
        ),
        ReviewRow(
            review_id="MOCK-REV-005",
            asin="MOCK-ASIN-003",
            rating=3,
            review_text=(
                "Affordable but the door warped after 2 months of rain. "
                "Material quality is poor."
            ),
            review_date="2026-08-05",
            source="mock_data",
        ),
        ReviewRow(
            review_id="MOCK-REV-006",
            asin="MOCK-ASIN-004",
            rating=4,
            review_text=(
                "Heavy duty and predator proof. Works well so far, "
                "good quality build."
            ),
            review_date="2026-09-10",
            source="mock_data",
        ),
        # --- packaging ---
        ReviewRow(
            review_id="MOCK-REV-007",
            asin="MOCK-ASIN-002",
            rating=2,
            review_text=(
                "Packaging was damaged on arrival and missing screws. "
                "Had to buy my own hardware."
            ),
            review_date="2026-07-25",
            source="mock_data",
        ),
        ReviewRow(
            review_id="MOCK-REV-008",
            asin="MOCK-ASIN-003",
            rating=1,
            review_text=(
                "Flimsy packaging, arrived broken. The door panel was "
                "cracked in transit."
            ),
            review_date="2026-08-12",
            source="mock_data",
        ),
        # --- feature_request ---
        ReviewRow(
            review_id="MOCK-REV-009",
            asin="MOCK-ASIN-001",
            rating=4,
            review_text=(
                "Decent door but I wish it had wifi control and app "
                "integration to check remotely."
            ),
            review_date="2026-09-05",
            source="mock_data",
        ),
        ReviewRow(
            review_id="MOCK-REV-010",
            asin="MOCK-ASIN-002",
            rating=4,
            review_text=(
                "Good value for the price. Would love to see app "
                "control and scheduling features in the next version."
            ),
            review_date="2026-09-15",
            source="mock_data",
        ),
        # --- price ---
        ReviewRow(
            review_id="MOCK-REV-011",
            asin="MOCK-ASIN-003",
            rating=2,
            review_text=(
                "Too expensive for the quality you get. Broke after "
                "just 2 months, not worth it."
            ),
            review_date="2026-08-28",
            source="mock_data",
        ),
        # --- shipping ---
        ReviewRow(
            review_id="MOCK-REV-012",
            asin="MOCK-ASIN-004",
            rating=4,
            review_text=(
                "Good product but shipping took 3 weeks. The door "
                "itself is solid and works as advertised."
            ),
            review_date="2026-09-18",
            source="mock_data",
        ),
    ]


# ---------------------------------------------------------------------------
# Profit input mock (sourced from config.profit_cost_defaults)
# ---------------------------------------------------------------------------


def get_mock_profit_input(config: Dict[str, Any]) -> AmazonProfitInput:
    """Build an :class:`AmazonProfitInput` from ``config.profit_cost_defaults``.

    Keeps the mock profit numbers in sync with the validated config so a
    config change propagates without editing this module. All monetary
    values are converted to :class:`Decimal` to avoid float noise.
    """
    defaults: Dict[str, Any] = config.get("profit_cost_defaults", {})

    def _d(key: str) -> Decimal:
        return Decimal(str(defaults.get(key, 0)))

    return AmazonProfitInput(
        selling_price=_d("selling_price"),
        unit_cost=_d("unit_cost"),
        inbound_shipping=_d("inbound_shipping"),
        international_shipping=_d("international_shipping"),
        customs_duty=_d("customs_duty"),
        fba_fee=_d("fba_fee"),
        referral_fee=_d("referral_fee"),
        storage_fee=_d("storage_fee"),
        advertising_cost=_d("advertising_cost"),
        return_cost=_d("return_cost"),
        other_variable_cost=_d("other_variable_cost"),
        fixed_development_cost=_d("fixed_development_cost"),
        initial_investment=_d("initial_investment"),
        estimated_monthly_units=int(defaults.get("estimated_monthly_units", 0)),
        monthly_fixed_cost=_d("monthly_fixed_cost"),
    )
