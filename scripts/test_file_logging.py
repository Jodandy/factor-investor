"""Test file logging for backtest results.

This demonstrates saving complete backtest reports to file, including:
- Strategy configuration
- Performance metrics
- ALL trades with details
- Top/bottom daily returns
- Holdings summary

The file is overwritten each run (for experimentation phase).
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def main():
    """Run a simple backtest and save results to file."""

    print("\n" + "=" * 80)
    print("FILE LOGGING TEST")
    print("=" * 80)

    # Define a simple strategy
    strategy = LongOnlyFactorStrategy(
        name="ROIC Quality - File Logging Test",
        factors={"roic_mean_5y_pct": 1.0},
        num_positions=30,
        rebalancing_frequency="annual",
        description="Top 30 stocks by 5-year average ROIC",
    )

    print(f"\nStrategy: {strategy.name}")
    print(f"Testing file logging functionality...")

    # Run backtest
    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2020, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    print(f"\n" + "-" * 80)
    print(f"Backtest complete:")
    print(f"  Period: {result.metadata['from_date']} to {result.metadata['to_date']}")
    print(f"  Total return: {result.metrics.total_return:.1%}")
    print(f"  CAGR: {result.metrics.cagr:.1%}")
    print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
    print(f"  Max drawdown: {result.metrics.max_drawdown:.1%}")
    print(f"  Trades: {len(result.trades)}")

    # Save to default file (latest_backtest_result.txt)
    print(f"\n" + "-" * 80)
    print(f"Saving report to file...")
    result.save_report()

    # Also save to custom file for comparison
    custom_file = "roic_quality_test.txt"
    print(f"\nSaving to custom file: {custom_file}")
    result.save_report(custom_file)

    print(f"\n" + "=" * 80)
    print(f"✅ Test complete!")
    print(f"\n📄 Check these files:")
    print(f"   - latest_backtest_result.txt")
    print(f"   - {custom_file}")
    print(f"\nBoth contain:")
    print(f"   - Strategy configuration")
    print(f"   - All ~40 performance metrics")
    print(f"   - All {len(result.trades)} trades with details")
    print(f"   - Top/bottom daily returns")
    print(f"   - Holdings summary")
    print("=" * 80)


if __name__ == "__main__":
    main()
