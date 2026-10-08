"""CSV import and validation for opportunity data.

Reads opportunity records from a CSV file, validates field presence, data
types and business constraints, and returns a list of structured
``Opportunity`` objects.

All monetary and numeric fields are parsed as :class:`decimal.Decimal` to
avoid floating point error. Empty rows are skipped. Validation errors are
collected and reported together with enough context (opportunity id, field
name, original value) to locate the problem.

v2 adds optional human-review fields (owner, source, validation_status,
customer_validation_notes, pricing_validation_notes, cost_validation_notes,
reviewer, review_status, review_notes). These are optional: a v1 CSV
without them loads without error. In strict mode, ``validation_status``
and ``review_status`` are enum-validated and the approved/rejected
constraints are enforced.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, fields as dataclass_fields
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config_loader import load_config

# Resolve the project root relative to this module so paths stay portable.
_MODULE_DIR = Path(__file__).resolve().parent


class CSVImportError(Exception):
    """Raised when the input CSV cannot be parsed or validated.

    The message includes every error discovered so the user can fix the
    file in one pass.
    """


@dataclass
class Opportunity:
    """A single opportunity record loaded from CSV."""

    opportunity_id: str
    opportunity_name: str
    customer_segment: str
    industry: str
    region: str
    estimated_units: Decimal
    unit_price: Decimal
    variable_cost_per_unit: Decimal
    fixed_cost: Decimal
    marketing_cost: Decimal
    implementation_cost: Decimal
    expected_monthly_growth: Decimal
    competition_level: str
    customer_need: str
    delivery_difficulty: str
    strategic_fit: str
    initial_investment: Decimal
    expected_monthly_operating_cost: Decimal
    expected_monthly_revenue: Optional[Decimal]
    risk_notes: Optional[str]
    # --- v2 optional human-review fields ---
    owner: Optional[str] = None
    source: Optional[str] = None
    validation_status: Optional[str] = None
    customer_validation_notes: Optional[str] = None
    pricing_validation_notes: Optional[str] = None
    cost_validation_notes: Optional[str] = None
    reviewer: Optional[str] = None
    review_status: Optional[str] = None
    review_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict representation (Decimals become strings)."""
        result: Dict[str, Any] = {}
        for f in dataclass_fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Decimal):
                result[f.name] = str(value)
            else:
                result[f.name] = value
        return result


def _parse_decimal(value: str, field_name: str, opportunity_id: str) -> Decimal:
    """Parse a string into a Decimal, raising a clear error on failure."""
    text = value.strip()
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise CSVImportError(
            f"Opportunity '{opportunity_id}': field '{field_name}' has invalid "
            f"numeric value '{value}' (expected a number)."
        ) from exc


def _is_blank_row(row: Dict[str, str]) -> bool:
    """Return True if every value in the row is empty/whitespace."""
    return all((v or "").strip() == "" for v in row.values())


