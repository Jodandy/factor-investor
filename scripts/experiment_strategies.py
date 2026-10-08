"""Experiment with multiple strategies - saving results to files.

This demonstrates how to test different strategies and save each result
to a file for later comparison.

During experimentation phase:
- Each strategy overwrites the same file (latest_backtest_result.txt)
- Easy to inspect the latest test
- Low clutter

Later, we'll build a proper cataloging system.
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def test_strategy(name: str, factors: dict[str, float], description: str):
    """Test a strategy and save results to latest_backtest_result.txt."""

    print("\n" + "=" * 80)
    print(f"TESTING: {name}")
    print("=" * 80)

    # Define strategy
    strategy = LongOnlyFactorStrategy(
        name=name,
        factors=factors,
        num_positions=30,
        rebalancing_frequency="annual",
        description=description,
    )

    # Run backtest
    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2018, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    # Print summary
    print(f"\nQuick Summary:")
    print(f"  Total Return:  {result.metrics.total_return:>8.1%}")
    print(f"  CAGR:          {result.metrics.cagr:>8.1%}")
    print(f"  Sharpe:        {result.metrics.sharpe_ratio:>8.2f}")
    print(f"  Max DD:        {result.metrics.max_drawdown:>8.1%}")
    print(f"  Win Rate:      {result.metrics.win_rate:>8.1%}")
    print(f"  Trades:        {len(result.trades):>8,}")

    # Save to latest_backtest_result.txt (overwrites each time)
    result.save_report()

    return result


def main():
    """Test multiple strategies, one at a time."""

    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  STRATEGY EXPERIMENTATION".center(78) + "║")
    print("║" + "  Testing different factor combinations".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    # STRATEGY 1: ROIC Quality
    print("\n\n📊 STRATEGY 1: Pure Quality (ROIC)")
    test_strategy(
        name="ROIC Quality",
        factors={"roic_mean_5y_pct": 1.0},
        description="Top 30 stocks by 5-year average ROIC",
    )

    input("\n⏸️  Press Enter to test next strategy...")

    # STRATEGY 2: FCF Yield Value
    print("\n\n📊 STRATEGY 2: Pure Value (FCF Yield)")
    test_strategy(
        name="FCF Yield Value",
        factors={"fcf_yield_level_pct": 1.0},
        description="Top 30 stocks by free cash flow yield",
    )

    input("\n⏸️  Press Enter to test next strategy...")

    # STRATEGY 3: Magic Formula (50/50 ROIC + FCF Yield)
    print("\n\n📊 STRATEGY 3: Magic Formula (Quality + Value)")
    test_strategy(
        name="Magic Formula 50/50",
        factors={
            "roic_mean_5y_pct": 0.5,
            "fcf_yield_level_pct": 0.5,
        },
        description="Greenblatt's Magic Formula: 50% ROIC, 50% FCF Yield",
    )

    input("\n⏸️  Press Enter to test next strategy...")

    # STRATEGY 4: Quality-focused Magic Formula (70/30)
    print("\n\n📊 STRATEGY 4: Quality-Focused Magic Formula (70/30)")
    test_strategy(
        name="Magic Formula 70/30",
        factors={
            "roic_mean_5y_pct": 0.7,
            "fcf_yield_level_pct": 0.3,
        },
        description="Quality-focused: 70% ROIC, 30% FCF Yield",
    )

    # Final summary
    print("\n" + "=" * 80)
    print("✅ EXPERIMENTATION COMPLETE")
    print("=" * 80)
    print(f"""
All strategies tested! Results saved to: latest_backtest_result.txt

The file currently contains the LAST strategy tested (Magic Formula 70/30).

To compare strategies:
1. Re-run specific strategy scripts (e.g., run_magic_formula.py)
2. Each run overwrites latest_backtest_result.txt
3. Inspect the file after each run

Next steps:
- Build visualization module to plot equity curves
- Add benchmark comparison
- Build proper strategy cataloging system
    """)


if __name__ == "__main__":
    main()
