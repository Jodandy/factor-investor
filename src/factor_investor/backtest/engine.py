"""Generic backtest engine.

The BacktestEngine is completely strategy-agnostic. It only cares about:
1. When to rebalance (from strategy.get_rebalancing_dates())
2. What to hold (from strategy.generate_signals())
3. How prices evolved (from the in-memory price panel)

Everything else (factor selection, ranking, filtering) is delegated to the
Strategy implementation.
"""

import logging
from dataclasses import dataclass
from datetime import date

import polars as pl

from factor_investor import settings
from factor_investor.analytics.metrics import PerformanceMetrics, calculate_performance_metrics
from factor_investor.backtest.portfolio import Portfolio
from factor_investor.backtest.prices import PRICE_FILTER_ID, PricePanel, load_price_panel
from factor_investor.backtest.strategy import Strategy, TargetPortfolio

logger = logging.getLogger(__name__)

# A held instrument without a price for this many calendar days is treated as
# no longer trading and is sold at its last known price.
STALE_PRICE_DAYS = 30


@dataclass
class BacktestResult:
    """Results from a backtest run.

    This is the output of BacktestEngine.run(). It contains all the data
    needed for performance analysis, visualization, and reporting.

    The metrics are calculated automatically during backtest and include
    ~40 comprehensive performance metrics covering returns, risk, recovery,
    and statistical properties.

    Attributes:
        strategy: The strategy that was tested (full object, not just name)
        returns_df: Daily returns [date, portfolio_return]
        holdings_history: Holdings over time [date, instrument_id, weight, value]
        trades: All trades executed [date, instrument_id, action, shares, price, cost]
        metrics: Comprehensive performance metrics (calculated automatically)
        metadata: Additional metadata about the backtest
    """

    strategy: Strategy  # Store full strategy object, not just name
    returns_df: pl.DataFrame  # [date, portfolio_return]
    holdings_history: pl.DataFrame  # [date, instrument_id, weight, value]
    trades: pl.DataFrame  # [date, instrument_id, action, shares, price, cost]
    metrics: PerformanceMetrics  # Calculated automatically
    metadata: dict

    @property
    def strategy_name(self) -> str:
        """Get strategy name (for backward compatibility)."""
        return self.strategy.name

    def print_report(self, benchmark_metrics: PerformanceMetrics | None = None) -> None:
        """Print comprehensive performance report to console.

        Args:
            benchmark_metrics: Optional benchmark metrics for comparison

        Example:
            >>> result = engine.run(strategy, from_date, to_date)
            >>> result.print_report()
        """
        from factor_investor.analytics.reports import print_performance_report

        print_performance_report(self.strategy_name, self.metrics, benchmark_metrics)

    def save_report(self, output_file: str = "latest_backtest_result.txt") -> None:
        """Save complete backtest report to file.

        Includes strategy config, all metrics, and ALL trades.
        File is overwritten each time (for experimentation).

        Args:
            output_file: Path to save report (default: latest_backtest_result.txt)

        Example:
            >>> result = engine.run(strategy, from_date, to_date)
            >>> result.save_report()
            📄 Report saved to: latest_backtest_result.txt
            >>> result.save_report("my_strategy_v2.txt")
            📄 Report saved to: my_strategy_v2.txt
        """
        from factor_investor.analytics.reports import save_backtest_report

        save_backtest_report(self, output_file)


