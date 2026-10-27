"""Integrity tests for the backtest engine.

Runs the engine on synthetic in-memory prices (no database needed) to verify
execution delay and portfolio accounting.
"""

from datetime import date, timedelta

import polars as pl
import pytest

from factor_investor.backtest.engine import STALE_PRICE_DAYS, BacktestEngine
from factor_investor.backtest.strategy import Strategy, TargetPortfolio

START = date(2015, 1, 5)


def trading_days(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


class InMemoryEngine(BacktestEngine):
    """Engine reading prices from a dict instead of the database."""

    def __init__(self, prices: dict[date, dict[int, float]], **kwargs: int) -> None:
        super().__init__(**kwargs)
        self._prices = prices

    def _get_trading_days(self, from_date: date, to_date: date) -> list[date]:
        return sorted(d for d in self._prices if from_date <= d <= to_date)

    def _get_prices(self, as_of_date: date) -> pl.DataFrame:
        day = self._prices.get(as_of_date, {})
        return pl.DataFrame(
            {"instrument_id": list(day.keys()), "price": list(day.values())},
            schema={"instrument_id": pl.Int32, "price": pl.Float64},
        )


class ScheduledStrategy(Strategy):
    """Holds a fixed target per rebalancing date."""

    def __init__(self, schedule: dict[date, dict[int, float]], cost_bps: int = 10) -> None:
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


def run(engine: BacktestEngine, strategy: Strategy, days: list[date]):
    return engine.run(strategy, days[0], days[-1], initial_capital=1_000_000)


@pytest.mark.integrity
class TestExecutionDelay:
    def test_trades_execute_one_day_after_signal(self) -> None:
        days = trading_days(10)
        prices = {d: {1: 100.0 + 10 * i} for i, d in enumerate(days)}
        strategy = ScheduledStrategy({days[2]: {1: 1.0}})

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        assert strategy.signal_dates == [days[2]]
        buy = result.trades.row(0, named=True)
        assert buy["date"] == days[3]
        assert buy["price"] == prices[days[3]][1]

    def test_moving_execution_to_signal_day_changes_result(self) -> None:
        """Confirms the delay is actually applied (WORK_ORDER fas 6)."""
        days = trading_days(10)
        prices = {d: {1: 100.0 * 1.05**i} for i, d in enumerate(days)}
        schedule = {days[2]: {1: 1.0}}

        delayed = run(InMemoryEngine(prices, execution_delay_days=1), ScheduledStrategy(schedule), days)
        same_day = run(InMemoryEngine(prices, execution_delay_days=0), ScheduledStrategy(schedule), days)

        assert same_day.metadata["final_value"] > delayed.metadata["final_value"]

    def test_buy_waits_for_instruments_next_own_trading_day(self) -> None:
        """Global calendar has days where a given stock does not trade (e.g. a
        weekend when another market is open). The order must wait for the
        stock's next own price, never use the signal-day price."""
        days = trading_days(10)
        prices = {d: {1: 100.0 + 10 * i, 9: 1.0} for i, d in enumerate(days)}
        del prices[days[3]][1]  # instrument 1 closed on the day after the signal
        strategy = ScheduledStrategy({days[2]: {1: 1.0}})

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        buy = result.trades.row(0, named=True)
        assert buy["date"] == days[4]
        assert buy["price"] == prices[days[4]][1]

    def test_sell_waits_for_instruments_next_own_trading_day(self) -> None:
        days = trading_days(10)
        prices = {d: {1: 100.0 + 10 * i, 2: 50.0, 9: 1.0} for i, d in enumerate(days)}
        del prices[days[6]][1]  # instrument 1 closed on the day after the signal
        strategy = ScheduledStrategy({days[1]: {1: 1.0}, days[5]: {2: 1.0}})

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        sell = result.trades.filter(
            (pl.col("instrument_id") == 1) & (pl.col("action") == "sell")
        ).row(0, named=True)
        assert sell["date"] == days[7]
        assert sell["price"] == prices[days[7]][1]

    def test_default_delay_comes_from_settings(self) -> None:
        assert BacktestEngine().execution_delay_days >= 1


@pytest.mark.integrity
class TestAccounting:
    def test_full_exit_removes_position(self) -> None:
        """Selling out of a name must remove it, not just credit cash."""
        days = trading_days(10)
        prices = {d: {1: 100.0, 2: 50.0} for d in days}
        strategy = ScheduledStrategy({days[1]: {1: 1.0}, days[5]: {2: 1.0}}, cost_bps=0)

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        last_day = result.holdings_history.filter(pl.col("date") == days[-1])
        assert last_day["instrument_id"].to_list() == [2]
        # Flat prices and zero costs: value must be unchanged
        assert result.metadata["final_value"] == pytest.approx(1_000_000)

    def test_returns_series_matches_portfolio_value(self) -> None:
        """Compounded daily returns must equal final/initial value, costs included."""
        days = trading_days(20)
        prices = {d: {1: 100.0 * 1.01**i, 2: 80.0 * 0.995**i} for i, d in enumerate(days)}
        strategy = ScheduledStrategy(
            {days[1]: {1: 0.5, 2: 0.5}, days[8]: {2: 1.0}, days[14]: {1: 1.0}}
        )

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        compounded = (1 + result.returns_df["portfolio_return"]).product()
        assert compounded == pytest.approx(result.metadata["final_value"] / 1_000_000)

    def test_position_that_stopped_trading_is_closed_at_last_price(self) -> None:
        """A name with no price for STALE_PRICE_DAYS is sold at its last price."""
        days = trading_days(60)
        prices = {d: {1: 100.0, 2: 50.0} for d in days}
        for d in days[4:]:
            prices[d] = {2: 50.0}  # instrument 1 stops trading
        prices[days[3]][1] = 120.0  # last traded price
        strategy = ScheduledStrategy({days[1]: {1: 1.0}, days[6]: {2: 1.0}}, cost_bps=0)

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        sell = result.trades.filter(
            (pl.col("instrument_id") == 1) & (pl.col("action") == "sell")
        ).row(0, named=True)
        assert sell["price"] == 120.0
        assert (sell["date"] - days[3]).days >= STALE_PRICE_DAYS
        assert result.metadata["final_value"] == pytest.approx(1_200_000)

    def test_buys_never_spend_more_than_available_cash(self) -> None:
        """While a sell is pending, buys are limited to cash (no leverage)."""
        days = trading_days(10)
        prices = {d: {1: 100.0, 2: 50.0, 9: 1.0} for d in days}
        for d in days[5:]:
            del prices[d][1]  # instrument 1 can't be sold for now
        strategy = ScheduledStrategy({days[1]: {1: 1.0}, days[5]: {2: 1.0}}, cost_bps=0)

        result = run(InMemoryEngine(prices, execution_delay_days=1), strategy, days)

        last_day = result.holdings_history.filter(pl.col("date") == days[-1])
        assert last_day["instrument_id"].to_list() == [1]
        assert result.metadata["final_value"] == pytest.approx(1_000_000)
