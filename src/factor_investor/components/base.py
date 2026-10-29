"""Component base classes and registry (ARCHITECTURE §3, §4).

A component has a versioned id, a kind and a pydantic `Params` schema that
rejects unknown fields. It sees data only through a point-in-time view (the
`View` protocol), which is bound to one date and takes no date arguments.
"""

import hashlib
import inspect
from abc import ABC, abstractmethod
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Protocol

import polars as pl
from pydantic import BaseModel, ConfigDict

from factor_investor.strategy.registry import VERSIONED_ID


class View(Protocol):
    @property
    def as_of(self) -> date: ...

    def metric(self, name: str) -> pl.DataFrame:
        """[instrument_id, value] on the view's date."""
        ...

    def metric_history(self, name: str, years: int) -> pl.DataFrame:
        """[instrument_id, date, value] for snapshots in the `years` up to the view's date."""
        ...

    def frame(self, instruments: pl.DataFrame, names: frozenset[str]) -> pl.DataFrame:
        """instrument_id plus one column per name (metric or universe field)."""
        ...


class ComponentKind(StrEnum):
    FILTER = "filter"
    SCORE = "score"
    PORTFOLIO = "portfolio"
    SIGNAL = "signal"  # daily clock: timing
    EXIT = "exit"  # daily clock: closing positions


class ComponentParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Component(ABC):
    id: ClassVar[str]
    kind: ClassVar[ComponentKind]
    Params: ClassVar[type[ComponentParams]]

    def __init__(self, params: ComponentParams) -> None:
        self.params = params

    @classmethod
    def source_file(cls) -> Path:
        return Path(inspect.getfile(cls))

    @classmethod
    def source_hash(cls) -> str:
        return hashlib.sha256(cls.source_file().read_bytes()).hexdigest()


class FilterComponent(Component):
    kind = ComponentKind.FILTER

    @abstractmethod
    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        """The instruments (a frame with instrument_id) that pass."""


class ScoreComponent(Component):
    kind = ComponentKind.SCORE

    @abstractmethod
    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        """[instrument_id, score] for every instrument; higher is better, null if unknown."""


class PortfolioComponent(Component):
    kind = ComponentKind.PORTFOLIO

    @abstractmethod
    def run(self, ranked: pl.DataFrame, current: list[int]) -> pl.DataFrame:
        """[instrument_id, weight] from composite scores and current holdings."""


class DailyPriceView(Protocol):
    @property
    def as_of(self) -> date: ...

    def prices(self, instruments: list[int], days: int) -> Any:
        """(days, instruments) array of daily prices ending on as_of, NaN if missing."""
        ...


class SignalComponent(Component):
    kind = ComponentKind.SIGNAL

    @abstractmethod
    def run(self, view: DailyPriceView, instruments: list[int]) -> set[int]:
        """The instruments for which the signal is on, as of the view's date."""


class ExitComponent(Component):
    kind = ComponentKind.EXIT

    @abstractmethod
    def run(self, positions: pl.DataFrame) -> set[int]:
        """Positions to close, from [instrument_id, entry_price, high, price]
        (high = highest daily price since entry, price = today's)."""


COMPONENTS: dict[str, type[Component]] = {}


def register_component[C: type[Component]](cls: C) -> C:
    if not VERSIONED_ID.match(cls.id):
        raise ValueError(f"Component id {cls.id!r} must be lower_snake_case ending in _v<N>")
    if cls.id in COMPONENTS:
        raise ValueError(f"Component id {cls.id!r} is already registered")
    COMPONENTS[cls.id] = cls
    return cls


def get_component(component_id: str) -> type[Component]:
    import factor_investor.components.library  # noqa: F401  (registers the components)

    if component_id not in COMPONENTS:
        raise KeyError(f"Unknown component {component_id!r}; registered: {sorted(COMPONENTS)}")
    return COMPONENTS[component_id]


def build_component(component_id: str, params: dict[str, Any]) -> Component:
    cls = get_component(component_id)
    return cls(cls.Params(**params))


SCORE_SCHEMA = {"instrument_id": pl.Int32, "score": pl.Float64}
WEIGHT_SCHEMA = {"instrument_id": pl.Int32, "weight": pl.Float64}
