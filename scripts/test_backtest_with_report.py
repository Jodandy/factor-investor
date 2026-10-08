"""Test backtest with comprehensive performance report.

This script demonstrates:
1. Running a backtest with the generic engine
2. Automatic calculation of ~40 performance metrics
3. Printing a comprehensive performance report
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def main():
    """Run backtest and display comprehensive report."""
    print("\n" + "=" * 80)
    print("BACKTEST WITH COMPREHENSIVE PERFORMANCE REPORT")
    print("=" * 80)

    # Define strategy
    strategy = LongOnlyFactorStrategy(
        name="ROIC Quality",
        factors={"roic_mean_5y_pct": 1.0},
        num_positions=30,
        rebalancing_frequency="annual",
        description="Simple ROIC-based quality strategy",
    )

    print(f"\nStrategy: {strategy.name}")
    print(f"  {strategy.description}")
    print(f"  Factors: {strategy.factors}")
    print(f"  Positions: {strategy.num_positions}")
    print(f"  Rebalancing: {strategy.rebalancing_frequency}")

    # Run backtest
    print(f"\nRunning backtest...")
    engine = BacktestEngine()

    result = engine.run(
        strategy=strategy,
        from_date=date(2022, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    print(f"\nBacktest complete!")
    print(f"  Days: {len(result.returns_df)}")
    print(f"  Trades: {len(result.trades)}")
    print(f"  Final value: {result.metadata['final_value']:,.0f}")

    # Print comprehensive report
    print("\n")
    result.print_report()

    # Also demonstrate direct metrics access
    print("\n" + "=" * 80)
    print("EXAMPLE: Direct metrics access")
    print("=" * 80)
    print(f"\nKey metrics:")
    print(f"  CAGR: {result.metrics.cagr:.1%}")
    print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
    print(f"  Max DD: {result.metrics.max_drawdown:.1%}")
    print(f"  Time at ATH: {result.metrics.pct_time_at_ath:.1%}")
    print(f"  Win rate: {result.metrics.win_rate:.1%}")

    return result


if __name__ == "__main__":
    result = main()
    print("\n✅ Test complete!")
