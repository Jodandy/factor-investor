"""Registers every strategy: code factories and YAML strategies."""

import factor_investor.strategy.top_n_factor  # noqa: F401
from factor_investor.pipeline.loader import register_yaml_strategies

register_yaml_strategies()


def _register_sleeves() -> None:
    import inspect
    from pathlib import Path

    from factor_investor.ensemble import sleeves
    from factor_investor.strategy.registry import STRATEGIES, RegisteredStrategy, add_strategy

    if "sleeves_v1" not in STRATEGIES:
        add_strategy(
            RegisteredStrategy(
                "sleeves_v1",
                sleeves.SleevesEnsemble,  # type: ignore[arg-type]
                (Path(inspect.getfile(sleeves)),),
            )
        )


_register_sleeves()
