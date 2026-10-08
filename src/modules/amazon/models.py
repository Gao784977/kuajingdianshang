"""Dataclasses for the V3 Amazon workflow.

All structured outputs and inputs live here so agents can pass typed
results via :class:`WorkflowContext` instead of poking dicts. Each
dataclass provides ``to_dict`` (JSON-serialisable, Decimals as strings
via :class:`AmazonDecimalEncoder`) and ``from_dict`` (round-trip).

Conventions:
* Monetary fields are :class:`decimal.Decimal`; ratios too.
* Source/confidence propagation uses :class:`Sourced` so every
  significant field carries provenance. ``mock_data`` confidence is
  never ``high``.
* ``AgentResult.output`` stays :data:`typing.Any` for JSON friendliness;
  :meth:`WorkflowContext.get_output` does typed access via
  ``cls.from_dict`` and ``isinstance``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

T = TypeVar("T")

# Allowed source and confidence enums (single source of truth for agents).
ALLOWED_SOURCES = (
    "user_input",
    "mock_data",
    "calculated",
    "imported_csv",
    "imported_xlsx",
    "manual_review",
)
ALLOWED_CONFIDENCE = ("high", "medium", "low", "unknown")

# Final workflow status enum (decision #10).
ALLOWED_FINAL_STATUS = (
    "completed",
    "completed_with_warnings",
    "failed",
    "incomplete",
)

# Agent status enum.
ALLOWED_AGENT_STATUS = (
    "completed",
    "completed_with_warnings",
    "skipped",
    "failed",
    "incomplete",
)


def _to_decimal(value: Any) -> Decimal:
    """Coerce ints/floats/strings to Decimal without float noise."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _decimal_to_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@dataclass
class Sourced(Generic[T]):
    """A value tagged with its source and confidence.

    Sources ∈ :data:`ALLOWED_SOURCES`; confidence ∈
    :data:`ALLOWED_CONFIDENCE`. ``mock_data`` confidence must never be
    ``high`` (enforced by agents, not by this dataclass).
    """

    value: Optional[T]
    source: str = "mock_data"
    confidence: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "source": self.source,
            "confidence": self.confidence,
        }
        v = self.value
        if isinstance(v, Decimal):
            out["value"] = str(v)
        else:
            out["value"] = v
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sourced[Any]":
        return cls(value=data.get("value"), source=data.get("source", "mock_data"),
                   confidence=data.get("confidence", "low"))


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class ProductInput:
    """User-provided product input (loaded from JSON)."""

    keyword: str
    marketplace: str
    target_price_min: Optional[Decimal] = None
    target_price_max: Optional[Decimal] = None
    direction: str = ""
    constraints: List[str] = field(default_factory=list)
    notes: str = ""
    source: str = "user_input"
    confidence: str = "high"
    # Optional user-supplied competitors/reviews overrides (paths or rows)
    competitors_path: Optional[str] = None
    reviews_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "marketplace": self.marketplace,
            "target_price_min": _decimal_to_str(self.target_price_min),
            "target_price_max": _decimal_to_str(self.target_price_max),
            "direction": self.direction,
            "constraints": list(self.constraints),
            "notes": self.notes,
            "source": self.source,
            "confidence": self.confidence,
            "competitors_path": self.competitors_path,
            "reviews_path": self.reviews_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductInput":
        tmin = data.get("target_price_min")
        tmax = data.get("target_price_max")
        return cls(
            keyword=str(data.get("keyword", "")),
            marketplace=str(data.get("marketplace", "")),
            target_price_min=_to_decimal(tmin) if tmin is not None else None,
            target_price_max=_to_decimal(tmax) if tmax is not None else None,
            direction=str(data.get("direction", "")),
            constraints=list(data.get("constraints", []) or []),
            notes=str(data.get("notes", "")),
            source=str(data.get("source", "user_input")),
            confidence=str(data.get("confidence", "high")),
            competitors_path=data.get("competitors_path"),
            reviews_path=data.get("reviews_path"),
        )


