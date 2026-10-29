"""Synthetic prices and strategies for engine tests (no database)."""

from datetime import date, timedelta

import numpy as np
import polars as pl

from factor_investor.backtest.engine import BacktestEngine, BacktestResult
from factor_investor.backtest.prices import PricePanel
from factor_investor.backtest.strategy import Strategy, TargetPortfolio

START = date(2015, 1, 5)

Prices = dict[date, dict[int, float]]
Schedule = dict[date, dict[int, float]]


def trading_days(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def random_walk_prices(n_instruments: int, n_days: int, seed: int) -> Prices:
    """Daily prices starting at 100, i.i.d. normal returns (mean 0.05%, sd 2%)."""
    rng = np.random.default_rng(seed)
    returns = 1 + rng.normal(0.0005, 0.02, (n_days - 1, n_instruments))
    paths = 100 * np.vstack([np.ones(n_instruments), np.cumprod(returns, axis=0)])
    return {
        d: {i: float(paths[t, i]) for i in range(n_instruments)}
        for t, d in enumerate(trading_days(n_days))
    }


def InMemoryEngine(
    prices: Prices, **kwargs: int
) -> BacktestEngine:
    """Engine on a synthetic price panel instead of the database."""
    rows = [(i, d, p) for d, day in prices.items() for i, p in day.items()]
    frame = pl.DataFrame(rows, schema=["instrument_id", "date", "price"], orient="row")
    return BacktestEngine(prices=PricePanel.from_frame(frame), **kwargs)


class ScheduledStrategy(Strategy):
    """Holds a fixed target per rebalancing date (an empty target means no trade)."""

    def __init__(self, schedule: Schedule, cost_bps: int = 10) -> None:
        self.schedule = schedule
        self.cost_bps = cost_bps
        self.signal_dates: list[date] = []

    @property
    def name(self) -> str:
        return "scheduled"

    @property
    def transaction_cost_bps(self) -> int:
        return self.cost_bps

    @property
    def max_position_weight(self) -> float:
        return 1.0

    def get_rebalancing_dates(self, from_date: date, to_date: date) -> list[date]:
        return sorted(d for d in self.schedule if from_date <= d <= to_date)

    def generate_signals(
        self, as_of_date: date, current_holdings: pl.DataFrame | None = None  # noqa: ARG002
    ) -> TargetPortfolio:
        self.signal_dates.append(as_of_date)
        weights = self.schedule[as_of_date]
        return TargetPortfolio(
            holdings=pl.DataFrame(
                {"instrument_id": list(weights.keys()), "weight": list(weights.values())},
                schema={"instrument_id": pl.Int32, "weight": pl.Float64},
            )
        )


def run(engine: BacktestEngine, strategy: Strategy, days: list[date]) -> BacktestResult:
    return engine.run(strategy, days[0], days[-1], initial_capital=1_000_000)


def equal_weight(ids: list[int]) -> dict[int, float]:
    return {i: 1 / len(ids) for i in ids}
