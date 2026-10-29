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
    """A strategy id, its factory and the files that define its behaviour.

    `hypothesis` and `area`, when set, must match a trial's (YAML strategies
    declare both)."""

    strategy_id: str
    factory: StrategyFactory
    source_files: tuple[Path, ...]
    hypothesis: str | None = None
    area: str | None = None

    def source_hash(self) -> str:
        # one file: its own hash (as logged before multi-file strategies existed)
        hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in self.source_files]
        if len(hashes) == 1:
            return hashes[0]
        return hashlib.sha256("".join(hashes).encode()).hexdigest()


STRATEGIES: dict[str, RegisteredStrategy] = {}


def register_strategy(strategy_id: str) -> Callable[[StrategyFactory], StrategyFactory]:
    """Decorator registering a factory under a versioned, unique id."""
    if not VERSIONED_ID.match(strategy_id):
        raise ValueError(f"Strategy id {strategy_id!r} must be lower_snake_case ending in _v<N>")

    def decorate(factory: StrategyFactory) -> StrategyFactory:
        source = inspect.getsourcefile(factory)
        if source is None:
            raise ValueError(f"No source file for {strategy_id!r}")
        add_strategy(RegisteredStrategy(strategy_id, factory, (Path(source),)))
        return factory

    return decorate


def add_strategy(registered: RegisteredStrategy) -> None:
    """Register a strategy built elsewhere (e.g. from a YAML file)."""
    if not VERSIONED_ID.match(registered.strategy_id):
        raise ValueError(
            f"Strategy id {registered.strategy_id!r} must be lower_snake_case ending in _v<N>"
        )
    if registered.strategy_id in STRATEGIES:
        raise ValueError(f"Strategy id {registered.strategy_id!r} is already registered")
    STRATEGIES[registered.strategy_id] = registered


def get_strategy(strategy_id: str) -> RegisteredStrategy:
    import factor_investor.strategy.library  # noqa: F401  (registers the strategies)

    if strategy_id not in STRATEGIES:
        raise KeyError(f"Unknown strategy {strategy_id!r}; registered: {sorted(STRATEGIES)}")
    return STRATEGIES[strategy_id]
