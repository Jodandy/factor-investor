"""Versioned strategy factories.

A research strategy is registered under a versioned id (`value_ey_v1`) with a
factory that builds it from a dict of parameters. A trial records the id, the
parameters and a hash of the factory's source file, so every logged run can be
rebuilt exactly. A version must not change behaviour once it has been used in
a logged run: the trial registry refuses a known id whose source hash changed
(ARCHITECTURE §4); make `_v2` instead.
"""

import hashlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factor_investor.backtest.strategy import Strategy

VERSIONED_ID = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*_v\d+$")

StrategyFactory = Callable[[dict[str, Any]], Strategy]


@dataclass(frozen=True)
class RegisteredStrategy:
    strategy_id: str
    factory: StrategyFactory
    source_file: Path

    def source_hash(self) -> str:
        return hashlib.sha256(self.source_file.read_bytes()).hexdigest()


STRATEGIES: dict[str, RegisteredStrategy] = {}


def register_strategy(strategy_id: str) -> Callable[[StrategyFactory], StrategyFactory]:
    """Decorator registering a factory under a versioned, unique id."""
    if not VERSIONED_ID.match(strategy_id):
        raise ValueError(f"Strategy id {strategy_id!r} must be lower_snake_case ending in _v<N>")

    def decorate(factory: StrategyFactory) -> StrategyFactory:
        if strategy_id in STRATEGIES:
            raise ValueError(f"Strategy id {strategy_id!r} is already registered")
        source = inspect.getsourcefile(factory)
        if source is None:
            raise ValueError(f"No source file for {strategy_id!r}")
        STRATEGIES[strategy_id] = RegisteredStrategy(strategy_id, factory, Path(source))
        return factory

    return decorate


def get_strategy(strategy_id: str) -> RegisteredStrategy:
    if strategy_id not in STRATEGIES:
        raise KeyError(f"Unknown strategy {strategy_id!r}; registered: {sorted(STRATEGIES)}")
    return STRATEGIES[strategy_id]
