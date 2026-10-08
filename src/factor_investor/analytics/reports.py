"""Performance report generation.

This module provides functions to generate nicely formatted performance reports
for display in console or saving to files.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from factor_investor.analytics.metrics import PerformanceMetrics

if TYPE_CHECKING:
    from factor_investor.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


def generate_performance_report(
    strategy_name: str,
    metrics: PerformanceMetrics,
    benchmark_metrics: PerformanceMetrics | None = None,
) -> str:
    """Generate a comprehensive performance report.

    Args:
        strategy_name: Name of the strategy
        metrics: Performance metrics for the strategy
        benchmark_metrics: Optional benchmark metrics for comparison

    Returns:
        Formatted report string

    Example:
        >>> report = generate_performance_report(
        ...     "Magic Formula",
        ...     metrics,
        ...     benchmark_metrics
        ... )
        >>> print(report)
    """
    lines = []

    # Header
    lines.append("=" * 80)
    lines.append(f"PERFORMANCE REPORT: {strategy_name}")
    lines.append("=" * 80)

    # Returns
    lines.append("\nRETURNS")
    lines.append("-" * 80)
    lines.append(f"  Total Return:       {metrics.total_return:>12.1%}")
    lines.append(f"  CAGR:               {metrics.cagr:>12.1%}")
    lines.append(f"  Annualized Return:  {metrics.annualized_return:>12.1%}")

    # Risk
    lines.append("\nRISK")
    lines.append("-" * 80)
    lines.append(f"  Volatility:         {metrics.volatility:>12.1%}")
    lines.append(f"  Downside Volatility:{metrics.downside_volatility:>12.1%}")
    lines.append(f"  Maximum Drawdown:   {metrics.max_drawdown:>12.1%}")
    lines.append(f"    Drawdown Period:  {metrics.max_drawdown_start} to {metrics.max_drawdown_end}")

    # Risk-Adjusted
    lines.append("\nRISK-ADJUSTED METRICS")
    lines.append("-" * 80)
    lines.append(f"  Sharpe Ratio:       {metrics.sharpe_ratio:>12.2f}")
    lines.append(f"  Sortino Ratio:      {metrics.sortino_ratio:>12.2f}")
    lines.append(f"  Calmar Ratio:       {metrics.calmar_ratio:>12.2f}")
    lines.append(f"  Omega Ratio:        {metrics.omega_ratio:>12.2f}")
    lines.append(f"  Ulcer Index:        {metrics.ulcer_index:>12.4f}")
    lines.append(f"  Pain Index:         {metrics.pain_index:>12.4f}")
    lines.append(f"  Recovery Factor:    {metrics.recovery_factor:>12.2f}")

    # Recovery & Peak Analysis
    lines.append("\nRECOVERY & PEAK ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"  Current Distance to ATH:  {metrics.current_distance_to_ath:>8.1%}")
    lines.append(f"  Average Distance to ATH:  {metrics.avg_distance_to_ath:>8.1%}")
    lines.append(f"  Time at All-Time High:    {metrics.pct_time_at_ath:>8.1%}")
    lines.append(f"  Time Near ATH (5%):       {metrics.pct_time_near_ath:>8.1%}")
    lines.append(f"  Max Days Underwater:      {metrics.max_time_underwater:>8,.0f} days")
    lines.append(f"  Avg Recovery Time:        {metrics.avg_recovery_time:>8.0f} days")
    lines.append(f"  Lake Ratio:               {metrics.lake_ratio:>8.4f}")

    # Trading Activity
    lines.append("\nTRADING ACTIVITY")
    lines.append("-" * 80)
    lines.append(f"  Number of Trades:         {metrics.num_trades:>8,.0f}")
    lines.append(f"  Annual Turnover:          {metrics.annual_turnover:>8,.0f}")
    lines.append(f"  Avg Holding Period:       {metrics.avg_holding_period_months:>8.1f} months")
    lines.append(f"  Win Rate:                 {metrics.win_rate:>8.1%}")

    # Statistical Properties
    lines.append("\nSTATISTICAL PROPERTIES")
    lines.append("-" * 80)
    lines.append(f"  Skewness:                 {metrics.skewness:>8.2f}")
    lines.append(f"  Kurtosis:                 {metrics.kurtosis:>8.2f}")
    lines.append(f"  Value at Risk (95%):      {metrics.var_95:>8.2%}")
    lines.append(f"  Conditional VaR (95%):    {metrics.cvar_95:>8.2%}")
    lines.append(f"  Tail Ratio:               {metrics.tail_ratio:>8.2f}")

    # Benchmark Comparison (if provided)
    if benchmark_metrics is not None:
        lines.append("\nBENCHMARK COMPARISON")
        lines.append("-" * 80)

        # Returns comparison
        lines.append(f"\n  Returns:")
        lines.append(f"    Strategy CAGR:          {metrics.cagr:>8.1%}")
        lines.append(f"    Benchmark CAGR:         {benchmark_metrics.cagr:>8.1%}")
        outperformance = metrics.cagr - benchmark_metrics.cagr
        lines.append(f"    Outperformance:         {outperformance:>8.1%}")

        # Risk comparison
        lines.append(f"\n  Risk:")
        lines.append(f"    Strategy Volatility:    {metrics.volatility:>8.1%}")
        lines.append(f"    Benchmark Volatility:   {benchmark_metrics.volatility:>8.1%}")
        lines.append(f"    Strategy Max DD:        {metrics.max_drawdown:>8.1%}")
        lines.append(f"    Benchmark Max DD:       {benchmark_metrics.max_drawdown:>8.1%}")

        # Risk-adjusted comparison
        lines.append(f"\n  Risk-Adjusted:")
        lines.append(f"    Strategy Sharpe:        {metrics.sharpe_ratio:>8.2f}")
        lines.append(f"    Benchmark Sharpe:       {benchmark_metrics.sharpe_ratio:>8.2f}")

        # Market-relative metrics
        if metrics.beta is not None:
            lines.append(f"\n  Market-Relative:")
            lines.append(f"    Beta:                   {metrics.beta:>8.2f}")
            lines.append(f"    Alpha:                  {metrics.alpha:>8.1%}")
            lines.append(f"    Tracking Error:         {metrics.tracking_error:>8.1%}")
            lines.append(f"    Information Ratio:      {metrics.information_ratio:>8.2f}")
            lines.append(f"    Correlation:            {metrics.correlation:>8.2f}")

        # Capture ratios
        if metrics.upside_capture is not None:
            lines.append(f"\n  Capture Ratios:")
            lines.append(f"    Upside Capture:         {metrics.upside_capture:>8.1%}")
            lines.append(f"    Downside Capture:       {metrics.downside_capture:>8.1%}")
            lines.append(f"    Up/Down Ratio:          {metrics.up_down_ratio:>8.2f}")
            lines.append(f"    Batting Average:        {metrics.batting_average:>8.1%}")

    lines.append("\n" + "=" * 80)

    return "\n".join(lines)


def print_performance_report(
    strategy_name: str,
    metrics: PerformanceMetrics,
    benchmark_metrics: PerformanceMetrics | None = None,
) -> None:
    """Print performance report to console.

    Args:
        strategy_name: Name of the strategy
        metrics: Performance metrics for the strategy
        benchmark_metrics: Optional benchmark metrics for comparison
    """
    report = generate_performance_report(strategy_name, metrics, benchmark_metrics)
    print(report)


def generate_summary_table(
    strategy_results: dict[str, PerformanceMetrics],
    benchmark_name: str | None = None,
    benchmark_metrics: PerformanceMetrics | None = None,
) -> str:
    """Generate a comparison table for multiple strategies.

    Args:
        strategy_results: Dict mapping strategy name to metrics
        benchmark_name: Optional benchmark name
        benchmark_metrics: Optional benchmark metrics

    Returns:
        Formatted comparison table

    Example:
        >>> results = {
        ...     "Magic Formula": metrics1,
        ...     "Momentum": metrics2,
        ...     "Quality": metrics3,
        ... }
        >>> table = generate_summary_table(results, "Equal Weight", bench_metrics)
        >>> print(table)
    """
    lines = []

    # Header
    lines.append("=" * 120)
    lines.append("STRATEGY COMPARISON")
    lines.append("=" * 120)

    # Column headers
    strategy_names = list(strategy_results.keys())
    if benchmark_metrics is not None:
        strategy_names.append(benchmark_name or "Benchmark")

    header = f"{'Metric':<30}"
    for name in strategy_names:
        header += f"{name:>15}"
    lines.append(header)
    lines.append("-" * 120)

    # Helper function to add rows
    def add_row(metric_name: str, attr: str, fmt: str = ".1%"):
        row = f"{metric_name:<30}"
        for name in strategy_names[:-1] if benchmark_metrics else strategy_names:
            value = getattr(strategy_results[name], attr)
            if value is None:
                row += f"{'N/A':>15}"
            elif fmt == ".1%":
                row += f"{value:>14.1%} "
            elif fmt == ".2f":
                row += f"{value:>14.2f} "
            elif fmt == ",.0f":
                row += f"{value:>14,.0f} "
            else:
                row += f"{value:>15}"

        if benchmark_metrics is not None:
            value = getattr(benchmark_metrics, attr)
            if value is None:
                row += f"{'N/A':>15}"
            elif fmt == ".1%":
                row += f"{value:>14.1%} "
            elif fmt == ".2f":
                row += f"{value:>14.2f} "
            elif fmt == ",.0f":
                row += f"{value:>14,.0f} "
            else:
                row += f"{value:>15}"

        lines.append(row)

    # Returns
    lines.append("\nRETURNS")
    add_row("CAGR", "cagr", ".1%")
    add_row("Total Return", "total_return", ".1%")

    # Risk
    lines.append("\nRISK")
    add_row("Volatility", "volatility", ".1%")
    add_row("Max Drawdown", "max_drawdown", ".1%")

    # Risk-Adjusted
    lines.append("\nRISK-ADJUSTED")
    add_row("Sharpe Ratio", "sharpe_ratio", ".2f")
    add_row("Sortino Ratio", "sortino_ratio", ".2f")
    add_row("Calmar Ratio", "calmar_ratio", ".2f")

    # Recovery
    lines.append("\nRECOVERY")
    add_row("Time at ATH", "pct_time_at_ath", ".1%")
    add_row("Avg Dist to ATH", "avg_distance_to_ath", ".1%")
    add_row("Max Days Underwater", "max_time_underwater", ",.0f")

    # Trading
    lines.append("\nTRADING")
    add_row("Number of Trades", "num_trades", ",.0f")
    add_row("Win Rate", "win_rate", ".1%")

    lines.append("\n" + "=" * 120)

    return "\n".join(lines)


def save_backtest_report(
    result: "BacktestResult",
    output_file: str | Path = "latest_backtest_result.txt",
) -> None:
    """Save complete backtest report to file.

    Includes:
    - Strategy configuration
    - Performance metrics
    - ALL trades (with details)
    - Top/bottom daily returns
    - Holdings summary

    File is overwritten each time (for experimentation phase).

    Args:
        result: BacktestResult from backtest
        output_file: Path to output file (default: latest_backtest_result.txt)

    Example:
        >>> result = engine.run(strategy, from_date, to_date)
        >>> save_backtest_report(result)
        Saved backtest report to: latest_backtest_result.txt
    """
    output_path = Path(output_file)
    logger.info(f"Saving backtest report to: {output_path}")

    lines = []

    # Header
    lines.append("=" * 100)
    lines.append(f"BACKTEST REPORT - {result.strategy.name}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 100)

    # Strategy Configuration
    lines.append("\n" + "=" * 100)
    lines.append("STRATEGY CONFIGURATION")
    lines.append("=" * 100)
    lines.append(f"Name:                {result.strategy.name}")
    if hasattr(result.strategy, "description") and result.strategy.description:
        lines.append(f"Description:         {result.strategy.description}")

    # Factors (if LongOnlyFactorStrategy)
    if hasattr(result.strategy, "factors"):
        lines.append(f"\nFactors:")
        for factor_id, weight in result.strategy.factors.items():
            lines.append(f"  - {factor_id:<40} {weight:>6.1%}")

    # Parameters
    if hasattr(result.strategy, "num_positions"):
        lines.append(f"\nPortfolio Parameters:")
        lines.append(f"  Number of Positions:     {result.strategy.num_positions}")
    if hasattr(result.strategy, "rebalancing_frequency"):
        lines.append(f"  Rebalancing Frequency:   {result.strategy.rebalancing_frequency}")
    if hasattr(result.strategy, "position_sizing"):
        lines.append(f"  Position Sizing:         {result.strategy.position_sizing}")

    # Transaction costs
    if hasattr(result.strategy, "transaction_cost_bps"):
        lines.append(f"\nTransaction Costs:")
        lines.append(f"  Basis Points per Trade:  {result.strategy.transaction_cost_bps}")

    # Risk management
    if hasattr(result.strategy, "max_position_weight"):
        lines.append(f"\nRisk Management:")
        lines.append(f"  Max Position Weight:     {result.strategy.max_position_weight:.1%}")

    # Backtest metadata
    lines.append(f"\nBacktest Period:")
    lines.append(f"  From:                    {result.metadata['from_date']}")
    lines.append(f"  To:                      {result.metadata['to_date']}")
    lines.append(f"  Trading Days:            {len(result.returns_df):,}")
    lines.append(f"  Rebalancing Events:      {result.metadata['num_rebalances']}")

    lines.append(f"\nCapital:")
    lines.append(f"  Initial Capital:         {result.metadata['initial_capital']:>15,.0f} SEK")
    lines.append(f"  Final Value:             {result.metadata['final_value']:>15,.0f} SEK")

    # Performance Report
    lines.append("\n")
    lines.append(
        generate_performance_report(
            result.strategy.name, result.metrics, benchmark_metrics=None
        )
    )

    # Top/Bottom Days
    lines.append("\n" + "=" * 100)
    lines.append("TOP 10 DAILY RETURNS")
    lines.append("=" * 100)

    top_days = result.returns_df.sort("portfolio_return", descending=True).head(10)
    lines.append(f"{'Date':<12} {'Return':>10}")
    lines.append("-" * 25)
    for row in top_days.iter_rows(named=True):
        lines.append(f"{str(row['date']):<12} {row['portfolio_return']:>9.2%}")

    lines.append("\n" + "=" * 100)
    lines.append("BOTTOM 10 DAILY RETURNS")
    lines.append("=" * 100)

    bottom_days = result.returns_df.sort("portfolio_return", descending=False).head(10)
    lines.append(f"{'Date':<12} {'Return':>10}")
    lines.append("-" * 25)
    for row in bottom_days.iter_rows(named=True):
        lines.append(f"{str(row['date']):<12} {row['portfolio_return']:>9.2%}")

    # ALL TRADES
    # Calculate line width later after we know how many factor columns
    trades_section_start = len(lines)
    lines.append("\n" + "=" * 140)  # Placeholder, will be updated
    lines.append(f"ALL TRADES ({len(result.trades)} total)")
    lines.append("=" * 140)  # Placeholder, will be updated

    if len(result.trades) > 0:
        # Filter out trades with None instrument_id
        trades_clean = result.trades.filter(pl.col("instrument_id").is_not_null())

        if len(trades_clean) < len(result.trades):
            logger.warning(
                f"Filtered out {len(result.trades) - len(trades_clean)} trades with None instrument_id"
            )

        if len(trades_clean) > 0:
            # Add value column (shares * price)
            trades_with_value = trades_clean.with_columns(
                (pl.col("shares") * pl.col("price")).alias("value")
            )

            # Get instrument names from database
            from factor_investor.db import get_session
            from sqlalchemy import text

            unique_ids = trades_with_value["instrument_id"].unique().to_list()

            with get_session() as session:
                # Query instruments table directly
                query = text(
                    """
                    SELECT ins_id, name
                    FROM instruments
                    WHERE ins_id = ANY(:ids)
                    """
                )
                result_rows = session.execute(query, {"ids": unique_ids}).fetchall()
                instrument_names = {row[0]: row[1] for row in result_rows}

            # Add name column
            trades_with_names = trades_with_value.with_columns(
                pl.col("instrument_id")
                .map_elements(
                    lambda id: instrument_names.get(id, f"Unknown ({id})"),
                    return_dtype=pl.Utf8,
                )
                .alias("name")
            )

            # Get factor values if strategy uses factors
            factor_columns = {}
            if hasattr(result.strategy, "factors") and result.strategy.factors:
                from factor_investor.factors.queries import get_factor

                # Get unique date-instrument combinations
                unique_dates = trades_with_names["date"].unique().to_list()

                for factor_id in result.strategy.factors.keys():
                    logger.info(f"Loading factor values for trades: {factor_id}")

                    # Get both percentile AND raw values
                    # If factor is percentile normalized (_pct suffix), also get raw version
                    factors_to_load = [factor_id]
                    if factor_id.endswith("_pct"):
                        # Get raw version (remove _pct suffix)
                        raw_factor_id = factor_id[:-4] + "_raw"
                        factors_to_load.append(raw_factor_id)

                    for current_factor_id in factors_to_load:
                        # Collect factor values for all trades
                        factor_values = {}
                        for trade_date in unique_dates:
                            try:
                                # Get factor for all instruments at this date
                                factor_df = get_factor(current_factor_id, trade_date)

                                # Store in dict keyed by (date, instrument_id)
                                for row in factor_df.iter_rows(named=True):
                                    key = (trade_date, row["instrument_id"])
                                    factor_values[key] = row["value"]
                            except Exception as e:
                                logger.warning(f"Could not load {current_factor_id} for {trade_date}: {e}")
                                continue

                        # Add factor column to trades
                        if factor_values:
                            trades_with_names = trades_with_names.with_columns(
                                pl.struct(["date", "instrument_id"])
                                .map_elements(
                                    lambda x: factor_values.get((x["date"], x["instrument_id"])),
                                    return_dtype=pl.Float64,
                                )
                                .alias(current_factor_id)
                            )
                            factor_columns[current_factor_id] = current_factor_id

            # Sort by date, then action (sells before buys)
            trades_sorted = trades_with_names.sort(["date", "action"], descending=[False, True])

            # Build header with factor columns
            header = (
                f"{'Date':<12} {'Action':<6} {'Instr ID':>8} {'Name':<30} "
            )
            # Add factor column headers
            if factor_columns:
                for factor_id in sorted(factor_columns.keys()):
                    # Create readable column name
                    if factor_id.endswith("_raw"):
                        # Raw value: show base metric name
                        base = factor_id.replace("_mean_5y_raw", "").replace("_level_raw", "")
                        factor_display = f"{base}_val"[:12]
                    elif factor_id.endswith("_pct"):
                        # Percentile: show with pct suffix
                        base = factor_id.replace("_mean_5y_pct", "").replace("_level_pct", "")
                        factor_display = f"{base}_pct"[:12]
                    else:
                        # Other: shorten generic name
                        factor_display = factor_id[:12]
                    header += f"{factor_display:>12} "
            # Add remaining columns
            header += f"{'Shares':>10} {'Price':>10} {'Value':>15} {'Cost':>10}"

            line_width = len(header)

            # Update section headers with correct width
            lines[trades_section_start] = "\n" + "=" * line_width
            lines[trades_section_start + 2] = "=" * line_width

            lines.append(header)
            lines.append("-" * line_width)

            for row in trades_sorted.iter_rows(named=True):
                # Truncate name if too long
                name = row["name"][:28] if len(row["name"]) > 28 else row["name"]

                line = (
                    f"{str(row['date']):<12} "
                    f"{row['action']:<6} "
                    f"{row['instrument_id']:>8} "
                    f"{name:<30} "
                )

                # Add factor values (if any) - in same order as header
                if factor_columns:
                    for factor_id in sorted(factor_columns.keys()):
                        factor_val = row.get(factor_id)
                        if factor_val is not None:
                            # Format based on type
                            if factor_id.endswith("_pct"):
                                # Percentile: show as integer (0-100)
                                line += f"{factor_val:>12.0f} "
                            else:
                                # Raw value: show with decimals
                                line += f"{factor_val:>12.1f} "
                        else:
                            line += f"{'N/A':>12} "

                # Add remaining columns
                line += (
                    f"{row['shares']:>10,.0f} "
                    f"{row['price']:>10.2f} "
                    f"{row['value']:>15,.0f} "
                    f"{row['cost']:>10.2f}"
                )

                lines.append(line)

            # Trade summary by action
            lines.append("\n" + "-" * line_width)
            lines.append("TRADE SUMMARY")
            lines.append("-" * line_width)

            buy_trades = trades_sorted.filter(pl.col("action") == "buy")
            sell_trades = trades_sorted.filter(pl.col("action") == "sell")

            lines.append(
                f"Total Buys:   {len(buy_trades):>6,}    Value: {buy_trades['value'].sum():>15,.0f} SEK"
            )
            lines.append(
                f"Total Sells:  {len(sell_trades):>6,}    Value: {sell_trades['value'].sum():>15,.0f} SEK"
            )
            lines.append(
                f"Total Costs:  {' ':>6}     Value: {trades_sorted['cost'].sum():>15,.0f} SEK"
            )
        else:
            lines.append("All trades had invalid instrument_id (filtered out).")

    else:
        lines.append("No trades executed.")

    # Holdings Summary
    lines.append("\n" + "=" * 100)
    lines.append("HOLDINGS SUMMARY")
    lines.append("=" * 100)

    if len(result.holdings_history) > 0:
        # Get latest holdings and filter out None instrument_ids
        latest_date = result.holdings_history["date"].max()
        latest_holdings = (
            result.holdings_history.filter(pl.col("date") == latest_date)
            .filter(pl.col("instrument_id").is_not_null())
            .sort("weight", descending=True)
        )

        if len(latest_holdings) > 0:
            # Get instrument names from database
            from factor_investor.db import get_session
            from sqlalchemy import text

            unique_ids = latest_holdings["instrument_id"].unique().to_list()

            with get_session() as session:
                # Query instruments table directly
                query = text(
                    """
                    SELECT ins_id, name
                    FROM instruments
                    WHERE ins_id = ANY(:ids)
                    """
                )
                result_rows = session.execute(query, {"ids": unique_ids}).fetchall()
                instrument_names = {row[0]: row[1] for row in result_rows}

            # Add name column
            holdings_with_names = latest_holdings.with_columns(
                pl.col("instrument_id")
                .map_elements(
                    lambda id: instrument_names.get(id, f"Unknown ({id})"),
                    return_dtype=pl.Utf8,
                )
                .alias("name")
            )

            lines.append(f"\nFinal Holdings (as of {latest_date}):")
            lines.append(f"{'Instr ID':>8} {'Name':<30} {'Weight':>10} {'Value':>15}")
            lines.append("-" * 70)

            for row in holdings_with_names.iter_rows(named=True):
                # Truncate name if too long
                name = row["name"][:28] if len(row["name"]) > 28 else row["name"]

                lines.append(
                    f"{row['instrument_id']:>8} "
                    f"{name:<30} "
                    f"{row['weight']:>9.1%} "
                    f"{row['value']:>15,.0f}"
                )

            lines.append("-" * 70)
            lines.append(
                f"{'Total':>8} {'':<30} "
                f"{holdings_with_names['weight'].sum():>9.1%} "
                f"{holdings_with_names['value'].sum():>15,.0f}"
            )

            # Concentration metrics
            lines.append(f"\nConcentration:")
            lines.append(f"  Number of Positions:     {len(holdings_with_names)}")
            lines.append(f"  Max Position Weight:     {holdings_with_names['weight'].max():.1%}")
            lines.append(f"  Top 5 Weight:            {holdings_with_names.head(5)['weight'].sum():.1%}")
            lines.append(
                f"  Top 10 Weight:           {holdings_with_names.head(10)['weight'].sum():.1%}"
            )
        else:
            lines.append("All holdings had invalid instrument_id (filtered out).")

    else:
        lines.append("No holdings history available.")

    # Footer
    footer_width = 140  # Default width
    lines.append("\n" + "=" * footer_width)
    lines.append("END OF REPORT")
    lines.append("=" * footer_width)

    # Write to file
    output_path.write_text("\n".join(lines))
    logger.info(f"✅ Backtest report saved to: {output_path}")
    print(f"\n📄 Report saved to: {output_path}")
    print(f"   ({len(lines)} lines, {len(result.trades)} trades)")


def load_backtest_report(report_file: str | Path) -> str:
    """Load and display a saved backtest report.

    Args:
        report_file: Path to saved report file

    Returns:
        Report contents as string
    """
    report_path = Path(report_file)
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    return report_path.read_text()
