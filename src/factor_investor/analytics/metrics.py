"""Comprehensive performance metrics calculation.

This module calculates ~50 performance metrics from backtest results.
All metrics are calculated in a single pass for efficiency (~5-10ms).

The metrics are organized into categories:
1. Returns - Total return, CAGR, annualized return
2. Risk - Volatility, drawdown, downside deviation
3. Risk-adjusted - Sharpe, Sortino, Calmar, Omega
4. Recovery - Time underwater, distance to ATH
5. Market-relative - Alpha, beta, tracking error (if benchmark provided)
6. Statistical - Skewness, kurtosis, VaR, CVaR
7. Trading - Turnover, holding periods, win rate
"""

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics.

    This dataclass contains ~50 metrics calculated from a backtest.
    All metrics are strategy-agnostic and work with any BacktestResult.

    Categories:
    - Returns (3 metrics)
    - Risk (5 metrics)
    - Risk-adjusted (7 metrics)
    - Recovery & Peak (7 metrics)
    - Market-relative (5 metrics, optional)
    - Up/Down capture (4 metrics, optional)
    - Trading (4 metrics)
    - Statistical (5 metrics)
    """

    # === RETURNS (3) ===
    total_return: float
    """Total cumulative return over backtest period (decimal)"""

    cagr: float
    """Compound Annual Growth Rate (decimal)"""

    annualized_return: float
    """Annualized arithmetic mean return (decimal)"""

    # === RISK (5) ===
    volatility: float
    """Annualized volatility (standard deviation of returns)"""

    downside_volatility: float
    """Annualized downside volatility (only negative returns)"""

    max_drawdown: float
    """Maximum peak-to-trough decline (decimal, negative)"""

    max_drawdown_start: date
    """Date when maximum drawdown started (peak)"""

    max_drawdown_end: date
    """Date when maximum drawdown ended (trough)"""

    # === RISK-ADJUSTED (7) ===
    sharpe_ratio: float
    """Sharpe ratio (excess return / volatility)"""

    sortino_ratio: float
    """Sortino ratio (excess return / downside volatility)"""

    calmar_ratio: float
    """Calmar ratio (CAGR / max drawdown)"""

    omega_ratio: float
    """Omega ratio (probability weighted gains vs losses)"""

    ulcer_index: float
    """Ulcer index (sqrt of mean squared drawdown)"""

    pain_index: float
    """Pain index (mean absolute drawdown)"""

    recovery_factor: float
    """Recovery factor (total return / max drawdown)"""

    # === RECOVERY & PEAK (7) ===
    current_distance_to_ath: float
    """Current distance to all-time high (decimal, 0 = at ATH)"""

    avg_distance_to_ath: float
    """Average distance to all-time high over backtest"""

    pct_time_at_ath: float
    """Percentage of time at all-time high"""

    pct_time_near_ath: float
    """Percentage of time within 5% of all-time high"""

    max_time_underwater: int
    """Maximum consecutive days below previous peak (days)"""

    avg_recovery_time: float
    """Average time to recover from drawdowns (days)"""

    lake_ratio: float
    """Lake ratio (area under drawdown curve / time)"""

    # === MARKET-RELATIVE (5, optional if benchmark provided) ===
    beta: float | None
    """Beta coefficient vs benchmark (None if no benchmark)"""

    alpha: float | None
    """Annualized alpha vs benchmark (None if no benchmark)"""

    tracking_error: float | None
    """Tracking error vs benchmark (None if no benchmark)"""

    information_ratio: float | None
    """Information ratio (alpha / tracking error, None if no benchmark)"""

    correlation: float | None
    """Correlation with benchmark (None if no benchmark)"""

    # === UP/DOWN CAPTURE (4, optional if benchmark provided) ===
    upside_capture: float | None
    """Upside capture ratio (None if no benchmark)"""

    downside_capture: float | None
    """Downside capture ratio (None if no benchmark)"""

    up_down_ratio: float | None
    """Ratio of upside to downside capture (None if no benchmark)"""

    batting_average: float | None
    """Percentage of periods outperforming benchmark (None if no benchmark)"""

    # === TRADING (4) ===
    annual_turnover: float
    """Average annual portfolio turnover (as decimal)"""

    avg_holding_period_months: float
    """Average holding period for positions (months)"""

    num_trades: int
    """Total number of trades executed"""

    win_rate: float
    """Percentage of profitable trades"""

    # === STATISTICAL (5) ===
    skewness: float
    """Skewness of returns distribution"""

    kurtosis: float
    """Excess kurtosis of returns distribution"""

    var_95: float
    """Value at Risk at 95% confidence (5th percentile)"""

    cvar_95: float
    """Conditional VaR (expected shortfall at 95%)"""

    tail_ratio: float
    """Ratio of 95th to 5th percentile returns"""


def _annualization(dates: list) -> tuple[float, float]:
    """Years covered and return rows per year, from the actual date span.

    The backtest calendar is the union of all markets, so rows per year vary
    (~252 to ~365). Assuming 252 overstated the period length and understated
    CAGR. Zero-return rows on non-trading days dilute daily variance by the
    same factor they increase periods_per_year, so annualized volatility is
    consistent.

    Returns:
        (n_years, periods_per_year)
    """
    n_years = (dates[-1] - dates[0]).days / 365.25 if len(dates) > 1 else 0.0
    if n_years <= 0:
        return (len(dates) / 252, 252.0)
    return (n_years, (len(dates) - 1) / n_years)


def calculate_performance_metrics(
    returns_df: pl.DataFrame,
    trades_df: pl.DataFrame | None = None,
    risk_free_rate: float = 0.02,
    benchmark_returns: pl.DataFrame | None = None,
) -> PerformanceMetrics:
    """Calculate all performance metrics from backtest results.

    This function calculates ~50 metrics in a single pass for efficiency.
    Total computation time: ~5-10ms.

    Args:
        returns_df: DataFrame with [date, portfolio_return]
        trades_df: Optional DataFrame with [date, instrument_id, action, shares, price, cost]
        risk_free_rate: Annual risk-free rate (default: 2%)
        benchmark_returns: Optional DataFrame with [date, benchmark_return]

    Returns:
        PerformanceMetrics with all ~50 metrics populated

    Example:
        >>> metrics = calculate_performance_metrics(
        ...     returns_df=result.returns_df,
        ...     trades_df=result.trades,
        ...     risk_free_rate=0.02,
        ... )
        >>> print(f"CAGR: {metrics.cagr:.1%}")
        >>> print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
    """
    if len(returns_df) == 0:
        logger.warning("Empty returns DataFrame, returning zero metrics")
        return _create_zero_metrics()

    # Extract returns and dates
    returns = returns_df["portfolio_return"].to_numpy()
    dates = returns_df["date"].to_list()
    n_days = len(returns)
    n_years, periods_per_year = _annualization(dates)

    # === CUMULATIVE CALCULATIONS (used by multiple metrics) ===
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max

    # === RETURNS ===
    total_return = cumulative[-1] - 1
    cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    annualized_return = float(np.mean(returns) * periods_per_year)

    # === RISK ===
    volatility = float(np.std(returns, ddof=1) * np.sqrt(periods_per_year))

    downside_returns = returns[returns < 0]
    downside_vol = (
        float(np.std(downside_returns, ddof=1) * np.sqrt(periods_per_year))
        if len(downside_returns) > 0
        else volatility
    )

    max_dd = float(np.min(drawdown))
    max_dd_idx = int(np.argmin(drawdown))
    max_dd_start_idx = int(np.argmax(running_max[:max_dd_idx])) if max_dd_idx > 0 else 0
    max_dd_start = dates[max_dd_start_idx]
    max_dd_end = dates[max_dd_idx]

    # === RISK-ADJUSTED ===
    excess_return = cagr - risk_free_rate
    sharpe_ratio = excess_return / volatility if volatility > 0 else 0.0
    sortino_ratio = excess_return / downside_vol if downside_vol > 0 else 0.0
    calmar_ratio = cagr / abs(max_dd) if max_dd != 0 else 0.0

    # Omega ratio (probability weighted gains vs losses)
    omega_ratio = _calculate_omega_ratio(returns, risk_free_rate / periods_per_year)

    # Ulcer index (RMS of drawdown)
    ulcer_index = float(np.sqrt(np.mean(drawdown**2)))

    # Pain index (mean absolute drawdown)
    pain_index = float(np.mean(np.abs(drawdown)))

    # Recovery factor
    recovery_factor = total_return / abs(max_dd) if max_dd != 0 else 0.0

    # === RECOVERY & PEAK ===
    distance_to_ath = drawdown
    current_distance_to_ath = float(distance_to_ath[-1])
    avg_distance_to_ath = float(np.mean(distance_to_ath))

    # Time at/near ATH
    at_ath = np.sum(distance_to_ath >= -0.001)  # Within 0.1%
    near_ath = np.sum(distance_to_ath >= -0.05)  # Within 5%
    pct_time_at_ath = float(at_ath / n_days)
    pct_time_near_ath = float(near_ath / n_days)

    # Underwater periods
    underwater_periods = _calculate_underwater_periods(cumulative, running_max)
    max_time_underwater = max(underwater_periods) if underwater_periods else 0
    avg_recovery_time = float(np.mean(underwater_periods)) if underwater_periods else 0.0

    # Lake ratio (area under drawdown curve)
    lake_ratio = float(np.sum(np.abs(drawdown)) / n_days)

    # === MARKET-RELATIVE (if benchmark provided) ===
    beta = None
    alpha = None
    tracking_error = None
    information_ratio = None
    correlation = None
    upside_capture = None
    downside_capture = None
    up_down_ratio = None
    batting_average = None

    if benchmark_returns is not None and len(benchmark_returns) > 0:
        benchmark_metrics = _calculate_benchmark_metrics(
            returns_df, benchmark_returns, risk_free_rate, periods_per_year
        )
        beta = benchmark_metrics["beta"]
        alpha = benchmark_metrics["alpha"]
        tracking_error = benchmark_metrics["tracking_error"]
        information_ratio = benchmark_metrics["information_ratio"]
        correlation = benchmark_metrics["correlation"]
        upside_capture = benchmark_metrics["upside_capture"]
        downside_capture = benchmark_metrics["downside_capture"]
        up_down_ratio = benchmark_metrics["up_down_ratio"]
        batting_average = benchmark_metrics["batting_average"]

    # === TRADING ===
    if trades_df is not None and len(trades_df) > 0:
        trading_metrics = _calculate_trading_metrics(trades_df, n_years)
        annual_turnover = trading_metrics["annual_turnover"]
        avg_holding_period_months = trading_metrics["avg_holding_period_months"]
        num_trades = trading_metrics["num_trades"]
        win_rate = trading_metrics["win_rate"]
    else:
        annual_turnover = 0.0
        avg_holding_period_months = 0.0
        num_trades = 0
        win_rate = 0.0

    # === STATISTICAL ===
    skewness = float(stats.skew(returns))
    kurtosis = float(stats.kurtosis(returns))  # Excess kurtosis
    var_95 = float(np.percentile(returns, 5))
    cvar_95 = float(np.mean(returns[returns <= var_95])) if len(returns[returns <= var_95]) > 0 else var_95
    tail_ratio = abs(float(np.percentile(returns, 95) / np.percentile(returns, 5))) if np.percentile(returns, 5) != 0 else 0.0

    return PerformanceMetrics(
        # Returns
        total_return=total_return,
        cagr=cagr,
        annualized_return=annualized_return,
        # Risk
        volatility=volatility,
        downside_volatility=downside_vol,
        max_drawdown=max_dd,
        max_drawdown_start=max_dd_start,
        max_drawdown_end=max_dd_end,
        # Risk-adjusted
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        omega_ratio=omega_ratio,
        ulcer_index=ulcer_index,
        pain_index=pain_index,
        recovery_factor=recovery_factor,
        # Recovery & Peak
        current_distance_to_ath=current_distance_to_ath,
        avg_distance_to_ath=avg_distance_to_ath,
        pct_time_at_ath=pct_time_at_ath,
        pct_time_near_ath=pct_time_near_ath,
        max_time_underwater=max_time_underwater,
        avg_recovery_time=avg_recovery_time,
        lake_ratio=lake_ratio,
        # Market-relative
        beta=beta,
        alpha=alpha,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
        correlation=correlation,
        # Up/Down capture
        upside_capture=upside_capture,
        downside_capture=downside_capture,
        up_down_ratio=up_down_ratio,
        batting_average=batting_average,
        # Trading
        annual_turnover=annual_turnover,
        avg_holding_period_months=avg_holding_period_months,
        num_trades=num_trades,
        win_rate=win_rate,
        # Statistical
        skewness=skewness,
        kurtosis=kurtosis,
        var_95=var_95,
        cvar_95=cvar_95,
        tail_ratio=tail_ratio,
    )


def _calculate_omega_ratio(returns: np.ndarray, threshold: float) -> float:
    """Calculate Omega ratio.

    Omega = Sum(returns > threshold) / Sum(threshold - returns for returns < threshold)

    Args:
        returns: Daily returns array
        threshold: Threshold return (typically risk-free rate / periods per year)

    Returns:
        Omega ratio
    """
    gains = returns[returns > threshold] - threshold
    losses = threshold - returns[returns < threshold]

    if len(losses) == 0 or np.sum(losses) == 0:
        return float("inf") if len(gains) > 0 else 0.0

    omega = np.sum(gains) / np.sum(losses)
    return float(omega)


def _calculate_underwater_periods(cumulative: np.ndarray, running_max: np.ndarray) -> list[int]:
    """Calculate all underwater periods (consecutive days below previous peak).

    Args:
        cumulative: Cumulative returns array
        running_max: Running maximum array

    Returns:
        List of underwater period lengths (in days)
    """
    underwater_periods = []
    current_period = 0

    for i in range(len(cumulative)):
        if cumulative[i] < running_max[i] * 0.999:  # Allow for tiny floating point errors
            current_period += 1
        else:
            if current_period > 0:
                underwater_periods.append(current_period)
                current_period = 0

    # Add final period if still underwater
    if current_period > 0:
        underwater_periods.append(current_period)

    return underwater_periods


def _calculate_benchmark_metrics(
    returns_df: pl.DataFrame,
    benchmark_returns: pl.DataFrame,
    risk_free_rate: float,
    periods_per_year: float,
) -> dict:
    """Calculate metrics relative to benchmark.

    Args:
        returns_df: Portfolio returns [date, portfolio_return]
        benchmark_returns: Benchmark returns [date, benchmark_return]
        risk_free_rate: Annual risk-free rate
        periods_per_year: Return rows per year (see _annualization)

    Returns:
        Dict with beta, alpha, tracking_error, etc.
    """
    # Join returns with benchmark
    joined = returns_df.join(benchmark_returns, on="date", how="inner")

    if len(joined) == 0:
        logger.warning("No overlapping dates with benchmark")
        return {
            "beta": None,
            "alpha": None,
            "tracking_error": None,
            "information_ratio": None,
            "correlation": None,
            "upside_capture": None,
            "downside_capture": None,
            "up_down_ratio": None,
            "batting_average": None,
        }

    port_returns = joined["portfolio_return"].to_numpy()
    bench_returns = joined["benchmark_return"].to_numpy()

    # Beta and Alpha
    covariance = np.cov(port_returns, bench_returns)[0, 1]
    bench_variance = np.var(bench_returns, ddof=1)
    beta = covariance / bench_variance if bench_variance > 0 else None

    # Annualized alpha
    port_cagr = (np.prod(1 + port_returns)) ** (periods_per_year / len(port_returns)) - 1
    bench_cagr = (np.prod(1 + bench_returns)) ** (periods_per_year / len(bench_returns)) - 1
    alpha = port_cagr - (risk_free_rate + beta * (bench_cagr - risk_free_rate)) if beta is not None else None

    # Tracking error
    active_returns = port_returns - bench_returns
    tracking_error = float(np.std(active_returns, ddof=1) * np.sqrt(periods_per_year))

    # Information ratio
    information_ratio = (
        float(np.mean(active_returns) * periods_per_year / tracking_error)
        if tracking_error > 0
        else None
    )

    # Correlation
    correlation = float(np.corrcoef(port_returns, bench_returns)[0, 1])

    # Upside/Downside capture
    up_days = bench_returns > 0
    down_days = bench_returns < 0

    if np.sum(up_days) > 0:
        port_up_return = np.mean(port_returns[up_days])
        bench_up_return = np.mean(bench_returns[up_days])
        upside_capture = (
            float(port_up_return / bench_up_return) if bench_up_return != 0 else None
        )
    else:
        upside_capture = None

    if np.sum(down_days) > 0:
        port_down_return = np.mean(port_returns[down_days])
        bench_down_return = np.mean(bench_returns[down_days])
        downside_capture = (
            float(port_down_return / bench_down_return) if bench_down_return != 0 else None
        )
    else:
        downside_capture = None

    up_down_ratio = (
        upside_capture / downside_capture
        if upside_capture is not None and downside_capture is not None and downside_capture != 0
        else None
    )

    # Batting average (% of periods outperforming)
    outperform = np.sum(port_returns > bench_returns)
    batting_average = float(outperform / len(port_returns))

    return {
        "beta": beta,
        "alpha": alpha,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "correlation": correlation,
        "upside_capture": upside_capture,
        "downside_capture": downside_capture,
        "up_down_ratio": up_down_ratio,
        "batting_average": batting_average,
    }


def _calculate_trading_metrics(trades_df: pl.DataFrame, n_years: float) -> dict:
    """Calculate trading-related metrics.

    Args:
        trades_df: Trades DataFrame [date, instrument_id, action, shares, price, cost]
        n_years: Backtest duration in years

    Returns:
        Dict with annual_turnover, avg_holding_period_months, num_trades, win_rate
    """
    num_trades = len(trades_df)

    # Annual turnover (sum of all trade values / portfolio value / years)
    # Approximate with total value traded
    total_value_traded = (trades_df["shares"] * trades_df["price"]).sum()
    annual_turnover = float(total_value_traded / n_years) if n_years > 0 else 0.0

    # Average holding period - match buys with sells
    buys = trades_df.filter(pl.col("action") == "buy")
    sells = trades_df.filter(pl.col("action") == "sell")

    holding_periods = []
    for ins_id in trades_df["instrument_id"].unique():
        ins_buys = buys.filter(pl.col("instrument_id") == ins_id).sort("date")
        ins_sells = sells.filter(pl.col("instrument_id") == ins_id).sort("date")

        # FIFO matching
        for i in range(min(len(ins_buys), len(ins_sells))):
            buy_date = ins_buys[i]["date"][0]
            sell_date = ins_sells[i]["date"][0]
            days = (sell_date - buy_date).days
            holding_periods.append(days)

    avg_holding_period_months = (
        float(np.mean(holding_periods) / 30) if holding_periods else 0.0
    )

    # Win rate (% of profitable round trips)
    profitable_trades = 0
    total_round_trips = 0

    for ins_id in trades_df["instrument_id"].unique():
        ins_buys = buys.filter(pl.col("instrument_id") == ins_id).sort("date")
        ins_sells = sells.filter(pl.col("instrument_id") == ins_id).sort("date")

        for i in range(min(len(ins_buys), len(ins_sells))):
            buy_price = ins_buys[i]["price"][0]
            sell_price = ins_sells[i]["price"][0]
            if sell_price > buy_price:
                profitable_trades += 1
            total_round_trips += 1

    win_rate = (
        float(profitable_trades / total_round_trips) if total_round_trips > 0 else 0.0
    )

    return {
        "annual_turnover": annual_turnover,
        "avg_holding_period_months": avg_holding_period_months,
        "num_trades": num_trades,
        "win_rate": win_rate,
    }


def _create_zero_metrics() -> PerformanceMetrics:
    """Create PerformanceMetrics with all zeros (for empty results)."""
    from datetime import date

    return PerformanceMetrics(
        total_return=0.0,
        cagr=0.0,
        annualized_return=0.0,
        volatility=0.0,
        downside_volatility=0.0,
        max_drawdown=0.0,
        max_drawdown_start=date.today(),
        max_drawdown_end=date.today(),
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        calmar_ratio=0.0,
        omega_ratio=0.0,
        ulcer_index=0.0,
        pain_index=0.0,
        recovery_factor=0.0,
        current_distance_to_ath=0.0,
        avg_distance_to_ath=0.0,
        pct_time_at_ath=0.0,
        pct_time_near_ath=0.0,
        max_time_underwater=0,
        avg_recovery_time=0.0,
        lake_ratio=0.0,
        beta=None,
        alpha=None,
        tracking_error=None,
        information_ratio=None,
        correlation=None,
        upside_capture=None,
        downside_capture=None,
        up_down_ratio=None,
        batting_average=None,
        annual_turnover=0.0,
        avg_holding_period_months=0.0,
        num_trades=0,
        win_rate=0.0,
        skewness=0.0,
        kurtosis=0.0,
        var_95=0.0,
        cvar_95=0.0,
        tail_ratio=0.0,
    )
