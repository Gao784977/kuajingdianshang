"""Configuration loading and validation for the V3 Amazon workflow.

Loads ``config/amazon_workflow.json`` and exposes workflow version,
agent versions, supported marketplaces, opportunity scoring weights,
mock-data settings, profit cost defaults, three scenarios (base /
optimistic / pessimistic) with Amazon-specific multipliers, review
categories, output settings and confidence rules. The config is
validated structurally and any failure raises :class:`AmazonConfigError`
with the offending field named.

Single source of truth: :data:`_AMAZON_MULTIPLIER_KEYS` is shared with
:mod:`src.modules.amazon.profit_agent` (apply) so a typo in either the
config or the calculator surfaces loudly.

This module never touches V1/V2 :mod:`src.modules.config_loader` or
``config/opportunity_config.json``; V3 owns its own config entirely.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .models import ALLOWED_CONFIDENCE, ALLOWED_SOURCES

_MODULE_DIR = Path(__file__).resolve().parent
# amazon_config.py lives at src/modules/amazon/, so .parent.parent.parent
# walks up to the project root (where config/ lives).
_DEFAULT_CONFIG_PATH = _MODULE_DIR.parent.parent.parent / "config" / "amazon_workflow.json"

# Single source of truth for Amazon scenario multiplier keys (decision #6).
# Shared with profit_agent.py — both apply (profit_agent) and validate
# (this module) use the same names so typos surface immediately.
_AMAZON_MULTIPLIER_KEYS: Tuple[str, ...] = (
    "selling_price_multiplier",
    "units_multiplier",
    "unit_cost_multiplier",
    "fba_fee_multiplier",
    "referral_fee_multiplier",
    "storage_fee_multiplier",
    "advertising_cost_multiplier",
    "return_cost_multiplier",
    "fixed_development_cost_multiplier",
)

# Scoring sub-components whose weights must sum to 100 (matches
# OpportunityOutput dimensions in models.py).
_SCORE_COMPONENTS: Tuple[str, ...] = (
    "market_opportunity",
    "competition",
    "supply_chain_feasibility",
    "differentiation_potential",
)


class AmazonConfigError(Exception):
    """Raised when the Amazon workflow config is missing or invalid."""


def _config_path(config_path: Optional[str] = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    return _DEFAULT_CONFIG_PATH


def load_amazon_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load and validate the Amazon workflow config JSON file.

    Args:
        config_path: Optional explicit path. Defaults to
            ``config/amazon_workflow.json`` relative to the project root.

    Returns:
        The validated config dict.

    Raises:
        AmazonConfigError: If the file is missing, malformed JSON, or
            fails structural/business-rule validation.
    """
    path = _config_path(config_path)
    if not path.exists():
        raise AmazonConfigError(f"Amazon config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise AmazonConfigError(f"Amazon config is not valid JSON: {exc}") from exc

    _validate_amazon_config(config)
    return config


def _validate_amazon_config(config: Dict[str, Any]) -> None:
    """Validate structure and business rules; raise on any violation."""
    # --- top-level required keys ---
    for key in (
        "workflow_version",
        "calculation_version",
        "agent_versions",
        "supported_marketplaces",
        "score_rules",
        "mock_data_settings",
        "profit_cost_defaults",
        "scenarios",
        "review_categories",
        "output_settings",
        "confidence_rules",
    ):
        if key not in config:
            raise AmazonConfigError(f"Amazon config missing required key '{key}'.")

    # --- workflow_version + calculation_version must be non-empty strings ---
    if not isinstance(config["workflow_version"], str) or not config["workflow_version"]:
        raise AmazonConfigError("Amazon config 'workflow_version' must be a non-empty string.")
    if not isinstance(config["calculation_version"], str) or not config["calculation_version"]:
        raise AmazonConfigError("Amazon config 'calculation_version' must be a non-empty string.")

    # --- agent_versions ---
    av = config["agent_versions"]
    if not isinstance(av, dict) or not av:
        raise AmazonConfigError("Amazon config 'agent_versions' must be a non-empty object.")
    for name, version in av.items():
        if not isinstance(version, str) or not version:
            raise AmazonConfigError(
                f"Amazon config 'agent_versions.{name}' must be a non-empty string."
            )

    # --- supported_marketplaces ---
    sm = config["supported_marketplaces"]
    if not isinstance(sm, list) or not sm:
        raise AmazonConfigError("Amazon config 'supported_marketplaces' must be a non-empty list.")
    for m in sm:
        if not isinstance(m, str) or not m:
            raise AmazonConfigError(
                f"Amazon config 'supported_marketplaces' entry {m!r} must be a non-empty string."
            )

    # --- score_rules: weights must sum to 100 ---
    sr = config["score_rules"]
    if not isinstance(sr, dict) or not sr:
        raise AmazonConfigError("Amazon config 'score_rules' must be a non-empty object.")
    missing = [c for c in _SCORE_COMPONENTS if c not in sr]
    if missing:
        raise AmazonConfigError(
            f"Amazon config 'score_rules' missing components: {missing}."
        )
    total = 0
    for comp in _SCORE_COMPONENTS:
        v = sr[comp]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise AmazonConfigError(
                f"Amazon config 'score_rules.{comp}' must be a number (got {type(v).__name__})."
            )
        if v < 0:
            raise AmazonConfigError(
                f"Amazon config 'score_rules.{comp}' must be non-negative (got {v})."
            )
        total += v
    if total != 100:
        raise AmazonConfigError(
            f"Amazon config 'score_rules' weights must sum to 100 (got {total})."
        )

    # --- mock_data_settings ---
    mds = config["mock_data_settings"]
    if not isinstance(mds, dict):
        raise AmazonConfigError("Amazon config 'mock_data_settings' must be an object.")

    # --- profit_cost_defaults: non-negative numbers ---
    pcd = config["profit_cost_defaults"]
    if not isinstance(pcd, dict) or not pcd:
        raise AmazonConfigError("Amazon config 'profit_cost_defaults' must be a non-empty object.")
    for k, v in pcd.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise AmazonConfigError(
                f"Amazon config 'profit_cost_defaults.{k}' must be a number "
                f"(got {type(v).__name__})."
            )
        if v < 0:
            raise AmazonConfigError(
                f"Amazon config 'profit_cost_defaults.{k}' must be non-negative (got {v})."
            )

    # --- scenarios: each must have exactly the _AMAZON_MULTIPLIER_KEYS, numeric >= 0 ---
    scen = config["scenarios"]
    if not isinstance(scen, dict) or not scen:
        raise AmazonConfigError("Amazon config 'scenarios' must be a non-empty object.")
    # At least base/optimistic/pessimistic are required.
    for required in ("base", "optimistic", "pessimistic"):
        if required not in scen:
            raise AmazonConfigError(
                f"Amazon config 'scenarios' missing required scenario '{required}'."
            )
    for name, mults in scen.items():
        if not isinstance(mults, dict):
            raise AmazonConfigError(f"Amazon config 'scenarios.{name}' must be an object.")
        # Reject unknown keys (typos) loudly.
        unknown = [k for k in mults if k not in _AMAZON_MULTIPLIER_KEYS]
        if unknown:
            raise AmazonConfigError(
                f"Amazon config 'scenarios.{name}' has unknown multiplier keys: {unknown}. "
                f"Allowed: {list(_AMAZON_MULTIPLIER_KEYS)}"
            )
        # Reject missing keys.
        missing = [k for k in _AMAZON_MULTIPLIER_KEYS if k not in mults]
        if missing:
            raise AmazonConfigError(
                f"Amazon config 'scenarios.{name}' missing multipliers: {missing}."
            )
        # Numeric and >= 0.
        for k in _AMAZON_MULTIPLIER_KEYS:
            v = mults[k]
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise AmazonConfigError(
                    f"Amazon config 'scenarios.{name}.{k}' must be a number "
                    f"(got {type(v).__name__})."
                )
            if v < 0:
                raise AmazonConfigError(
                    f"Amazon config 'scenarios.{name}.{k}' must be non-negative (got {v})."
                )

    # --- review_categories ---
    rc = config["review_categories"]
    if not isinstance(rc, list) or not rc:
        raise AmazonConfigError("Amazon config 'review_categories' must be a non-empty list.")
    for c in rc:
        if not isinstance(c, str) or not c:
            raise AmazonConfigError(
                f"Amazon config 'review_categories' entry {c!r} must be a non-empty string."
            )

    # --- output_settings ---
    os_cfg = config["output_settings"]
    if not isinstance(os_cfg, dict):
        raise AmazonConfigError("Amazon config 'output_settings' must be an object.")
    for k in ("default_output_dir", "markdown_template", "json_template",
              "market_excel_template", "product_excel_template", "intermediate_dir"):
        if k not in os_cfg:
            raise AmazonConfigError(f"Amazon config 'output_settings' missing key '{k}'.")

    # --- confidence_rules: source -> confidence enum ---
    cr = config["confidence_rules"]
    if not isinstance(cr, dict) or not cr:
        raise AmazonConfigError("Amazon config 'confidence_rules' must be a non-empty object.")
    for src, conf in cr.items():
        if src not in ALLOWED_SOURCES:
            raise AmazonConfigError(
                f"Amazon config 'confidence_rules' has unknown source {src!r}; "
                f"allowed: {list(ALLOWED_SOURCES)}"
            )
        if conf not in ALLOWED_CONFIDENCE:
            raise AmazonConfigError(
                f"Amazon config 'confidence_rules.{src}' has invalid confidence {conf!r}; "
                f"allowed: {list(ALLOWED_CONFIDENCE)}"
            )
        # Decision #7: mock_data confidence never high.
        if src == "mock_data" and conf == "high":
            raise AmazonConfigError(
                "Amazon config 'confidence_rules.mock_data' must not be 'high' "
                "(mock data is never high-confidence)."
            )


def compute_amazon_config_sha256(config: Dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON serialization of the config dict.

    We hash the actual config used (not the file path) because the spec
    requires the report to record the full configuration content — a
    config file may be modified later, breaking reproducibility if only
    the path were recorded. Keys are sorted for deterministic output.
    """
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