@dataclass
class CompetitorRow:
    """A single competitor row (user CSV or mock)."""

    brand: str
    asin: str
    product_name: str
    price: Decimal
    rating: Decimal
    review_count: int
    selling_points: str = ""
    negative_points: str = ""
    source: str = "mock_data"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand": self.brand,
            "asin": self.asin,
            "product_name": self.product_name,
            "price": str(self.price),
            "rating": str(self.rating),
            "review_count": self.review_count,
            "selling_points": self.selling_points,
            "negative_points": self.negative_points,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompetitorRow":
        return cls(
            brand=str(data.get("brand", "")),
            asin=str(data.get("asin", "")),
            product_name=str(data.get("product_name", "")),
            price=_to_decimal(data.get("price")),
            rating=_to_decimal(data.get("rating")),
            review_count=int(data.get("review_count", 0) or 0),
            selling_points=str(data.get("selling_points", "")),
            negative_points=str(data.get("negative_points", "")),
            source=str(data.get("source", "mock_data")),
        )


@dataclass
class ReviewRow:
    """A single review row (user CSV or mock)."""

    review_id: str
    asin: str
    rating: int
    review_text: str
    review_date: str = ""
    source: str = "mock_data"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "asin": self.asin,
            "rating": self.rating,
            "review_text": self.review_text,
            "review_date": self.review_date,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewRow":
        return cls(
            review_id=str(data.get("review_id", "")),
            asin=str(data.get("asin", "")),
            rating=int(data.get("rating", 0) or 0),
            review_text=str(data.get("review_text", "")),
            review_date=str(data.get("review_date", "")),
            source=str(data.get("source", "mock_data")),
        )


# ---------------------------------------------------------------------------
# Agent outputs
# ---------------------------------------------------------------------------


@dataclass
class KeywordOutput:
    """Keyword analysis output (KeywordAgent)."""

    normalized_keyword: str
    related_keywords: List[str] = field(default_factory=list)
    keyword_intent: str = "commercial"
    keyword_type: str = "product"
    competition: str = "medium"
    trend: str = "stable"
    search_volume: Optional[int] = None
    source: str = "mock_data"
    confidence: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "normalized_keyword": self.normalized_keyword,
            "related_keywords": list(self.related_keywords),
            "keyword_intent": self.keyword_intent,
            "keyword_type": self.keyword_type,
            "competition": self.competition,
            "trend": self.trend,
            "search_volume": self.search_volume,
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KeywordOutput":
        return cls(
            normalized_keyword=str(data.get("normalized_keyword", "")),
            related_keywords=list(data.get("related_keywords", []) or []),
            keyword_intent=str(data.get("keyword_intent", "commercial")),
            keyword_type=str(data.get("keyword_type", "product")),
            competition=str(data.get("competition", "medium")),
            trend=str(data.get("trend", "stable")),
            search_volume=data.get("search_volume"),
            source=str(data.get("source", "mock_data")),
            confidence=str(data.get("confidence", "low")),
        )


@dataclass
class MarketOutput:
    """Market analysis output (MarketAgent)."""

    marketplace: str
    category: str = ""
    product_line: str = ""
    consumption_scenario: str = ""
    target_customer: str = ""
    market_capacity: str = "qualitative"
    growth_trend: str = "stable"
    price_range: str = ""
    competition_level: str = "medium"
    opportunity_score: int = 0
    market_assumptions: List[str] = field(default_factory=list)
    source: str = "mock_data"
    confidence: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "marketplace": self.marketplace,
            "category": self.category,
            "product_line": self.product_line,
            "consumption_scenario": self.consumption_scenario,
            "target_customer": self.target_customer,
            "market_capacity": self.market_capacity,
            "growth_trend": self.growth_trend,
            "price_range": self.price_range,
            "competition_level": self.competition_level,
            "opportunity_score": self.opportunity_score,
            "market_assumptions": list(self.market_assumptions),
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketOutput":
        return cls(
            marketplace=str(data.get("marketplace", "")),
            category=str(data.get("category", "")),
            product_line=str(data.get("product_line", "")),
            consumption_scenario=str(data.get("consumption_scenario", "")),
            target_customer=str(data.get("target_customer", "")),
            market_capacity=str(data.get("market_capacity", "qualitative")),
            growth_trend=str(data.get("growth_trend", "stable")),
            price_range=str(data.get("price_range", "")),
            competition_level=str(data.get("competition_level", "medium")),
            opportunity_score=int(data.get("opportunity_score", 0) or 0),
            market_assumptions=list(data.get("market_assumptions", []) or []),
            source=str(data.get("source", "mock_data")),
            confidence=str(data.get("confidence", "low")),
        )


