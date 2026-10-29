"""Benchmark weighting rules (pure functions, no database)."""

from datetime import date

import polars as pl
import pytest

from factor_investor.benchmarks.universe import (
    EUROPE,
    MAX_WEIGHT,
    NORDICS,
    US,
    Region,
    cap_at,
    cap_weights,
    equal_weights,
    random_pick,
    with_base_currency,
)

D = date(2024, 1, 31)


def snapshot(rows: list[tuple[int, float, float, float]]) -> pl.DataFrame:
    """(instrument_id, market_cap_local, price, median_turnover_60d)."""
    return pl.DataFrame(
        rows,
        schema=["instrument_id", "market_cap_local", "price", "median_turnover_60d"],
        orient="row",
    )


def history(rows: list[tuple[int, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows, schema={"instrument_id": pl.Int32, "median_shares": pl.Float64}, orient="row"
    )


def as_dict(weights: pl.DataFrame) -> dict[int, float]:
    return dict(weights.select("instrument_id", "weight").rows())


def test_equal_weights() -> None:
    weights = as_dict(
        equal_weights(snapshot([(1, 1, 1, 1), (2, 1, 1, 1), (3, 1, 1, 1), (4, 1, 1, 1)]))
    )
    assert weights == {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25}


def test_cap_at_redistributes_until_no_weight_exceeds_cap() -> None:
    # 0.5 is capped; redistributing pushes 0.25 over the cap too
    raw = pl.DataFrame({"instrument_id": range(1, 13), "weight": [0.5, 0.25, *[0.025] * 10]})

    weights = as_dict(cap_at(raw, 0.3))

    assert sum(weights.values()) == pytest.approx(1)
    assert max(weights.values()) <= 0.3 + 1e-12
    assert weights[1] == pytest.approx(0.3) and weights[2] == pytest.approx(0.3)
    # Uncapped names keep their relative sizes
    assert weights[3] == pytest.approx(weights[12])


def test_cap_at_leaves_weights_below_cap_unchanged() -> None:
    raw = pl.DataFrame({"instrument_id": [1, 2, 3], "weight": [0.5, 0.3, 0.2]})
    assert as_dict(cap_at(raw, 0.6)) == {1: 0.5, 2: 0.3, 3: 0.2}


def test_cap_weights_proportional_to_market_cap() -> None:
    universe = snapshot([(i, 100.0 + i, 1.0, 1.0) for i in range(1, 21)])

    weights = as_dict(cap_weights(universe, history([])))

    total = sum(100.0 + i for i in range(1, 21))
    assert weights[20] == pytest.approx(120 / total)
    assert max(weights.values()) <= MAX_WEIGHT


def test_cap_weights_drop_turnover_larger_than_market_cap() -> None:
    universe = snapshot(
        [(i, 1000.0, 10.0, 5.0) for i in range(1, 12)] + [(99, 1000.0, 10.0, 2000.0)]
    )
    assert 99 not in as_dict(cap_weights(universe, history([])))


@pytest.mark.parametrize("jump", [11.0, 1 / 11])
def test_cap_weights_drop_share_count_jumps_both_ways(jump: float) -> None:
    # Implied shares now: 1000 / 10 = 100; trailing median 100 / jump
    universe = snapshot([(i, 1000.0, 10.0, 5.0) for i in range(1, 13)])
    trailing = history([(i, 100.0) for i in range(1, 12)] + [(12, 100.0 / jump)])
    assert 12 not in as_dict(cap_weights(universe, trailing))


def test_cap_weights_keep_moderate_share_changes_and_names_without_history() -> None:
    universe = snapshot([(i, 1000.0, 10.0, 5.0) for i in range(1, 13)])
    trailing = history([(i, 100.0) for i in range(1, 11)] + [(11, 100.0 / 9)])  # 12: no history
    weights = as_dict(cap_weights(universe, trailing))
    assert 11 in weights and 12 in weights


def test_random_pick_is_seeded_uniform_and_varies_by_date() -> None:
    universe = snapshot([(i, 1.0, 1.0, 1.0) for i in range(100)])

    first = as_dict(random_pick(universe, 10, seed=7, as_of_date=D))
    again = as_dict(random_pick(universe.reverse(), 10, seed=7, as_of_date=D))
    other_day = as_dict(random_pick(universe, 10, seed=7, as_of_date=date(2024, 2, 29)))
    other_seed = as_dict(random_pick(universe, 10, seed=8, as_of_date=D))

    assert first == again  # independent of row order
    assert len(first) == 10 and set(first.values()) == {0.1}
    assert first != other_day and first != other_seed


def test_random_pick_takes_everything_when_universe_is_small() -> None:
    universe = snapshot([(1, 1.0, 1.0, 1.0), (2, 1.0, 1.0, 1.0)])
    assert as_dict(random_pick(universe, 10, seed=1, as_of_date=D)) == {1: 0.5, 2: 0.5}


def test_cap_weights_compare_market_caps_in_one_currency() -> None:
    """Two companies with the same local market cap, one in EUR and one in SEK:
    the EUR company is worth about 11 times more."""
    universe = with_base_currency(
        snapshot([(1, 100.0, 10.0, 1.0), (2, 100.0, 10.0, 1.0)]).with_columns(
            pl.Series("currency", ["EUR", "SEK"])
        ),
        {"USD": 1.0, "EUR": 0.9, "SEK": 9.9},
        "EUR",
    )
    weights = as_dict(cap_weights(universe, history([])))
    assert weights[1] / weights[2] == pytest.approx(11.0)


def test_names_without_an_exchange_rate_are_dropped() -> None:
    universe = snapshot([(1, 100.0, 10.0, 1.0), (2, 100.0, 10.0, 1.0)]).with_columns(
        pl.Series("currency", ["EUR", "XYZ"])
    )
    converted = with_base_currency(universe, {"EUR": 0.9}, "EUR")
    assert converted["instrument_id"].to_list() == [1]
    assert converted["to_base"].to_list() == [1.0]


def test_regions() -> None:
    assert US.code == "US" and US.currency == "USD"
    assert isinstance(EUROPE, Region) and EUROPE.currency == "EUR"
    codes = {m.code for m in EUROPE.markets}
    assert {m.code for m in NORDICS} <= codes
    assert {"GB", "DE", "FR", "NL", "CH", "ES", "IT", "BE", "PT", "PL"} <= codes
    assert all(m.country_id != US.country_id for m in EUROPE.markets)
