"""Debug position sizing issue in Magic Formula backtest.

Investigate why we're seeing:
- One position at 39.3% (should be max 10%)
- 1,335% total return
- Only trades on last day
"""

from datetime import date

import polars as pl

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def debug_magic_formula():
    """Run Magic Formula and inspect what's happening."""
    print("\n" + "=" * 80)
    print("DEBUG: Magic Formula Position Sizing")
    print("=" * 80)

    strategy = LongOnlyFactorStrategy(
        name="Magic Formula",
        factors={
            "roic_mean_5y_pct": 0.5,
            "fcf_yield_level_pct": 0.5,
        },
        num_positions=30,
        rebalancing_frequency="annual",
    )

    print(f"\nStrategy configuration:")
    print(f"  Max position weight: {strategy.max_position_weight:.1%}")
    print(f"  Num positions: {strategy.num_positions}")

    # Run backtest
    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy,
        from_date=date(2021, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    # Inspect trades
    print(f"\n" + "=" * 80)
    print("TRADES ANALYSIS")
    print("=" * 80)

    print(f"\nTotal trades: {len(result.trades)}")

    # Group by date
    trades_by_date = result.trades.group_by("date").agg([
        pl.count("instrument_id").alias("num_trades"),
        pl.col("action").value_counts().alias("actions"),
    ])

    print(f"\nTrades by date:")
    print(trades_by_date)

    # Show all trades
    print(f"\nAll trades:")
    print(result.trades.select(["date", "instrument_id", "action", "shares", "price", "cost"]))

    # Inspect holdings
    print(f"\n" + "=" * 80)
    print("HOLDINGS ANALYSIS")
    print("=" * 80)

    # Latest holdings
    latest_date = result.holdings_history["date"].max()
    latest_holdings = result.holdings_history.filter(
        pl.col("date") == latest_date
    ).sort("weight", descending=True)

    print(f"\nLatest holdings ({latest_date}):")
    print(f"Total positions: {len(latest_holdings)}")
    print(f"\nWeight distribution:")
    print(latest_holdings.select(["instrument_id", "weight", "value"]))

    # Check if weights sum to ~1.0
    total_weight = latest_holdings["weight"].sum()
    print(f"\nTotal weight: {total_weight:.4f} (should be ~1.0)")

    # Check individual weights vs max
    max_weight = latest_holdings["weight"].max()
    print(f"Max weight: {max_weight:.1%} (should be ≤ {strategy.max_position_weight:.1%})")

    # Inspect returns
    print(f"\n" + "=" * 80)
    print("RETURNS ANALYSIS")
    print("=" * 80)

    print(f"\nTotal days: {len(result.returns_df)}")

    # Check for extreme returns
    extreme_returns = result.returns_df.filter(pl.col("portfolio_return").abs() > 0.1)
    print(f"\nExtreme returns (>10% daily):")
    print(f"  Count: {len(extreme_returns)}")
    if len(extreme_returns) > 0:
        print(f"  Sample:")
        print(extreme_returns.sort("portfolio_return", descending=True).head(10))

    # Cumulative returns over time
    cumulative = (1 + result.returns_df["portfolio_return"]).cum_prod()

    print(f"\nCumulative return progression:")
    # Sample every 100 days
    sample_indices = list(range(0, len(result.returns_df), 100))
    for idx in sample_indices:
        date_val = result.returns_df["date"][idx]
        cum_ret = cumulative[idx] - 1
        print(f"  {date_val}: {cum_ret:>8.1%}")

    # Final
    final_cum = cumulative[-1] - 1
    print(f"  {result.returns_df['date'][-1]}: {final_cum:>8.1%} (final)")

    # Check metadata
    print(f"\n" + "=" * 80)
    print("METADATA")
    print("=" * 80)

    print(f"\nInitial capital: {result.metadata['initial_capital']:,.0f}")
    print(f"Final value: {result.metadata['final_value']:,.0f}")
    print(f"Calculated return: {(result.metadata['final_value'] / result.metadata['initial_capital'] - 1):.1%}")

    return result


if __name__ == "__main__":
    result = debug_magic_formula()

    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)

    # Check what's wrong
    latest_holdings = result.holdings_history.filter(
        pl.col("date") == result.holdings_history["date"].max()
    )

    max_weight = latest_holdings["weight"].max()

    if max_weight > 0.11:  # More than 11% (allowing for small rounding)
        print(f"\n❌ PROBLEM: Max position weight is {max_weight:.1%}")
        print(f"   Should be ≤ 10%")
        print(f"   Bug in position sizing enforcement!")

    if len(result.trades.filter(pl.col("action") == "buy")) < 30:
        print(f"\n❌ PROBLEM: Only {len(result.trades.filter(pl.col('action') == 'buy'))} buy trades")
        print(f"   Should have ~30 per rebalancing")
        print(f"   Missing factor data for earlier periods!")

    num_rebalances = len(result.trades.filter(pl.col("action") == "buy").group_by("date"))
    if num_rebalances < 3:
        print(f"\n❌ PROBLEM: Only {num_rebalances} rebalancing events")
        print(f"   Should have 4 (annual from 2021-2024)")
        print(f"   Missing factor data!")
