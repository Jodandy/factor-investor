"""resize_holdings false: kept holdings keep their weight, new buys share the free cash."""

import polars as pl
import pytest

from factor_investor.pipeline.strategy import let_winners_run


def frame(weights: dict[int, float]) -> pl.DataFrame:
    return pl.DataFrame(
        {"instrument_id": list(weights), "weight": list(weights.values())},
        schema={"instrument_id": pl.Int32, "weight": pl.Float64},
    )


def test_kept_names_are_untouched_and_new_buys_get_their_slot() -> None:
    selection = frame({1: 0.05, 2: 0.05, 3: 0.05})
    holdings = frame({1: 0.30, 2: 0.10, 9: 0.05})  # 9 is sold; cash 0.55
    target = let_winners_run(selection, holdings)
    assert target.keep == frozenset({1, 2})
    assert not target.normalize
    assert dict(target.holdings.rows()) == {1: 0.30, 2: 0.10, 3: 0.05}


def test_new_buys_share_the_free_cash_when_winners_have_grown() -> None:
    # winners take 90%: two new names share the 10% left (sold name 9 included)
    selection = frame({1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5})
    holdings = frame({1: 0.60, 2: 0.30, 9: 0.06})
    target = let_winners_run(selection, holdings)
    weights = dict(target.holdings.rows())
    assert weights[3] == pytest.approx(0.05) and weights[4] == pytest.approx(0.05)


def test_without_holdings_it_is_the_plain_target() -> None:
    selection = frame({1: 0.05, 2: 0.05})
    target = let_winners_run(selection, frame({}))
    assert target.keep == frozenset()
    assert dict(target.holdings.rows()) == {1: 0.05, 2: 0.05}