@dataclass
class CompetitorOutput:
    """Competitor analysis output (CompetitorAgent)."""

    competitor_matrix: List[Dict[str, Any]] = field(default_factory=list)
    price_distribution: Dict[str, Any] = field(default_factory=dict)
    rating_distribution: Dict[str, Any] = field(default_factory=dict)
    review_distribution: Dict[str, Any] = field(default_factory=dict)
    common_selling_points: List[str] = field(default_factory=list)
    common_negative_points: List[str] = field(default_factory=list)
    market_gaps: List[str] = field(default_factory=list)
    differentiation_opportunities: List[str] = field(default_factory=list)
    source: str = "mock_data"
    confidence: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "competitor_matrix": list(self.competitor_matrix),
            "price_distribution": dict(self.price_distribution),
            "rating_distribution": dict(self.rating_distribution),
            "review_distribution": dict(self.review_distribution),
            "common_selling_points": list(self.common_selling_points),
            "common_negative_points": list(self.common_negative_points),
            "market_gaps": list(self.market_gaps),
            "differentiation_opportunities": list(self.differentiation_opportunities),
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompetitorOutput":
        return cls(
            competitor_matrix=list(data.get("competitor_matrix", []) or []),
            price_distribution=dict(data.get("price_distribution", {}) or {}),
            rating_distribution=dict(data.get("rating_distribution", {}) or {}),
            review_distribution=dict(data.get("review_distribution", {}) or {}),
            common_selling_points=list(data.get("common_selling_points", []) or []),
            common_negative_points=list(data.get("common_negative_points", []) or []),
            market_gaps=list(data.get("market_gaps", []) or []),
            differentiation_opportunities=list(data.get("differentiation_opportunities", []) or []),
            source=str(data.get("source", "mock_data")),
            confidence=str(data.get("confidence", "low")),
        )


@dataclass
class ReviewOutput:
    """Review analysis output (ReviewAgent)."""

    review_count: int = 0
    sentiment_summary: Dict[str, Any] = field(default_factory=dict)
    issue_categories: Dict[str, int] = field(default_factory=dict)
    positive_themes: List[str] = field(default_factory=list)
    negative_themes: List[str] = field(default_factory=list)
    feature_requests: List[str] = field(default_factory=list)
    quality_issues: List[str] = field(default_factory=list)
    packaging_issues: List[str] = field(default_factory=list)
    product_improvement_directions: List[str] = field(default_factory=list)
    source: str = "mock_data"
    confidence: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_count": self.review_count,
            "sentiment_summary": dict(self.sentiment_summary),
            "issue_categories": dict(self.issue_categories),
            "positive_themes": list(self.positive_themes),
            "negative_themes": list(self.negative_themes),
            "feature_requests": list(self.feature_requests),
            "quality_issues": list(self.quality_issues),
            "packaging_issues": list(self.packaging_issues),
            "product_improvement_directions": list(self.product_improvement_directions),
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewOutput":
        return cls(
            review_count=int(data.get("review_count", 0) or 0),
            sentiment_summary=dict(data.get("sentiment_summary", {}) or {}),
            issue_categories=dict(data.get("issue_categories", {}) or {}),
            positive_themes=list(data.get("positive_themes", []) or []),
            negative_themes=list(data.get("negative_themes", []) or []),
            feature_requests=list(data.get("feature_requests", []) or []),
            quality_issues=list(data.get("quality_issues", []) or []),
            packaging_issues=list(data.get("packaging_issues", []) or []),
            product_improvement_directions=list(data.get("product_improvement_directions", []) or []),
            source=str(data.get("source", "mock_data")),
            confidence=str(data.get("confidence", "low")),
        )


