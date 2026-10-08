"""Amazon US product development multi-agent workflow (V3).

This package adds an offline Amazon US product analysis workflow on top
of the existing V1/V2 opportunity analysis tool. All data is sourced
from deterministic mock data or user-provided JSON/CSV inputs; no
network, API keys, or Amazon SP-API calls are made.

The package is organised in execution order:

* :mod:`src.modules.amazon.models`         - dataclasses and Sourced[T]
* :mod:`src.modules.amazon.amazon_config`  - config loading + validation
* :mod:`src.modules.amazon.mock_data`      - deterministic mock fixtures
* :mod:`src.modules.amazon.input_loader`   - user JSON / CSV loaders
* :mod:`src.modules.amazon.profit_agent`   - Amazon profit kernel
* :mod:`src.modules.amazon.keyword_agent`
* :mod:`src.modules.amazon.market_agent`
* :mod:`src.modules.amazon.competitor_agent`
* :mod:`src.modules.amazon.review_agent`
* :mod:`src.modules.amazon.opportunity_agent`
* :mod:`src.modules.amazon.product_agent`
* :mod:`src.modules.amazon.master_agent`
* :mod:`src.modules.amazon.report_agent`
* :mod:`src.modules.amazon.excel_agent`
* :mod:`src.modules.amazon.workflow`       - CLI entry point

V1/V2 modules (``src.modules.csv_import``, ``src.modules.config_loader``,
``src.modules.profit_calculator``, ``src.modules.project_report`` and
friends) are **not** modified by V3.
"""
