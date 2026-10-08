"""Run the Magic Formula strategy - Joel Greenblatt's classic quality + value approach.

The Magic Formula combines:
- Quality: ROIC (Return on Invested Capital) - 5-year average
- Value: FCF Yield (Free Cash Flow Yield) - current level

The strategy ranks all stocks by these two factors equally weighted,
then buys the top 30 stocks and rebalances annually.
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def run_magic_formula():
    """Run Joel Greenblatt's Magic Formula strategy."""
    print("\n" + "=" * 80)
    print("MAGIC FORMULA - JOEL GREENBLATT")
    print("=" * 80)
    print("""
The Magic Formula is one of the most famous factor strategies.
It combines two simple principles:

1. Buy good businesses (high ROIC)
2. Buy them at attractive prices (high FCF yield)

By combining quality and value, the strategy aims to find
"wonderful companies at fair prices" - avoiding both:
- Expensive quality traps
- Cheap value traps

Let's see how it performs in the Swedish market!
    """)

    # Define the Magic Formula strategy
    strategy = LongOnlyFactorStrategy(
        name="Magic Formula",
        factors={
            "roic_mean_5y_pct": 0.5,      # 50% quality (5-year avg ROIC)
            "fcf_yield_level_pct": 0.5,   # 50% value (FCF yield)
        },
        num_positions=30,
        rebalancing_frequency="annual",
        description="Greenblatt's Magic Formula - Quality (ROIC) + Value (FCF Yield)",
    )

    print(f"Strategy Configuration:")
    print(f"  Name: {strategy.name}")
    print(f"  Factors:")
    for factor, weight in strategy.factors.items():
        print(f"    - {factor}: {weight:.0%}")
    print(f"  Portfolio size: {strategy.num_positions} stocks")
    print(f"  Rebalancing: {strategy.rebalancing_frequency}")
    print(f"  Transaction costs: {strategy.transaction_cost_bps} bps per trade")

    # Run backtest
    print(f"\n" + "-" * 80)
    print("Running backtest...")
    print("-" * 80)

    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2021, 1, 1),  # Start when we have 5 years of history
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    print(f"\n✅ Backtest complete!")
    print(f"  Period: {result.metadata['from_date']} to {result.metadata['to_date']}")
    print(f"  Days simulated: {len(result.returns_df):,}")
    print(f"  Rebalancing events: {result.metadata['num_rebalances']}")
    print(f"  Total trades: {len(result.trades)}")

    # Print comprehensive performance report
    print("\n" + "=" * 80)
    result.print_report()

    # Additional analysis
    print("\n" + "=" * 80)
    print("MAGIC FORMULA ANALYSIS")
    print("=" * 80)

    m = result.metrics

    print(f"\n🎯 Key Performance Metrics:")
    print(f"  CAGR:                    {m.cagr:>8.1%}")
    print(f"  Sharpe Ratio:            {m.sharpe_ratio:>8.2f}")
    print(f"  Max Drawdown:            {m.max_drawdown:>8.1%}")
    print(f"  Calmar Ratio:            {m.calmar_ratio:>8.2f}")

    print(f"\n📊 Risk-Adjusted Performance:")
    if m.sharpe_ratio > 1.5:
        print(f"  ✅ Excellent Sharpe ratio (>1.5) - strong risk-adjusted returns")
    elif m.sharpe_ratio > 1.0:
        print(f"  ✅ Good Sharpe ratio (>1.0) - solid risk-adjusted returns")
    elif m.sharpe_ratio > 0.5:
        print(f"  ⚠️  Moderate Sharpe ratio - acceptable but not outstanding")
    else:
        print(f"  ❌ Low Sharpe ratio - poor risk-adjusted returns")

    print(f"\n💪 Drawdown Analysis:")
    if abs(m.max_drawdown) < 0.15:
        print(f"  ✅ Low drawdown (<15%) - smooth ride")
    elif abs(m.max_drawdown) < 0.25:
        print(f"  ✅ Moderate drawdown (<25%) - typical for equity strategies")
    elif abs(m.max_drawdown) < 0.35:
        print(f"  ⚠️  Significant drawdown (<35%) - requires patience")
    else:
        print(f"  ❌ Large drawdown (>35%) - very challenging to hold")

    print(f"\n🏔️  Peak Analysis:")
    print(f"  Time at ATH:             {m.pct_time_at_ath:>8.1%}")
    if m.pct_time_at_ath > 0.4:
        print(f"  ✅ Frequently at new highs - strong momentum")
    elif m.pct_time_at_ath > 0.2:
        print(f"  ✅ Regular new highs - healthy progress")
    else:
        print(f"  ⚠️  Rarely at new highs - choppy performance")

    print(f"\n📈 Trading Efficiency:")
    print(f"  Win Rate:                {m.win_rate:>8.1%}")
    print(f"  Avg Hold Period:         {m.avg_holding_period_months:>8.1f} months")
    if m.win_rate > 0.6:
        print(f"  ✅ High win rate - consistently picking winners")
    elif m.win_rate > 0.5:
        print(f"  ✅ Majority of trades profitable")
    else:
        print(f"  ⚠️  Less than 50% win rate - relies on winners being bigger than losers")

    # Show some sample holdings if available
    if len(result.holdings_history) > 0:
        print(f"\n📋 Sample Holdings (Latest Portfolio):")
        latest_holdings = result.holdings_history.filter(
            pl.col("date") == result.holdings_history["date"].max()
        ).sort("weight", descending=True).head(10)

        print(f"\n  Top 10 Holdings:")
        for row in latest_holdings.iter_rows(named=True):
            print(f"    Instrument {row['instrument_id']:>6}: "
                  f"{row['weight']:>6.1%} "
                  f"({row['value']:>12,.0f} SEK)")

    return result


if __name__ == "__main__":
    import polars as pl

    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  JOEL GREENBLATT'S MAGIC FORMULA".center(78) + "║")
    print("║" + "  Quality (ROIC) + Value (FCF Yield)".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    result = run_magic_formula()

    print("\n" + "=" * 80)
    print("🎉 MAGIC FORMULA BACKTEST COMPLETE!")
    print("=" * 80)
    print("""
Next steps to try:
1. Compare vs other strategies (pure quality, pure value, momentum)
2. Test different portfolio sizes (20, 40, 50 stocks)
3. Test different rebalancing frequencies (monthly, quarterly)
4. Add filters (minimum market cap, liquidity requirements)
5. Analyze position-level metrics to understand hold experience
    """)
