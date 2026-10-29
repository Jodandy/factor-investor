"""The pipeline's daily mode on real data (two years of H2 v1, Sweden).

1. Plumbing: daily mode with an exit that can never trigger reproduces the
   plain strategy exactly.
2. No lookahead: run to T on prices truncated at T, the trades and values
   are identical to the run on full data.
3. Timing is real: a trend filter changes the trades.
"""

from datetime import date
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from factor_investor.backtest.engine import BacktestEngine
from factor_investor.backtest.prices import PANEL_PATH, PricePanel
from factor_investor.pipeline.config import resolve
from factor_investor.pipeline.daily import DailyPrices, daily_prices
from factor_investor.pipeline.loader import load_raw
from factor_investor.pipeline.strategy import PipelineStrategy
from factor_investor.search.registry import _engine_for
from factor_investor.strategy.registry import get_strategy

pytestmark = [pytest.mark.integration, pytest.mark.integrity]

FROM, T = date(2015, 1, 1), date(2016, 6, 30)
H2 = {"rebalance": "quarterly", "scoring.blocks": "equal", "portfolio.params.top_n": 25}


def strategy(daily: DailyPrices | None = None, **extra: Any) -> PipelineStrategy:
    from pathlib import Path

    raw = load_raw(Path("config/strategies/h2_composite_v1.yaml"))
    config = resolve(raw, H2).model_copy(update=extra)
    return PipelineStrategy(config, daily=daily)


def specs(*items: tuple[str, dict[str, Any]]) -> list[Any]:
    from factor_investor.pipeline.config import ComponentSpec

    return [ComponentSpec(component=c, params=p) for c, p in items]


def test_daily_mode_that_never_acts_reproduces_the_plain_strategy() -> None:
    engine = _engine_for("SE")
    plain = engine.run(get_strategy("h2_composite_v1").factory(H2), FROM, T)
    never = strategy(exits=specs(("trailing_stop_v1", {"pct": 0.9999})))
    assert never.uses_daily_clock
    daily = engine.run(never, FROM, T)
    assert daily.metadata["final_value"] == plain.metadata["final_value"]
    assert_frame_equal(daily.trades, plain.trades)


def test_daily_decisions_identical_on_prices_truncated_at_t() -> None:
    """Both runs use Swedish prices only, so both have the same calendar (the
    signal dates of repeated orders depend on the calendar)."""
    timing_and_stop = {
        "timing": specs(("price_above_ma_v1", {"days": 200})),
        "exits": specs(("trailing_stop_v1", {"pct": 0.15})),
    }
    full_daily = daily_prices("SE")
    frame = (
        pl.scan_parquet(PANEL_PATH)
        .filter(
            pl.col("instrument_id").is_in(list(full_daily.index))
            & (pl.col("date") <= date(2026, 12, 31))
        )
        .collect()
    )
    full = BacktestEngine(prices=PricePanel.from_frame(frame)).run(
        strategy(daily=full_daily, **timing_and_stop), FROM, T
    )

    keep = [d for d in full_daily.dates if d <= T]
    truncated_daily = DailyPrices(keep, full_daily.index, full_daily.matrix[: len(keep)])
    truncated_engine = BacktestEngine(
        prices=PricePanel.from_frame(frame.filter(pl.col("date") <= T))
    )
    truncated = truncated_engine.run(strategy(daily=truncated_daily, **timing_and_stop), FROM, T)

    assert len(full.trades) > 50
    assert_frame_equal(full.trades, truncated.trades)
    assert full.metadata["final_value"] == truncated.metadata["final_value"]


def test_timing_changes_the_trades() -> None:
    engine = _engine_for("SE")
    plain = engine.run(get_strategy("h2_composite_v1").factory(H2), FROM, T)
    timed = engine.run(strategy(timing=specs(("price_above_ma_v1", {"days": 200}))), FROM, T)
    assert len(timed.trades) != len(plain.trades) or not timed.trades.equals(plain.trades)
    # some buys happen between rebalancing dates (watchlist names turning on)
    rebalance_days = set(plain.trades["date"].unique().to_list())
    assert set(timed.trades.filter(pl.col("action") == "buy")["date"].to_list()) - rebalance_days
