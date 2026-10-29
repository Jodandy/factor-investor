"""Integrity tests for the backtest engine.

Runs the engine on synthetic in-memory prices (no database needed) to verify
execution delay and portfolio accounting.
"""

import polars as pl
import pytest

from factor_investor.backtest.engine import STALE_PRICE_DAYS, BacktestEngine
from tests.integrity.synthetic import (
    InMemoryEngine,
    ScheduledStrategy,
    equal_weight,
    random_walk_prices,
    run,
    trading_days,
)


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


def oracle_schedule(prices, days, every: int, top: int) -> dict:
    """Cheats: on each signal day, picks the names with the best return from the
    execution day (T+1) to the next execution day. Only possible with future prices."""
    schedule = {}
    for j in range(0, len(days) - 1, every):
        buy, sell = days[j + 1], days[min(j + 1 + every, len(days) - 1)]
        ranked = sorted(prices[buy], key=lambda i: prices[sell][i] / prices[buy][i], reverse=True)
        schedule[days[j]] = equal_weight(ranked[:top])
    return schedule


@pytest.mark.integrity
class TestSanity:
    def test_oracle_gets_absurd_returns(self) -> None:
        """An engine that cannot profit from perfect foresight is broken (WORK_ORDER fas 6)."""
        days = trading_days(241)
        prices = random_walk_prices(40, len(days), seed=1)
        oracle = oracle_schedule(prices, days, every=10, top=5)
        all_names = {d: equal_weight(list(range(40))) for d in oracle}

        cheat = run(InMemoryEngine(prices), ScheduledStrategy(oracle), days)
        market = run(InMemoryEngine(prices), ScheduledStrategy(all_names), days)

        # About 10x here; the same picks one period late give an ordinary result
        assert cheat.metadata["final_value"] > 3 * market.metadata["final_value"]

    def test_no_trades_keeps_exact_cash(self) -> None:
        """Empty targets: no trades, every daily return exactly zero (cash earns nothing)."""
        days = trading_days(30)
        prices = random_walk_prices(5, len(days), seed=2)
        strategy = ScheduledStrategy({days[0]: {}, days[10]: {}, days[20]: {}})

        result = run(InMemoryEngine(prices), strategy, days)

        assert result.trades.is_empty()
        assert (result.returns_df["portfolio_return"] == 0).all()
        assert result.metadata["final_value"] == 1_000_000

    def test_buy_and_hold_value_with_costs_is_exact(self) -> None:
        """Buy at T+1 for all cash including 10 bps, hold: value = cash / (1 + cost) * gain."""
        days = trading_days(10)
        prices = {d: {1: 100.0 if t < 5 else 150.0} for t, d in enumerate(days)}
        strategy = ScheduledStrategy({days[0]: {1: 1.0}}, cost_bps=10)

        result = run(InMemoryEngine(prices), strategy, days)

        assert result.metadata["final_value"] == pytest.approx(1_000_000 / 1.001 * 1.5, rel=1e-12)
        assert result.trades["cost"].sum() == pytest.approx(1_000_000 / 1.001 * 0.001, rel=1e-12)

    def test_equal_weight_universe_matches_closed_form_every_day(self) -> None:
        """Benchmark replication (WORK_ORDER fas 6): without costs, an equal-weighted
        universe rebalanced at T+1 is worth V(last execution) times the mean price
        relative of all names since then, on every day."""
        n, every = 20, 10
        days = trading_days(61)
        prices = random_walk_prices(n, len(days), seed=4)
        signals = days[:-1:every]
        schedule = {d: equal_weight(list(range(n))) for d in signals}

        result = run(InMemoryEngine(prices), ScheduledStrategy(schedule, cost_bps=0), days)

        executions = {days[days.index(d) + 1] for d in signals}
        expected, value, base = [], 1_000_000.0, None
        for d in days:
            if base is not None:
                value_today = value * sum(prices[d][i] / prices[base][i] for i in range(n)) / n
            else:
                value_today = value
            if d in executions:
                value, base = value_today, d
            expected.append(value_today)

        actual = 1_000_000 * (1 + result.returns_df["portfolio_return"]).cum_prod()
        assert actual.to_list() == pytest.approx(expected, rel=1e-9)
