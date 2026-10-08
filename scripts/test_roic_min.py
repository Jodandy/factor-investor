"""Test ROIC with MIN transformation instead of MEAN.

This is more conservative - selects companies based on their WORST year,
not their average.
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def main():
    print("\n" + "=" * 80)
    print("TEST: ROIC MIN (Conservative)")
    print("=" * 80)
    print("""
Using ROIC MIN (5-year minimum) instead of MEAN.

This selects companies that had good ROIC even in their WORST year.
More conservative than mean - avoids companies with one good year.
    """)

    # Strategy using MIN instead of MEAN
    strategy = LongOnlyFactorStrategy(
        name="ROIC Min Conservative",
        factors={"roic_min_5y_pct": 1.0},  # MIN instead of MEAN
        num_positions=30,
        rebalancing_frequency="annual",
        description="Top 30 by worst (minimum) ROIC over 5 years",
    )

    print(f"Factor: roic_min_5y_pct")
    print(f"  - Transformation: min (worst year)")
    print(f"  - Window: 5 years")
    print(f"  - Normalization: percentile")

    # Run backtest
    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2020, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    print(f"\n" + "-" * 80)
    print("Results:")
    print(f"  CAGR:          {result.metrics.cagr:>8.1%}")
    print(f"  Total Return:  {result.metrics.total_return:>8.1%}")
    print(f"  Sharpe:        {result.metrics.sharpe_ratio:>8.2f}")
    print(f"  Max Drawdown:  {result.metrics.max_drawdown:>8.1%}")
    print(f"  Trades:        {len(result.trades):>8,}")

    # Save report
    result.save_report()

    print("\n" + "=" * 80)
    print("✅ Report saved to: latest_backtest_result.txt")
    print("\nCheck the factor values (roic_pct and roic_val) in trades table.")
    print("These should show the MINIMUM ROIC over 5 years, not the average.")
    print("=" * 80)


if __name__ == "__main__":
    main()