def load_opportunities(
    csv_path: str,
    config: Optional[Dict[str, Any]] = None,
    strict: bool = False,
) -> List[Opportunity]:
    """Read and validate opportunity records from a CSV file.

    Args:
        csv_path: Path to the CSV file. UTF-8 and UTF-8 BOM are supported.
        config: Optional pre-loaded config dict. If None, the default
            config file is loaded.
        strict: If True, enforce human-review field rules (enum values,
            approved requires reviewer, rejected requires review_notes).

    Returns:
        A list of validated :class:`Opportunity` objects.

    Raises:
        CSVImportError: If the file is missing, required fields are absent,
            or any row fails validation.
    """
    path = Path(csv_path)
    if not path.exists():
        raise CSVImportError(f"Input file not found: {csv_path}")
    if not path.is_file():
        raise CSVImportError(f"Input path is not a file: {csv_path}")

    if config is None:
        from .config_loader import ConfigError

        try:
            config = load_config()
        except ConfigError as exc:
            raise CSVImportError(str(exc)) from exc

    all_fields: List[str] = list(config["fields"])
    optional_fields: List[str] = list(config.get("optional_fields", []))
    required_fields: List[str] = [f for f in all_fields if f not in optional_fields]
    non_negative_fields: List[str] = list(config["non_negative_numeric_fields"])
    optional_numeric_fields: List[str] = list(config["optional_numeric_fields"])
    growth_fields: List[str] = list(config["growth_fields"])
    enum_fields: Dict[str, List[str]] = dict(config["enum_fields"])
    review_enum_fields: Dict[str, List[str]] = dict(config.get("review_enum_fields", {}))
    required_text_fields: List[str] = list(config["required_text_fields"])

    errors: List[str] = []

    # utf-8-sig transparently strips a leading BOM if present.
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []

        missing = [fld for fld in required_fields if fld not in header]
        if missing:
            raise CSVImportError(
                "CSV is missing required field(s): " + ", ".join(missing)
            )

        seen_ids: Dict[str, int] = {}
        opportunities: List[Opportunity] = []

        for line_no, row in enumerate(reader, start=2):  # header is line 1
            if _is_blank_row(row):
                continue

            opp_id = (row.get("opportunity_id") or "").strip()
            row_errors_start = len(errors)

            # --- required text fields ---
            for tf in required_text_fields:
                if not (row.get(tf) or "").strip():
                    errors.append(
                        f"Line {line_no}: field '{tf}' cannot be empty."
                    )

            # --- duplicate id check ---
            if opp_id:
                if opp_id in seen_ids:
                    errors.append(
                        f"Line {line_no}: duplicate opportunity_id "
                        f"'{opp_id}' (first seen on line {seen_ids[opp_id]})."
                    )
                else:
                    seen_ids[opp_id] = line_no

            # --- numeric fields (non-negative) ---
            numeric_values: Dict[str, Decimal] = {}
            for nf in non_negative_fields:
                raw = (row.get(nf) or "").strip()
                if raw == "":
                    errors.append(
                        f"Line {line_no} (opportunity '{opp_id}'): "
                        f"field '{nf}' cannot be empty."
                    )
                    continue
                val = _parse_decimal(raw, nf, opp_id or f"line {line_no}")
                if val < 0:
                    errors.append(
                        f"Line {line_no} (opportunity '{opp_id}'): "
                        f"field '{nf}' must be non-negative, got '{raw}'."
                    )
                    continue
                numeric_values[nf] = val

            # --- optional numeric fields (expected_monthly_revenue) ---
            for of in optional_numeric_fields:
                raw = (row.get(of) or "").strip()
                if raw == "":
                    numeric_values[of] = None  # type: ignore[assignment]
                else:
                    val = _parse_decimal(raw, of, opp_id or f"line {line_no}")
                    if val < 0:
                        errors.append(
                            f"Line {line_no} (opportunity '{opp_id}'): "
                            f"field '{of}' must be non-negative, got '{raw}'."
                        )
                        continue
                    numeric_values[of] = val

            # --- growth fields (decimal, may be negative) ---
            for gf in growth_fields:
                raw = (row.get(gf) or "").strip()
                if raw == "":
                    errors.append(
                        f"Line {line_no} (opportunity '{opp_id}'): "
                        f"field '{gf}' cannot be empty."
                    )
                    continue
                numeric_values[gf] = _parse_decimal(raw, gf, opp_id or f"line {line_no}")

            # --- enum fields ---
            enum_values: Dict[str, str] = {}
            for ef, allowed in enum_fields.items():
                raw = (row.get(ef) or "").strip().lower()
                if raw not in allowed:
                    errors.append(
                        f"Line {line_no} (opportunity '{opp_id}'): "
                        f"field '{ef}' has invalid value '{row.get(ef)}'. "
                        f"Allowed values: {', '.join(allowed)}."
                    )
                    continue
                enum_values[ef] = raw

            # --- review enum fields (only validate if present & strict) ---
            review_values: Dict[str, Optional[str]] = {}
            for ef, allowed in review_enum_fields.items():
                raw = (row.get(ef) or "").strip()
                if raw == "":
                    review_values[ef] = None
                    continue
                raw_lower = raw.lower()
                if raw_lower not in allowed:
                    if strict:
                        errors.append(
                            f"Line {line_no} (opportunity '{opp_id}'): "
                            f"field '{ef}' has invalid value '{raw}'. "
                            f"Allowed values: {', '.join(allowed)}."
                        )
                    review_values[ef] = None
                    continue
                review_values[ef] = raw_lower

            # --- strict-mode review constraints ---
            if strict:
                if review_values.get("review_status") == "approved":
                    reviewer = (row.get("reviewer") or "").strip()
                    if not reviewer:
                        errors.append(
                            f"Line {line_no} (opportunity '{opp_id}'): "
                            f"review_status 'approved' requires a non-empty 'reviewer'."
                        )
                if review_values.get("review_status") == "rejected":
                    notes = (row.get("review_notes") or "").strip()
                    if not notes:
                        errors.append(
                            f"Line {line_no} (opportunity '{opp_id}'): "
                            f"review_status 'rejected' requires non-empty 'review_notes'."
                        )

            # If we hit any errors for this row, skip constructing the object
            # but keep validating the rest of the file.
            if len(errors) > row_errors_start:
                continue

            try:
                opp = Opportunity(
                    opportunity_id=opp_id,
                    opportunity_name=(row.get("opportunity_name") or "").strip(),
                    customer_segment=(row.get("customer_segment") or "").strip(),
                    industry=(row.get("industry") or "").strip(),
                    region=(row.get("region") or "").strip(),
                    estimated_units=numeric_values["estimated_units"],
                    unit_price=numeric_values["unit_price"],
                    variable_cost_per_unit=numeric_values["variable_cost_per_unit"],
                    fixed_cost=numeric_values["fixed_cost"],
                    marketing_cost=numeric_values["marketing_cost"],
                    implementation_cost=numeric_values["implementation_cost"],
                    expected_monthly_growth=numeric_values["expected_monthly_growth"],
                    competition_level=enum_values["competition_level"],
                    customer_need=enum_values["customer_need"],
                    delivery_difficulty=enum_values["delivery_difficulty"],
                    strategic_fit=enum_values["strategic_fit"],
                    initial_investment=numeric_values["initial_investment"],
                    expected_monthly_operating_cost=numeric_values[
                        "expected_monthly_operating_cost"
                    ],
                    expected_monthly_revenue=numeric_values.get("expected_monthly_revenue"),
                    risk_notes=(row.get("risk_notes") or "").strip() or None,
                    owner=(row.get("owner") or "").strip() or None,
                    source=(row.get("source") or "").strip() or None,
                    validation_status=review_values.get("validation_status"),
                    customer_validation_notes=(
                        (row.get("customer_validation_notes") or "").strip() or None
                    ),
                    pricing_validation_notes=(
                        (row.get("pricing_validation_notes") or "").strip() or None
                    ),
                    cost_validation_notes=(
                        (row.get("cost_validation_notes") or "").strip() or None
                    ),
                    reviewer=(row.get("reviewer") or "").strip() or None,
                    review_status=review_values.get("review_status"),
                    review_notes=(row.get("review_notes") or "").strip() or None,
                )
                opportunities.append(opp)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(
                    f"Line {line_no} (opportunity '{opp_id}'): "
                    f"unexpected error building record: {exc}"
                )

    if errors:
        raise CSVImportError(
            "CSV validation failed with "
            f"{len(errors)} error(s):\n  - " + "\n  - ".join(errors)
        )

    if not opportunities:
        raise CSVImportError("No valid opportunity records found in CSV.")

    return opportunities
