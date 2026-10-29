"""YAML strategies in config/strategies/ registered as trial strategies.

The file name must equal the strategy id. A trial's parameters are one choice
per searched field (`pipeline.config.resolve`). The source hash covers the
YAML file and every component module it references, so editing either after
a logged run is refused (make `_v2`).
"""

from pathlib import Path
from typing import Any

import yaml

from factor_investor.components.base import get_component
from factor_investor.pipeline.config import component_ids, resolve
from factor_investor.strategy.registry import STRATEGIES, RegisteredStrategy, add_strategy

STRATEGY_DIR = Path("config/strategies")


def load_raw(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or raw.get("id") != path.stem:
        raise ValueError(f"{path}: id must equal the file name ({path.stem})")
    return raw


def yaml_strategy(path: Path) -> RegisteredStrategy:
    raw = load_raw(path)

    def factory(params: dict[str, Any]) -> Any:
        from factor_investor.pipeline.strategy import PipelineStrategy

        return PipelineStrategy(resolve(raw, params))

    modules = sorted({get_component(c).source_file() for c in component_ids(raw)})
    return RegisteredStrategy(
        raw["id"], factory, (path, *modules), hypothesis=raw.get("hypothesis"), area=raw.get("area")
    )


def register_yaml_strategies(directory: Path = STRATEGY_DIR) -> None:
    for path in sorted(directory.glob("*.yaml")):
        if path.stem not in STRATEGIES:
            add_strategy(yaml_strategy(path))