@dataclass
class OpportunityOutput:
    """Opportunity scoring output (OpportunityAgent)."""

    market_opportunity: int = 0
    competition: int = 0
    supply_chain_feasibility: int = 0
    differentiation_potential: int = 0
    development_recommendation: str = "validate_first"
    reasons: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    required_validation: List[str] = field(default_factory=list)
    confidence: str = "low"
    human_review_required: bool = True
    source: str = "calculated"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_opportunity": self.market_opportunity,
            "competition": self.competition,
            "supply_chain_feasibility": self.supply_chain_feasibility,
            "differentiation_potential": self.differentiation_potential,
            "development_recommendation": self.development_recommendation,
            "reasons": list(self.reasons),
            "risks": list(self.risks),
            "required_validation": list(self.required_validation),
            "confidence": self.confidence,
            "human_review_required": self.human_review_required,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpportunityOutput":
        return cls(
            market_opportunity=int(data.get("market_opportunity", 0) or 0),
            competition=int(data.get("competition", 0) or 0),
            supply_chain_feasibility=int(data.get("supply_chain_feasibility", 0) or 0),
            differentiation_potential=int(data.get("differentiation_potential", 0) or 0),
            development_recommendation=str(data.get("development_recommendation", "validate_first")),
            reasons=list(data.get("reasons", []) or []),
            risks=list(data.get("risks", []) or []),
            required_validation=list(data.get("required_validation", []) or []),
            confidence=str(data.get("confidence", "low")),
            human_review_required=bool(data.get("human_review_required", True)),
            source=str(data.get("source", "calculated")),
        )


@dataclass
class ProductOutput:
    """Product development plan output (ProductAgent)."""

    product_name: str = ""
    product_positioning: str = ""
    target_customer: str = ""
    use_scenario: str = ""
    core_selling_points: List[str] = field(default_factory=list)
    functional_design: List[str] = field(default_factory=list)
    differentiation_plan: List[str] = field(default_factory=list)
    target_price: Optional[Decimal] = None
    target_cost: Optional[Decimal] = None
    target_gross_margin: Optional[Decimal] = None
    packaging_direction: str = ""
    installation_direction: str = ""
    development_cycle_days: int = 0
    launch_risks: List[str] = field(default_factory=list)
    validation_plan: List[str] = field(default_factory=list)
    required_supplier_questions: List[str] = field(default_factory=list)
    source: str = "calculated"
    confidence: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_name": self.product_name,
            "product_positioning": self.product_positioning,
            "target_customer": self.target_customer,
            "use_scenario": self.use_scenario,
            "core_selling_points": list(self.core_selling_points),
            "functional_design": list(self.functional_design),
            "differentiation_plan": list(self.differentiation_plan),
            "target_price": _decimal_to_str(self.target_price),
            "target_cost": _decimal_to_str(self.target_cost),
            "target_gross_margin": _decimal_to_str(self.target_gross_margin),
            "packaging_direction": self.packaging_direction,
            "installation_direction": self.installation_direction,
            "development_cycle_days": self.development_cycle_days,
            "launch_risks": list(self.launch_risks),
            "validation_plan": list(self.validation_plan),
            "required_supplier_questions": list(self.required_supplier_questions),
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductOutput":
        return cls(
            product_name=str(data.get("product_name", "")),
            product_positioning=str(data.get("product_positioning", "")),
            target_customer=str(data.get("target_customer", "")),
            use_scenario=str(data.get("use_scenario", "")),
            core_selling_points=list(data.get("core_selling_points", []) or []),
            functional_design=list(data.get("functional_design", []) or []),
            differentiation_plan=list(data.get("differentiation_plan", []) or []),
            target_price=_to_decimal(data.get("target_price")) if data.get("target_price") is not None else None,
            target_cost=_to_decimal(data.get("target_cost")) if data.get("target_cost") is not None else None,
            target_gross_margin=_to_decimal(data.get("target_gross_margin")) if data.get("target_gross_margin") is not None else None,
            packaging_direction=str(data.get("packaging_direction", "")),
            installation_direction=str(data.get("installation_direction", "")),
            development_cycle_days=int(data.get("development_cycle_days", 0) or 0),
            launch_risks=list(data.get("launch_risks", []) or []),
            validation_plan=list(data.get("validation_plan", []) or []),
            required_supplier_questions=list(data.get("required_supplier_questions", []) or []),
            source=str(data.get("source", "calculated")),
            confidence=str(data.get("confidence", "medium")),
        )


