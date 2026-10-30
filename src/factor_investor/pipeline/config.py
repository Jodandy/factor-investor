"""Strategy configuration (ARCHITECTURE §5) and its pre-registered search space.

A strategy YAML may replace any value with `{search: [...]}` (the options are
the values) or `{search: {label: value, ...}}` (named options, e.g. weight
sets). The search space is fixed by the file: a trial's parameters are one
choice per searched field, keyed by its path ("portfolio.params.top_n",
"universe[0].params.expression"), and only the listed options are accepted.
"""

import itertools
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from factor_investor.components.base import ComponentKind, get_component
from factor_investor.strategy.registry import VERSIONED_ID

SEARCH = "search"
Rebalance = Literal["monthly", "quarterly", "semiannual", "annual"]


class ComponentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str
    params: dict[str, Any] = Field(default_factory=dict)

    def check(self, kind: ComponentKind) -> None:
        cls = get_component(self.component)
        if cls.kind != kind:
            raise ValueError(f"{self.component} is a {cls.kind} component, expected {kind}")
        cls.Params(**self.params)


class ScoreBlock(ComponentSpec):
    weight: float = Field(gt=0)


class Scoring(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    blocks: list[ScoreBlock] = Field(min_length=1)
    # share of the total block weight that must have a score for a name to be ranked
    min_coverage: float = Field(default=1.0, gt=0, le=1)


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    hypothesis: str
    description: str = ""
    area: str
    rebalance: Rebalance
    cost_bps: int = Field(default=10, ge=0)
    universe: list[ComponentSpec] = Field(default_factory=list)
    scoring: Scoring
    portfolio: ComponentSpec
    # Daily clock (stages 3-5): new positions only when every timing signal is
    # on (candidates wait on a watchlist until the next rebalancing); exits are
    # checked every day; with sell_on_rank false, holdings are only sold by exits.
    timing: list[ComponentSpec] = Field(default_factory=list)
    exits: list[ComponentSpec] = Field(default_factory=list)
    # signals that must stay on for a position to be held (e.g. not below the cloud)
    exit_signals: list[ComponentSpec] = Field(default_factory=list)
    sell_on_rank: bool = True

    @field_validator("id")
    @classmethod
    def _versioned(cls, value: str) -> str:
        if not VERSIONED_ID.match(value):
            raise ValueError(f"Strategy id {value!r} must be lower_snake_case ending in _v<N>")
        return value

    @field_validator("area")
    @classmethod
    def _known_area(cls, value: str) -> str:
        from factor_investor.benchmarks.run import AREAS

        if value not in AREAS:
            raise ValueError(f"Unknown area {value!r}; choose from {sorted(AREAS)}")
        return value

    @model_validator(mode="after")
    def _components(self) -> "StrategyConfig":
        for spec in self.universe:
            spec.check(ComponentKind.FILTER)
        for block in self.scoring.blocks:
            block.check(ComponentKind.SCORE)
        self.portfolio.check(ComponentKind.PORTFOLIO)
        for spec in self.timing:
            spec.check(ComponentKind.SIGNAL)
        for spec in self.exits:
            spec.check(ComponentKind.EXIT)
        for spec in self.exit_signals:
            spec.check(ComponentKind.SIGNAL)
        return self


def _is_search(node: Any) -> bool:
    return isinstance(node, dict) and set(node) == {SEARCH}


def _options(node: dict[str, Any]) -> dict[Any, Any]:
    options = node[SEARCH]
    if isinstance(options, dict):
        return dict(options)
    if isinstance(options, list) and options:
        if not all(isinstance(o, str | int | float | bool) or o is None for o in options):
            raise ValueError("A search list holds plain values; use {search: {label: value}}")
        return {o: o for o in options}
    raise ValueError(f"Invalid search: {node!r}")


def _walk(node: Any, path: str) -> list[tuple[str, Any]]:
    """(path, node) for every searched field, in document order."""
    if _is_search(node):
        return [(path, node)]
    if isinstance(node, dict):
        return [hit for k, v in node.items() for hit in _walk(v, f"{path}.{k}" if path else k)]
    if isinstance(node, list):
        return [hit for i, v in enumerate(node) for hit in _walk(v, f"{path}[{i}]")]
    return []


def search_space(raw: dict[str, Any]) -> dict[str, list[Any]]:
    return {path: list(_options(node)) for path, node in _walk(raw, "")}


def expand_grid(raw: dict[str, Any]) -> list[dict[str, Any]]:
    space = search_space(raw)
    return [dict(zip(space, combo, strict=True)) for combo in itertools.product(*space.values())]


def _substitute(node: Any, path: str, choices: dict[str, Any]) -> Any:
    if _is_search(node):
        return _options(node)[choices[path]]
    if isinstance(node, dict):
        return {k: _substitute(v, f"{path}.{k}" if path else k, choices) for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute(v, f"{path}[{i}]", choices) for i, v in enumerate(node)]
    return node


def resolve(raw: dict[str, Any], choices: dict[str, Any]) -> StrategyConfig:
    """The configuration for one point of the pre-registered search space."""
    space = search_space(raw)
    missing, unknown = set(space) - set(choices), set(choices) - set(space)
    if missing or unknown:
        raise ValueError(f"Choices: missing {sorted(missing)}, unknown {sorted(unknown)}")
    for path, label in choices.items():
        if label not in space[path]:
            raise ValueError(f"{path}={label!r} is not a pre-registered option {space[path]}")
    return StrategyConfig.model_validate(_substitute(raw, "", choices))


def component_ids(raw: Any) -> set[str]:
    """Every component id in the file, in every search option."""
    if isinstance(raw, dict):
        found = {raw["component"]} if isinstance(raw.get("component"), str) else set()
        return found.union(*(component_ids(v) for v in raw.values()))
    if isinstance(raw, list):
        return set().union(*(component_ids(v) for v in raw))
    return set()
