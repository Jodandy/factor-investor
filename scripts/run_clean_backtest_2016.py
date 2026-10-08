"""Clean backtest from 2016-2024 with single-factor ROIC strategy.

This provides a clean baseline to verify the infrastructure works correctly
without data quality issues from multi-factor strategies or short time periods.

Strategy:
- Single factor: ROIC (5-year average, percentile normalized)
- 30 positions, equal weighted
- Annual rebalancing
- Period: 2016-2024 (8 years)
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def run_clean_roic_backtest():
    """Run clean ROIC backtest from 2016."""
    print("\n" + "=" * 80)
    print("CLEAN BASELINE BACKTEST: ROIC Quality (2016-2024)")
    print("=" * 80)
    print("""
This is a clean baseline test to verify infrastructure:
- Single factor (ROIC only) - simpler, less data quality issues
- 8 year period (2016-2024) - more rebalancing events
- Corrupted instruments filtered automatically

Goal: Establish realistic baseline performance expectations
    """)

    # Invalidate corrupted instruments cache to reload new list
    from factor_investor.universe.corrupted_instruments import _CORRUPTED_INSTRUMENTS_CACHE
    import factor_investor.universe.corrupted_instruments as ci_module
    ci_module._CORRUPTED_INSTRUMENTS_CACHE = None

    # Load and show corrupted instruments
    from factor_investor.universe.corrupted_instruments import load_corrupted_instruments
    corrupted = load_corrupted_instruments()
    print(f"\nCorrupted instruments (automatically filtered): {len(corrupted)}")
    for inst_id in sorted(corrupted):
        print(f"  - {inst_id}")

    # Define simple ROIC strategy
    strategy = LongOnlyFactorStrategy(
        name="ROIC Quality",
        factors={"roic_mean_5y_pct": 1.0},  # Single factor, 100% weight
        num_positions=30,
        rebalancing_frequency="annual",
        description="Top 30 stocks by 5-year average ROIC (percentile ranked)",
    )

    print(f"\n" + "-" * 80)
    print("Strategy Configuration:")
    print(f"  Name: {strategy.name}")
    print(f"  Factor: roic_mean_5y_pct (5-year average ROIC, percentile normalized)")
    print(f"  Portfolio size: {strategy.num_positions} stocks")
    print(f"  Rebalancing: {strategy.rebalancing_frequency}")
    print(f"  Transaction costs: {strategy.transaction_cost_bps} bps per trade")
    print(f"  Max position weight: {strategy.max_position_weight:.1%}")

    # Run backtest
    print(f"\n" + "-" * 80)
    print("Running backtest...")
    print(f"  Period: 2016-01-01 to 2024-12-31 (8 years)")
    print(f"  Initial capital: 1,000,000 SEK")
    print("-" * 80)

    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2016, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    print(f"\n✅ Backtest complete!")
    print(f"  Period: {result.metadata['from_date']} to {result.metadata['to_date']}")
    print(f"  Days simulated: {len(result.returns_df):,}")
    print(f"  Rebalancing events: {result.metadata['num_rebalances']}")
    print(f"  Total trades: {len(result.trades)}")

    # Print comprehensive report
    print("\n" + "=" * 80)
    result.print_report()

    # Additional analysis
    print("\n" + "=" * 80)
    print("DATA QUALITY CHECKS")
    print("=" * 80)

    m = result.metrics

    # Check for reasonable returns
    print(f"\n📊 Returns Analysis:")
    print(f"  CAGR: {m.cagr:.1%}")
    if 0.05 <= m.cagr <= 0.30:
        print(f"  ✅ CAGR in reasonable range (5-30% annually)")
    elif m.cagr > 0.30:
        print(f"  ⚠️  High CAGR - may still have data quality issues")
    else:
        print(f"  ⚠️  Low CAGR - check if strategy is working")

    # Check for extreme single-day returns
    extreme_days = result.returns_df.filter(pl.col("portfolio_return").abs() > 0.10)
    print(f"\n📈 Extreme Daily Returns (>10%):")
    print(f"  Count: {len(extreme_days)}")
    if len(extreme_days) > 5:
        print(f"  ⚠️  Many extreme days - possible data quality issues")
        print(f"  Sample:")
        print(extreme_days.sort("portfolio_return", descending=True).head(5))
    else:
        print(f"  ✅ Few extreme days - looks clean")

    # Check position concentration
    if len(result.holdings_history) > 0:
        latest_holdings = result.holdings_history.filter(
            pl.col("date") == result.holdings_history["date"].max()
        ).sort("weight", descending=True)

        max_weight = latest_holdings["weight"].max()
        print(f"\n📊 Position Concentration:")
        print(f"  Max position: {max_weight:.1%}")
        if max_weight > 0.15:
            print(f"  ⚠️  High concentration - check top position")
            top_5 = latest_holdings.head(5)
            print(f"  Top 5 positions:")
            for row in top_5.iter_rows(named=True):
                print(f"    Instrument {row['instrument_id']:6d}: {row['weight']:>6.1%}")
        else:
            print(f"  ✅ Reasonable diversification")

    # Check max drawdown
    print(f"\n💪 Drawdown Analysis:")
    print(f"  Max drawdown: {m.max_drawdown:.1%}")
    if abs(m.max_drawdown) < 0.30:
        print(f"  ✅ Moderate drawdown - healthy")
    elif abs(m.max_drawdown) < 0.50:
        print(f"  ⚠️  Significant drawdown - challenging to hold")
    else:
        print(f"  ❌ Extreme drawdown - likely data issues")

    # Summary
    print(f"\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if (0.08 <= m.cagr <= 0.25 and
        abs(m.max_drawdown) < 0.40 and
        max_weight < 0.20 and
        len(extreme_days) < 10):
        print(f"\n✅ BACKTEST LOOKS CLEAN!")
        print(f"   - Returns reasonable")
        print(f"   - No extreme outliers")
        print(f"   - Diversified positions")
        print(f"   - Ready for strategy comparison")
    else:
        print(f"\n⚠️  POTENTIAL DATA QUALITY ISSUES")
        print(f"   - Review extreme returns")
        print(f"   - Check concentrated positions")
        print(f"   - May need more filtering")

    return result


if __name__ == "__main__":
    import polars as pl

    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  CLEAN BASELINE BACKTEST".center(78) + "║")
    print("║" + "  ROIC Quality Strategy 2016-2024".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    result = run_clean_roic_backtest()

    print("\n" + "=" * 80)
    print("✅ Clean baseline backtest complete!")
    print("=" * 80)
    print(f"""
Next steps:
1. If clean: Compare with other strategies (value, momentum, multi-factor)
2. If data issues: Add more instruments to corrupted list
3. Build visualization tools to spot outliers visually
4. Add liquidity filter when volume data available
    """)