# ---------------------------------------------------------------------------
# Profit kernel
# ---------------------------------------------------------------------------


@dataclass
class AmazonProfitInput:
    """Inputs to :func:`calculate_amazon_profit`.

    All monetary fields are :class:`decimal.Decimal`. The 13 cost
    fields follow the V3 spec taxonomy; ``initial_investment`` and
    ``estimated_monthly_units`` drive payback and monthly profit.
    """

    selling_price: Decimal
    unit_cost: Decimal
    inbound_shipping: Decimal = Decimal("0")
    international_shipping: Decimal = Decimal("0")
    customs_duty: Decimal = Decimal("0")
    fba_fee: Decimal = Decimal("0")
    referral_fee: Decimal = Decimal("0")
    storage_fee: Decimal = Decimal("0")
    advertising_cost: Decimal = Decimal("0")
    return_cost: Decimal = Decimal("0")
    other_variable_cost: Decimal = Decimal("0")
    fixed_development_cost: Decimal = Decimal("0")
    initial_investment: Decimal = Decimal("0")
    estimated_monthly_units: int = 0
    monthly_fixed_cost: Decimal = Decimal("0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selling_price": str(self.selling_price),
            "unit_cost": str(self.unit_cost),
            "inbound_shipping": str(self.inbound_shipping),
            "international_shipping": str(self.international_shipping),
            "customs_duty": str(self.customs_duty),
            "fba_fee": str(self.fba_fee),
            "referral_fee": str(self.referral_fee),
            "storage_fee": str(self.storage_fee),
            "advertising_cost": str(self.advertising_cost),
            "return_cost": str(self.return_cost),
            "other_variable_cost": str(self.other_variable_cost),
            "fixed_development_cost": str(self.fixed_development_cost),
            "initial_investment": str(self.initial_investment),
            "estimated_monthly_units": self.estimated_monthly_units,
            "monthly_fixed_cost": str(self.monthly_fixed_cost),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AmazonProfitInput":
        return cls(
            selling_price=_to_decimal(data.get("selling_price")),
            unit_cost=_to_decimal(data.get("unit_cost")),
            inbound_shipping=_to_decimal(data.get("inbound_shipping")),
            international_shipping=_to_decimal(data.get("international_shipping")),
            customs_duty=_to_decimal(data.get("customs_duty")),
            fba_fee=_to_decimal(data.get("fba_fee")),
            referral_fee=_to_decimal(data.get("referral_fee")),
            storage_fee=_to_decimal(data.get("storage_fee")),
            advertising_cost=_to_decimal(data.get("advertising_cost")),
            return_cost=_to_decimal(data.get("return_cost")),
            other_variable_cost=_to_decimal(data.get("other_variable_cost")),
            fixed_development_cost=_to_decimal(data.get("fixed_development_cost")),
            initial_investment=_to_decimal(data.get("initial_investment")),
            estimated_monthly_units=int(data.get("estimated_monthly_units", 0) or 0),
            monthly_fixed_cost=_to_decimal(data.get("monthly_fixed_cost")),
        )


@dataclass
class AmazonProfitResult:
    """Profit result for one scenario.

    Carries the scenario-adjusted cost values plus the derived metrics
    (unit_profit, unit_margin, monthly_profit, annualized_profit, roi).
    ``roi`` is ``None`` when ``initial_investment <= 0``.
    """

    scenario: str
    selling_price: Decimal
    unit_cost: Decimal
    inbound_shipping: Decimal
    international_shipping: Decimal
    customs_duty: Decimal
    fba_fee: Decimal
    referral_fee: Decimal
    storage_fee: Decimal
    advertising_cost: Decimal
    return_cost: Decimal
    other_variable_cost: Decimal
    fixed_development_cost: Decimal
    initial_investment: Decimal
    estimated_monthly_units: int
    monthly_fixed_cost: Decimal
    total_variable_cost_per_unit: Decimal
    unit_profit: Decimal
    unit_margin: Decimal
    monthly_profit: Decimal
    annualized_profit: Decimal
    roi: Optional[Decimal]
    calculation_version: str = "amazon_calculation_v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "selling_price": str(self.selling_price),
            "unit_cost": str(self.unit_cost),
            "inbound_shipping": str(self.inbound_shipping),
            "international_shipping": str(self.international_shipping),
            "customs_duty": str(self.customs_duty),
            "fba_fee": str(self.fba_fee),
            "referral_fee": str(self.referral_fee),
            "storage_fee": str(self.storage_fee),
            "advertising_cost": str(self.advertising_cost),
            "return_cost": str(self.return_cost),
            "other_variable_cost": str(self.other_variable_cost),
            "fixed_development_cost": str(self.fixed_development_cost),
            "initial_investment": str(self.initial_investment),
            "estimated_monthly_units": self.estimated_monthly_units,
            "monthly_fixed_cost": str(self.monthly_fixed_cost),
            "total_variable_cost_per_unit": str(self.total_variable_cost_per_unit),
            "unit_profit": str(self.unit_profit),
            "unit_margin": str(self.unit_margin),
            "monthly_profit": str(self.monthly_profit),
            "annualized_profit": str(self.annualized_profit),
            "roi": _decimal_to_str(self.roi),
            "calculation_version": self.calculation_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AmazonProfitResult":
        return cls(
            scenario=str(data.get("scenario", "base")),
            selling_price=_to_decimal(data.get("selling_price")),
            unit_cost=_to_decimal(data.get("unit_cost")),
            inbound_shipping=_to_decimal(data.get("inbound_shipping")),
            international_shipping=_to_decimal(data.get("international_shipping")),
            customs_duty=_to_decimal(data.get("customs_duty")),
            fba_fee=_to_decimal(data.get("fba_fee")),
            referral_fee=_to_decimal(data.get("referral_fee")),
            storage_fee=_to_decimal(data.get("storage_fee")),
            advertising_cost=_to_decimal(data.get("advertising_cost")),
            return_cost=_to_decimal(data.get("return_cost")),
            other_variable_cost=_to_decimal(data.get("other_variable_cost")),
            fixed_development_cost=_to_decimal(data.get("fixed_development_cost")),
            initial_investment=_to_decimal(data.get("initial_investment")),
            estimated_monthly_units=int(data.get("estimated_monthly_units", 0) or 0),
            monthly_fixed_cost=_to_decimal(data.get("monthly_fixed_cost")),
            total_variable_cost_per_unit=_to_decimal(data.get("total_variable_cost_per_unit")),
            unit_profit=_to_decimal(data.get("unit_profit")),
            unit_margin=_to_decimal(data.get("unit_margin")),
            monthly_profit=_to_decimal(data.get("monthly_profit")),
            annualized_profit=_to_decimal(data.get("annualized_profit")),
            roi=_to_decimal(data.get("roi")) if data.get("roi") is not None else None,
            calculation_version=str(data.get("calculation_version", "amazon_calculation_v1")),
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Result of a single agent run.

    ``output`` is intentionally :data:`typing.Any` for JSON friendliness;
    downstream agents should use :meth:`WorkflowContext.get_output` for
    typed access.
    """

    agent_name: str
    status: str
    input_summary: Dict[str, Any] = field(default_factory=dict)
    output: Any = None
    warnings: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    source: str = "calculated"
    version: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "agent_name": self.agent_name,
            "status": self.status,
            "input_summary": dict(self.input_summary),
            "warnings": list(self.warnings),
            "assumptions": list(self.assumptions),
            "source": self.source,
            "version": self.version,
        }
        if self.output is not None and hasattr(self.output, "to_dict"):
            out["output"] = self.output.to_dict()
        else:
            out["output"] = self.output
        if self.error is not None:
            out["error"] = self.error
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResult":
        return cls(
            agent_name=str(data.get("agent_name", "")),
            status=str(data.get("status", "completed")),
            input_summary=dict(data.get("input_summary", {}) or {}),
            output=data.get("output"),
            warnings=list(data.get("warnings", []) or []),
            assumptions=list(data.get("assumptions", []) or []),
            source=str(data.get("source", "calculated")),
            version=str(data.get("version", "")),
            error=data.get("error"),
        )


@dataclass
class WorkflowContext:
    """Shared context passed through the agent pipeline.

    Holds agent results, final workflow status, CLI args, loaded config
    snapshot and the product input. ``get_output`` does typed access via
    ``cls.from_dict`` (raises if the agent is missing or skipped).
    """

    product_input: Optional[ProductInput] = None
    config: Dict[str, Any] = field(default_factory=dict)
    config_sha256: str = ""
    cli_args: Dict[str, Any] = field(default_factory=dict)
    agents: Dict[str, AgentResult] = field(default_factory=dict)
    final_status: str = "incomplete"
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    input_sha256: Optional[str] = None
    generated_at: str = ""
    python_version: str = ""
    agent_order: List[str] = field(default_factory=list)

    def set_result(self, agent_name: str, result: AgentResult) -> None:
        self.agents[agent_name] = result

    def get_result(self, agent_name: str) -> Optional[AgentResult]:
        return self.agents.get(agent_name)

    def get_output(self, agent_name: str, cls: Type[T]) -> Optional[T]:
        """Typed access to an agent's output.

        Returns ``None`` if the agent didn't run or its output is None.
        Raises :class:`TypeError` if the stored output is not the
        expected type and cannot be coerced via ``cls.from_dict``.
        """
        result = self.agents.get(agent_name)
        if result is None or result.output is None:
            return None
        out = result.output
        if isinstance(out, cls):
            return out
        if isinstance(out, dict) and hasattr(cls, "from_dict"):
            return cls.from_dict(out)  # type: ignore[attr-defined]
        raise TypeError(
            f"Agent '{agent_name}' output is {type(out).__name__}, "
            f"expected {cls.__name__}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_input": self.product_input.to_dict() if self.product_input else None,
            "config": dict(self.config),
            "config_sha256": self.config_sha256,
            "cli_args": dict(self.cli_args),
            "agents": {name: r.to_dict() for name, r in self.agents.items()},
            "final_status": self.final_status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "input_sha256": self.input_sha256,
            "generated_at": self.generated_at,
            "python_version": self.python_version,
            "agent_order": list(self.agent_order),
        }


# ---------------------------------------------------------------------------
# JSON encoder (replicates V1/V2 _DecimalEncoder; cross-module import
# would violate convention per architecture decision #4).
# ---------------------------------------------------------------------------


class AmazonDecimalEncoder(json.JSONEncoder):
    """JSON encoder that serializes :class:`Decimal` values as strings.

    Replicates :class:`src.modules.project_report._DecimalEncoder`; kept
    private in V1/V2 so V3 owns its own copy to avoid cross-module
    private imports.
    """

    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)
