"""Performance analytics module.

This module provides comprehensive performance analysis for backtest results.
It is completely strategy-agnostic - it works with any BacktestResult regardless
of the strategy type (factor-based, technical, ML, etc.).

The analytics module calculates:
- Returns metrics (total return, CAGR, annualized return)
- Risk metrics (volatility, max drawdown, downside deviation)
- Risk-adjusted metrics (Sharpe, Sortino, Calmar, Omega)
- Recovery metrics (time underwater, distance to ATH, recovery time)
- Market-relative metrics (alpha, beta, information ratio)
- Statistical metrics (skewness, kurtosis, VaR, CVaR)
- Position-level metrics (hold volatility, position-level drawdowns)

Example:
    >>> from factor_investor.analytics import calculate_performance_metrics
    >>>
    >>> # After running backtest
    >>> result = engine.run(strategy, from_date, to_date)
    >>>
    >>> # Calculate all metrics (takes ~5-10ms)
    >>> metrics = calculate_performance_metrics(result)
    >>>
    >>> # Access metrics
    >>> print(f"CAGR: {metrics.cagr:.1%}")
    >>> print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
    >>> print(f"Max DD: {metrics.max_drawdown:.1%}")
"""

from factor_investor.analytics.metrics import (
    PerformanceMetrics,
    calculate_performance_metrics,
)
from factor_investor.analytics.reports import (
    generate_performance_report,
    generate_summary_table,
    print_performance_report,
    save_backtest_report,
)

__all__ = [
    "PerformanceMetrics",
    "calculate_performance_metrics",
    "generate_performance_report",
    "print_performance_report",
    "generate_summary_table",
    "save_backtest_report",
]