class BacktestEngine:
    """Generic backtest simulation engine.

    The engine is strategy-agnostic and handles:
    - Date iteration
    - Price loading
    - Portfolio rebalancing
    - Daily return calculation
    - Trade recording

    It does NOT:
    - Select factors (Strategy does this)
    - Rank instruments (Strategy does this)
    - Define rebalancing schedule (Strategy does this)
    - Calculate performance metrics (Analytics module does this)

    Example:
        >>> from factor_investor.backtest.strategy import LongOnlyFactorStrategy
        >>> from factor_investor.backtest.engine import BacktestEngine
        >>>
        >>> # Define strategy
        >>> strategy = LongOnlyFactorStrategy(
        ...     name="ROIC Quality",
        ...     factors={"roic_mean_5y_pct": 1.0},
        ...     num_positions=30,
        ... )
        >>>
        >>> # Run backtest
        >>> engine = BacktestEngine()
        >>> result = engine.run(
        ...     strategy=strategy,
        ...     from_date=date(2018, 1, 1),
        ...     to_date=date(2024, 12, 31),
        ... )
        >>>
        >>> # Analyze results
        >>> print(f"Total return: {result.returns_df['portfolio_return'].sum():.1%}")
        >>> print(f"Trades: {len(result.trades)}")
    """

    def __init__(
        self, execution_delay_days: int | None = None, prices: PricePanel | None = None
    ) -> None:
        """Initialize engine.

        Args:
            execution_delay_days: Trading days between signal and execution.
                Defaults to settings.toml (>= 1). 0 is only for tests that
                verify the delay is applied.
            prices: Price panel; defaults to the total_returns panel, loaded
                on first use.
        """
        if execution_delay_days is None:
            execution_delay_days = settings.execution_delay_days()
        self.execution_delay_days = execution_delay_days
        self._panel = prices

    @property
    def prices(self) -> PricePanel:
        if self._panel is None:
            self._panel = load_price_panel()
        return self._panel

    def run(
        self,
        strategy: Strategy,
        from_date: date,
        to_date: date,
        initial_capital: float = 1_000_000,
    ) -> BacktestResult:
        """Run backtest for a strategy.

        Signals are generated on each rebalancing date and executed
        `execution_delay_days` trading days later, at that day's price.

        Args:
            strategy: Strategy to test
            from_date: Backtest start date
            to_date: Backtest end date
            initial_capital: Starting capital

        Returns:
            BacktestResult with all simulation data
        """
        logger.info(f"Starting backtest: {strategy.name}")
        logger.info(f"  Period: {from_date} to {to_date}")
        logger.info(f"  Initial capital: {initial_capital:,.0f}")

        # Initialize portfolio
        portfolio = Portfolio(initial_capital)

        # Get rebalancing dates from strategy
        rebal_dates = strategy.get_rebalancing_dates(from_date, to_date)
        logger.info(f"  Rebalancing dates: {len(rebal_dates)}")

        if len(rebal_dates) == 0:
            raise ValueError("Strategy returned no rebalancing dates")

        # Get all trading days (for daily returns)
        trading_days = self._get_trading_days(from_date, to_date)
        logger.info(f"  Trading days: {len(trading_days)}")

        # Track holdings and trades for result
        all_holdings = []
        all_trades = []
        daily_returns = []

        # Simulation loop
        next_rebal_idx = 0
        # Signals waiting for their delay: (due_day_idx, signal_date, target)
        pending: list[tuple[int, date, TargetPortfolio]] = []
        # Per-instrument orders from the latest due signal: id -> (weight, signal_date).
        # The trading calendar is the union of all markets, so a given stock may
        # not trade on the due day; its order waits for the stock's own next price.
        open_orders: dict[int, tuple[float, date]] = {}
        last_price_date: dict[int, date] = {}
        previous_value = portfolio.total_value

        for day_idx, current_date in enumerate(trading_days):
            if (day_idx + 1) % 100 == 0:
                logger.debug(f"  Progress: {day_idx + 1}/{len(trading_days)} days")

            # Get prices for today
            prices_today = self._get_prices(current_date)

            if len(prices_today) == 0:
                logger.warning(f"No prices for {current_date}, skipping")
                continue

            portfolio.update_prices(prices_today, current_date)

            # Generate signal on rebalancing date; execution is delayed
            if next_rebal_idx < len(rebal_dates) and current_date >= rebal_dates[next_rebal_idx]:
                rebal_date = rebal_dates[next_rebal_idx]
                next_rebal_idx += 1
                logger.debug(f"  Signal on {rebal_date}")

                target = strategy.generate_signals(rebal_date, portfolio.get_holdings_df())
                logger.debug(f"    Target: {len(target.holdings)} positions")

                # Skip rebalancing if no target holdings (e.g., no factor data)
                if len(target.holdings) == 0:
                    logger.warning("    Skipping rebalance - no target holdings")
                else:
                    pending.append((day_idx + self.execution_delay_days, rebal_date, target))

            # A due signal replaces any unfilled orders from the previous one
            while pending and pending[0][0] <= day_idx:
                _, signal_date, target = pending.pop(0)
                weights = Portfolio.normalize_weights(
                    target.holdings, strategy.max_position_weight
                )
                open_orders = {
                    row["instrument_id"]: (row["weight"], signal_date)
                    for row in weights.iter_rows(named=True)
                }
                for ins_id in portfolio.holdings["instrument_id"].to_list():
                    open_orders.setdefault(ins_id, (0.0, signal_date))

            priced_today = set(prices_today["instrument_id"].to_list())
            for ins_id in portfolio.holdings["instrument_id"].to_list():
                if ins_id in priced_today:
                    last_price_date[ins_id] = current_date

            # Holdings without a price for STALE_PRICE_DAYS have stopped trading
            stale = {
                ins_id
                for ins_id in portfolio.holdings["instrument_id"].to_list()
                if ins_id not in priced_today
                and (current_date - last_price_date.get(ins_id, current_date)).days
                >= STALE_PRICE_DAYS
            }

            # Buy orders that never got a price are dropped
            open_orders = {
                ins_id: order
                for ins_id, order in open_orders.items()
                if ins_id in priced_today
                or ins_id in stale
                or (current_date - order[1]).days < STALE_PRICE_DAYS
            }

            executable = {i: o for i, o in open_orders.items() if i in priced_today}
            for ins_id in stale:
                executable[ins_id] = (0.0, open_orders.get(ins_id, (0.0, None))[1])

            if executable:
                current_holdings_df = portfolio.get_holdings_df()
                trades = portfolio.rebalance(
                    target_weights=pl.DataFrame(
                        {
                            "instrument_id": list(executable.keys()),
                            "weight": [w for w, _ in executable.values()],
                        },
                        schema={"instrument_id": pl.Int32, "weight": pl.Float64},
                    ),
                    prices=prices_today,
                    rebal_date=current_date,
                    transaction_cost_bps=strategy.transaction_cost_bps,
                    max_position_weight=strategy.max_position_weight,
                    partial=True,
                    sell_at_last_price=stale,
                )
                for ins_id in executable:
                    open_orders.pop(ins_id, None)

                for trade in trades:
                    if trade.action == "buy":
                        last_price_date[trade.instrument_id] = current_date
                    all_trades.append({
                        "date": trade.date,
                        "signal_date": executable[trade.instrument_id][1],
                        "instrument_id": trade.instrument_id,
                        "action": trade.action,
                        "shares": trade.shares,
                        "price": trade.price,
                        "cost": trade.cost,
                    })

                if trades:
                    logger.debug(f"    Executed {len(trades)} trades on {current_date}")
                    new_holdings_df = portfolio.get_holdings_df()
                    trades_df = pl.DataFrame(all_trades[-len(trades):])
                    signal_date = executable[trades[0].instrument_id][1] or current_date
                    strategy.on_rebalance(
                        signal_date, current_holdings_df, new_holdings_df, trades_df
                    )

            # Daily return from end-of-day value, so trading costs are included
            current_value = portfolio.total_value
            daily_return = current_value / previous_value - 1 if previous_value > 0 else 0.0
            previous_value = current_value
            daily_returns.append({
                "date": current_date,
                "portfolio_return": daily_return,
            })

            # Record holdings (daily snapshot)
            holdings_df = portfolio.get_holdings_df()
            if len(holdings_df) > 0:
                for row in holdings_df.iter_rows(named=True):
                    all_holdings.append({
                        "date": current_date,
                        "instrument_id": row["instrument_id"],
                        "shares": row["shares"],
                        "price": row["price"],
                        "value": row["value"],
                        "weight": row["weight"],
                    })

        # Create result DataFrames
        returns_df = pl.DataFrame(daily_returns)
        holdings_df = pl.DataFrame(all_holdings) if all_holdings else pl.DataFrame(
            schema={
                "date": pl.Date,
                "instrument_id": pl.Int32,
                "shares": pl.Float64,
                "price": pl.Float64,
                "value": pl.Float64,
                "weight": pl.Float64,
            }
        )
        trades_df = pl.DataFrame(all_trades) if all_trades else pl.DataFrame(
            schema={
                "date": pl.Date,
                "signal_date": pl.Date,
                "instrument_id": pl.Int32,
                "action": pl.Utf8,
                "shares": pl.Float64,
                "price": pl.Float64,
                "cost": pl.Float64,
            }
        )

        logger.info("Backtest complete:")
        logger.info(f"  Days simulated: {len(returns_df)}")
        logger.info(f"  Trades executed: {len(trades_df)}")
        logger.info(f"  Final value: {portfolio.total_value:,.0f}")
        logger.info(f"  Total return: {(portfolio.total_value / initial_capital - 1):.1%}")

        # Calculate comprehensive performance metrics
        logger.info("Calculating performance metrics...")
        metrics = calculate_performance_metrics(
            returns_df=returns_df,
            trades_df=trades_df,
            risk_free_rate=0.02,
            benchmark_returns=None,  # TODO: Add benchmark support
        )

        logger.info("Performance metrics calculated:")
        logger.info(f"  CAGR: {metrics.cagr:.1%}")
        logger.info(f"  Sharpe ratio: {metrics.sharpe_ratio:.2f}")
        logger.info(f"  Max drawdown: {metrics.max_drawdown:.1%}")
        logger.info(f"  Calmar ratio: {metrics.calmar_ratio:.2f}")

        return BacktestResult(
            strategy=strategy,  # Store full strategy object
            returns_df=returns_df,
            holdings_history=holdings_df,
            trades=trades_df,
            metrics=metrics,
            metadata={
                "initial_capital": initial_capital,
                "final_value": portfolio.total_value,
                "from_date": from_date,
                "to_date": to_date,
                "num_rebalances": len(rebal_dates),
                "price_filter": PRICE_FILTER_ID,
            },
        )

    def _get_trading_days(self, from_date: date, to_date: date) -> list[date]:
        """All days with price data for any instrument, from_date..to_date."""
        return self.prices.trading_days_between(from_date, to_date)

    def _get_prices(self, as_of_date: date) -> pl.DataFrame:
        """[instrument_id, price] on as_of_date.

        The price is the total return index (dividends reinvested), so
        holding value includes dividends.
        """
        return self.prices.prices_on(as_of_date)
