"""Full backtest workflow example.

This script demonstrates the complete workflow for running a backtest
with the generic infrastructure:

1. Define a strategy using the Strategy interface
2. Run backtest using BacktestEngine
3. Automatic calculation of ~40 performance metrics
4. Display comprehensive performance report

The infrastructure is completely generic and works with any strategy type.
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def example_single_factor_strategy():
    """Example: Simple single-factor strategy."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Single-Factor Quality Strategy")
    print("=" * 80)

    # Define strategy - just specify what to hold and when to rebalance
    strategy = LongOnlyFactorStrategy(
        name="ROIC Quality",
        factors={"roic_mean_5y_pct": 1.0},  # Single factor: 5-year average ROIC
        num_positions=30,
        rebalancing_frequency="annual",
        description="Hold top 30 stocks by 5-year average ROIC",
    )

    # Run backtest - engine handles all execution details
    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2022, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    # Print report - all ~40 metrics calculated automatically
    result.print_report()

    return result


def example_multi_factor_strategy():
    """Example: Multi-factor strategy combining quality and value."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Multi-Factor Quality + Value Strategy")
    print("=" * 80)

    # Define strategy - combine multiple factors
    strategy = LongOnlyFactorStrategy(
        name="Quality + Value",
        factors={
            "roic_mean_5y_pct": 0.5,  # 50% weight on quality
            "fcf_yield_level_pct": 0.5,  # 50% weight on value
        },
        num_positions=30,
        rebalancing_frequency="annual",
        description="Hold top 30 stocks by combined quality and value score",
    )

    # Run backtest
    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2022, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    # Print report
    result.print_report()

    return result


def example_compare_strategies():
    """Example: Compare multiple strategies."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Strategy Comparison")
    print("=" * 80)

    strategies = [
        LongOnlyFactorStrategy(
            name="Pure Quality",
            factors={"roic_mean_5y_pct": 1.0},
            num_positions=30,
            rebalancing_frequency="annual",
        ),
        LongOnlyFactorStrategy(
            name="Pure Value",
            factors={"fcf_yield_level_pct": 1.0},
            num_positions=30,
            rebalancing_frequency="annual",
        ),
        LongOnlyFactorStrategy(
            name="Quality + Value",
            factors={
                "roic_mean_5y_pct": 0.5,
                "fcf_yield_level_pct": 0.5,
            },
            num_positions=30,
            rebalancing_frequency="annual",
        ),
    ]

    engine = BacktestEngine()
    results = {}

    for strategy in strategies:
        print(f"\nRunning: {strategy.name}...")
        result = engine.run(
            strategy=strategy,
            from_date=date(2022, 1, 1),
            to_date=date(2024, 12, 31),
            initial_capital=1_000_000,
        )
        results[strategy.name] = result.metrics

    # Print comparison table
    from factor_investor.analytics import generate_summary_table

    table = generate_summary_table(results)
    print("\n" + table)

    return results


def example_access_metrics_programmatically():
    """Example: Access metrics programmatically for custom analysis."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Programmatic Metrics Access")
    print("=" * 80)

    strategy = LongOnlyFactorStrategy(
        name="ROIC Quality",
        factors={"roic_mean_5y_pct": 1.0},
        num_positions=30,
        rebalancing_frequency="annual",
    )

    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2022, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    # Access individual metrics
    m = result.metrics

    print(f"\nKey Performance Indicators:")
    print(f"  CAGR:                {m.cagr:.1%}")
    print(f"  Sharpe Ratio:        {m.sharpe_ratio:.2f}")
    print(f"  Max Drawdown:        {m.max_drawdown:.1%}")
    print(f"  Calmar Ratio:        {m.calmar_ratio:.2f}")

    print(f"\nRecovery Metrics:")
    print(f"  Time at ATH:         {m.pct_time_at_ath:.1%}")
    print(f"  Avg Distance to ATH: {m.avg_distance_to_ath:.1%}")
    print(f"  Max Days Underwater: {m.max_time_underwater} days")

    print(f"\nTrading Metrics:")
    print(f"  Number of Trades:    {m.num_trades}")
    print(f"  Win Rate:            {m.win_rate:.1%}")
    print(f"  Avg Hold Period:     {m.avg_holding_period_months:.1f} months")

    # Custom analysis
    print(f"\nCustom Analysis:")
    if m.sharpe_ratio > 1.0 and m.max_drawdown > -0.25:
        print(f"  ✅ Good risk-adjusted returns with moderate drawdown")
    elif m.sharpe_ratio > 1.0:
        print(f"  ⚠️  Good Sharpe but large drawdown")
    else:
        print(f"  ⚠️  Sharpe ratio below target")

    if m.pct_time_at_ath > 0.3:
        print(f"  ✅ Spends significant time at peaks")
    else:
        print(f"  ⚠️  Rarely at all-time highs")

    return result


def main():
    """Run all examples."""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  GENERIC BACKTEST INFRASTRUCTURE - EXAMPLES".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    # Example 1: Single factor
    result1 = example_single_factor_strategy()

    # Example 2: Multi-factor
    # result2 = example_multi_factor_strategy()  # Uncomment when fcf_yield factor exists

    # Example 3: Comparison
    # results = example_compare_strategies()  # Uncomment when multiple factors exist

    # Example 4: Programmatic access
    result4 = example_access_metrics_programmatically()

    print("\n" + "=" * 80)
    print("KEY FEATURES DEMONSTRATED:")
    print("=" * 80)
    print("""
1. ✅ Generic Strategy Interface
   - Define WHAT to hold (factors, weights, num positions)
   - Define WHEN to rebalance (frequency)
   - Engine handles HOW to execute

2. ✅ Automatic Metrics Calculation
   - ~40 comprehensive metrics calculated automatically
   - Returns, Risk, Risk-adjusted, Recovery, Trading, Statistical
   - Computation time: ~5-10ms (negligible)

3. ✅ Strategy-Agnostic Infrastructure
   - Works with any strategy type (factor, technical, ML, etc.)
   - Separation of concerns: Strategy → Engine → Analytics
   - Consistent metrics across all strategies

4. ✅ Easy to Use
   - Define strategy in 5 lines
   - Run backtest in 1 line
   - Get comprehensive report in 1 line
   - Or access metrics programmatically

5. ✅ Flexible and Extensible
   - Easy to add new strategy types (just implement Strategy ABC)
   - Easy to add new metrics (just update PerformanceMetrics)
   - Easy to add benchmarks (already supported)
    """)

    print("✅ All examples complete!")


if __name__ == "__main__":
    main()
