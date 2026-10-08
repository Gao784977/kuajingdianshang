"""Configuration loading and validation for the opportunity analysis tool.

Loads ``config/opportunity_config.json`` and exposes the scoring rules,
scenario multipliers, sensitivity parameters and field schema. Scoring
rules are config-driven: the weights must sum to 100, thresholds must be
monotonically decreasing, and every scoring version referenced must exist
in the config.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_MODULE_DIR = Path(__file__).resolve().parent
_DEFAULT_CONFIG_PATH = _MODULE_DIR.parent.parent / "config" / "opportunity_config.json"

# The four scoring sub-components whose weights must sum to 100.
_WEIGHT_COMPONENTS = ("demand", "economics", "strategy", "feasibility")


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


def _config_path(config_path: Optional[str] = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    return _DEFAULT_CONFIG_PATH


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load and validate the opportunity config JSON file.

    Args:
        config_path: Optional explicit path. Defaults to
            ``config/opportunity_config.json`` relative to the project root.

    Returns:
        The validated config dict.

    Raises:
        ConfigError: If the file is missing, malformed, or fails validation.
    """
    path = _config_path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {exc}") from exc

    _validate_config(config)
    return config


def _validate_config(config: Dict[str, Any]) -> None:
    """Validate the structure and business rules of the config."""
    # --- scoring rules ---
    if "scoring_rules" not in config or not isinstance(config["scoring_rules"], dict):
        raise ConfigError("Config missing 'scoring_rules' object.")

    for version, rules in config["scoring_rules"].items():
        _validate_scoring_rules(version, rules)

    # --- scenarios ---
    if "scenarios" not in config or not isinstance(config["scenarios"], dict):
        raise ConfigError("Config missing 'scenarios' object.")
    for name, scen in config["scenarios"].items():
        if not isinstance(scen, dict):
            raise ConfigError(f"Scenario '{name}' must be an object.")
        for key in (
            "unit_price_multiplier",
            "units_multiplier",
            "variable_cost_multiplier",
            "fixed_cost_multiplier",
            "marketing_cost_multiplier",
            "implementation_cost_multiplier",
            "operating_cost_multiplier",
        ):
            if key not in scen:
                raise ConfigError(f"Scenario '{name}' missing multiplier '{key}'.")

    # --- sensitivity ---
    sens = config.get("sensitivity")
    if sens is not None:
        if "parameters" not in sens or not isinstance(sens["parameters"], list):
            raise ConfigError("Config 'sensitivity.parameters' must be a list.")
        if "range_percents" not in sens or not isinstance(sens["range_percents"], list):
            raise ConfigError("Config 'sensitivity.range_percents' must be a list.")

    # --- enum consistency: scoring enum values must match input enum fields ---
    enum_fields = config.get("enum_fields", {})
    for version, rules in config["scoring_rules"].items():
        for field_name in (
            "customer_need_scores",
            "strategic_fit_scores",
            "delivery_difficulty_scores",
            "competition_penalties",
        ):
            cfg_field = field_name.replace("_scores", "").replace("_penalties", "")
            # Map scoring field names to enum field names.
            mapping = {
                "customer_need_scores": "customer_need",
                "strategic_fit_scores": "strategic_fit",
                "delivery_difficulty_scores": "delivery_difficulty",
                "competition_penalties": "competition_level",
            }
            enum_field = mapping[field_name]
            allowed = enum_fields.get(enum_field, [])
            for key in rules.get(field_name, {}):
                if key not in allowed:
                    raise ConfigError(
                        f"Scoring version '{version}': field '{field_name}' has key "
                        f"'{key}' which is not an allowed value for '{enum_field}' "
                        f"(allowed: {allowed})."
                    )


def _validate_scoring_rules(version: str, rules: Dict[str, Any]) -> None:
    weights = rules.get("score_weights")
    if not isinstance(weights, dict):
        raise ConfigError(
            f"Scoring version '{version}': missing 'score_weights' object."
        )
    weight_sum = 0
    for comp in _WEIGHT_COMPONENTS:
        if comp not in weights:
            raise ConfigError(
                f"Scoring version '{version}': score_weights missing '{comp}'."
            )
        try:
            weight_sum += int(weights[comp])
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"Scoring version '{version}': score_weights['{comp}'] is not an integer."
            ) from exc
    if weight_sum != 100:
        raise ConfigError(
            f"Scoring version '{version}': score_weights sum to {weight_sum}, "
            f"expected 100."
        )

    # grade thresholds must be present and monotonically decreasing A>B>C>D
    thresholds = rules.get("grade_thresholds")
    if not isinstance(thresholds, dict):
        raise ConfigError(
            f"Scoring version '{version}': missing 'grade_thresholds' object."
        )
    for grade in ("A", "B", "C", "D"):
        if grade not in thresholds:
            raise ConfigError(
                f"Scoring version '{version}': grade_thresholds missing '{grade}'."
            )
    if not (
        thresholds["A"] > thresholds["B"] > thresholds["C"] >= thresholds["D"]
    ):
        raise ConfigError(
            f"Scoring version '{version}': grade_thresholds must be "
            "A > B > C >= D."
        )

    for field_name in (
        "customer_need_scores",
        "strategic_fit_scores",
        "delivery_difficulty_scores",
        "competition_penalties",
    ):
        if field_name not in rules or not isinstance(rules[field_name], dict):
            raise ConfigError(
                f"Scoring version '{version}': missing '{field_name}' object."
            )

    bands = rules.get("economics_score_bands")
    if not isinstance(bands, list):
        raise ConfigError(
            f"Scoring version '{version}': missing 'economics_score_bands' list."
        )
    for band in bands:
        for key in ("min_margin", "max_payback", "score"):
            if key not in band:
                raise ConfigError(
                    f"Scoring version '{version}': economics band missing '{key}'."
                )

    if "payback_metric" not in rules:
        raise ConfigError(
            f"Scoring version '{version}': missing 'payback_metric'."
        )
    if rules["payback_metric"] not in ("gross_profit", "net_monthly_profit"):
        raise ConfigError(
            f"Scoring version '{version}': payback_metric must be "
            "'gross_profit' or 'net_monthly_profit'."
        )


def get_scoring_rules(config: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Return the scoring rules for the given version.

    Raises ConfigError if the version is not defined in the config.
    """
    rules = config.get("scoring_rules", {}).get(version)
    if rules is None:
        raise ConfigError(
            f"Scoring version '{version}' is not defined in config. "
            f"Available: {', '.join(config.get('scoring_rules', {}).keys())}."
        )
    return rules


def get_scenario_multipliers(
    config: Dict[str, Any], scenario: str
) -> Dict[str, float]:
    """Return the multipliers for the named scenario."""
    scen = config.get("scenarios", {}).get(scenario)
    if scen is None:
        raise ConfigError(
            f"Scenario '{scenario}' is not defined in config. "
            f"Available: {', '.join(config.get('scenarios', {}).keys())}."
        )
    return dict(scen)


def get_sensitivity_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return the sensitivity analysis configuration."""
    sens = config.get("sensitivity", {})
    return {
        "parameters": list(sens.get("parameters", [])),
        "range_percents": list(sens.get("range_percents", [])),
    }


def compute_config_sha256(config_path: Optional[str] = None) -> str:
    """Return the SHA-256 hex digest of the config file contents."""
    path = _config_path(config_path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_config_sha256_from_dict(config: Dict[str, Any]) -> str:
    """Return a SHA-256 of the canonical JSON serialization of the config.

    Used to embed a config snapshot hash in reports even when the config
    object was loaded from memory.
    """
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
