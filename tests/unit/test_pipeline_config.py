"""Strategy YAML: schema, search space and resolution (no database)."""

import pytest

from factor_investor.pipeline.config import (
    StrategyConfig,
    expand_grid,
    resolve,
    search_space,
)

RAW = {
    "id": "test_pipeline_v1",
    "hypothesis": "H2",
    "area": "SE",
    "rebalance": {"search": ["quarterly", "semiannual"]},
    "universe": [{"component": "expression_v1", "params": {"expression": "turnover >= 1e6"}}],
    "scoring": {
        "min_coverage": 0.5,
        "blocks": {
            "search": {
                "equal": [
                    {"component": "percentile_v1", "params": {"metric": "roic"}, "weight": 1},
                    {
                        "component": "percentile_v1",
                        "params": {"metric": "ev_ebit", "higher_is_better": False},
                        "weight": 1,
                    },
                ],
                "value_heavy": [
                    {"component": "percentile_v1", "params": {"metric": "roic"}, "weight": 1},
                    {
                        "component": "percentile_v1",
                        "params": {"metric": "ev_ebit", "higher_is_better": False},
                        "weight": 3,
                    },
                ],
            }
        },
    },
    "portfolio": {
        "component": "top_n_hysteresis_v1",
        "params": {"top_n": {"search": [15, 25]}, "sell_rank": 1.5},
    },
}


def test_search_space_lists_every_searched_field_with_its_labels() -> None:
    assert search_space(RAW) == {
        "rebalance": ["quarterly", "semiannual"],
        "scoring.blocks": ["equal", "value_heavy"],
        "portfolio.params.top_n": [15, 25],
    }


def test_expand_grid_is_the_full_product_in_a_stable_order() -> None:
    grid = expand_grid(RAW)
    assert len(grid) == 8
    assert grid[0] == {
        "rebalance": "quarterly",
        "scoring.blocks": "equal",
        "portfolio.params.top_n": 15,
    }
    assert len({tuple(sorted(g.items())) for g in grid}) == 8


def test_resolve_substitutes_choices_and_validates() -> None:
    config = resolve(
        RAW,
        {"rebalance": "semiannual", "scoring.blocks": "value_heavy", "portfolio.params.top_n": 25},
    )
    assert isinstance(config, StrategyConfig)
    assert config.rebalance == "semiannual"
    assert config.portfolio.params == {"top_n": 25, "sell_rank": 1.5}
    assert [b.weight for b in config.scoring.blocks] == [1, 3]


@pytest.mark.parametrize(
    ("choices", "message"),
    [
        (
            {"rebalance": "monthly", "scoring.blocks": "equal", "portfolio.params.top_n": 15},
            "monthly",
        ),
        ({"rebalance": "quarterly", "scoring.blocks": "equal"}, "missing"),
        (
            {
                "rebalance": "quarterly",
                "scoring.blocks": "equal",
                "portfolio.params.top_n": 15,
                "extra": 1,
            },
            "unknown",
        ),
    ],
)
def test_only_pre_registered_choices_are_accepted(choices: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        resolve(RAW, choices)


def test_schema_rejects_unknown_fields_and_bad_values() -> None:
    choices = {"rebalance": "quarterly", "scoring.blocks": "equal", "portfolio.params.top_n": 15}
    with pytest.raises(ValueError):
        resolve({**RAW, "colour": "blue"}, choices)
    with pytest.raises(ValueError):
        resolve({**RAW, "id": "no_version"}, choices)
    with pytest.raises(ValueError):
        resolve({**RAW, "rebalance": {"search": ["weekly"]}}, {**choices, "rebalance": "weekly"})


def test_component_ids_in_config() -> None:
    from factor_investor.pipeline.config import component_ids

    assert component_ids(RAW) == {"expression_v1", "percentile_v1", "top_n_hysteresis_v1"}
