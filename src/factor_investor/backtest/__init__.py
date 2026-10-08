"""Backtesting module.

This module provides a generic backtesting framework that works with any
trading strategy. The framework separates:

1. **Strategy logic** (what to trade, when to rebalance)
   - Defined by implementing the Strategy ABC
   - Example: LongOnlyFactorStrategy

2. **Execution simulation** (how to trade, costs, portfolio tracking)
   - Handled by BacktestEngine + Portfolio
   - Generic and strategy-agnostic

3. **Performance analysis** (metrics, visualization, reporting)
   - Handled by analytics module
   - Works with any BacktestResult

Example:
    >>> from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy
    >>> from datetime import date
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
    >>> print(f"Total return: {(result.metadata['final_value'] / result.metadata['initial_capital'] - 1):.1%}")
"""

from factor_investor.backtest.engine import BacktestEngine, BacktestResult
from factor_investor.backtest.portfolio import Portfolio, Trade
from factor_investor.backtest.strategy import (
    LongOnlyFactorStrategy,
    Strategy,
    TargetPortfolio,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "Portfolio",
    "Trade",
    "Strategy",
    "TargetPortfolio",
    "LongOnlyFactorStrategy",
]
