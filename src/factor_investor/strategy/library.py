"""Registers every strategy: code factories and YAML strategies."""

import factor_investor.strategy.top_n_factor  # noqa: F401
from factor_investor.pipeline.loader import register_yaml_strategies

register_yaml_strategies()
