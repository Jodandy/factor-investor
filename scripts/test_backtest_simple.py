"""Simple end-to-end backtest test.

This script tests the basic backtesting infrastructure:
1. Strategy can generate signals
2. Portfolio can rebalance
3. BacktestEngine can run simulation
4. Results are generated correctly

This is a smoke test before building full performance analytics.
"""

from datetime import date

from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy


def test_simple_backtest():
    """Run a simple backtest to verify infrastructure works."""
    print("\n" + "=" * 80)
    print("SIMPLE BACKTEST TEST")
    print("=" * 80)

    # Define a simple strategy
    strategy = LongOnlyFactorStrategy(
        name="ROIC Quality (Test)",
        factors={"roic_mean_5y_pct": 1.0},
        num_positions=30,
        rebalancing_frequency="annual",
        description="Simple ROIC-based quality strategy for testing",
    )

    print(f"\nStrategy: {strategy.name}")
    print(f"  Factors: {strategy.factors}")
    print(f"  Positions: {strategy.num_positions}")
    print(f"  Rebalancing: {strategy.rebalancing_frequency}")

    # Run backtest (short period for testing)
    engine = BacktestEngine()

    print(f"\nRunning backtest...")
    result = engine.run(
        strategy=strategy,
        from_date=date(2022, 1, 1),
        to_date=date(2024, 12, 31),
        initial_capital=1_000_000,
    )

    print(f"\nBacktest complete!")

    # Check results
    print(f"\n" + "-" * 80)
    print("RESULTS SUMMARY")
    print("-" * 80)

    print(f"\nMetadata:")
    for key, value in result.metadata.items():
        print(f"  {key:20s}: {value}")

    print(f"\nReturns DataFrame:")
    print(f"  Rows: {len(result.returns_df)}")
    print(f"  Columns: {result.returns_df.columns}")
    if len(result.returns_df) > 0:
        print(f"  Sample (first 5):")
        print(result.returns_df.head(5))

    print(f"\nHoldings History:")
    print(f"  Rows: {len(result.holdings_history)}")
    if len(result.holdings_history) > 0:
        print(f"  Sample (first 5):")
        print(result.holdings_history.head(5))

    print(f"\nTrades:")
    print(f"  Total trades: {len(result.trades)}")
    if len(result.trades) > 0:
        print(f"  Sample (first 5):")
        print(result.trades.head(5))

        # Aggregate stats
        buy_trades = result.trades.filter(pl.col("action") == "buy")
        sell_trades = result.trades.filter(pl.col("action") == "sell")

        print(f"\n  Buy trades: {len(buy_trades)}")
        print(f"  Sell trades: {len(sell_trades)}")

        if len(buy_trades) > 0:
            total_buy_value = (buy_trades["shares"] * buy_trades["price"]).sum()
            total_buy_cost = buy_trades["cost"].sum()
            print(f"  Total buy value: {total_buy_value:,.0f}")
            print(f"  Total buy costs: {total_buy_cost:,.0f}")

    # Display comprehensive performance metrics
    if len(result.returns_df) > 0:
        print(f"\n" + "-" * 80)
        print("COMPREHENSIVE PERFORMANCE METRICS")
        print("-" * 80)

        m = result.metrics  # Shorthand

        # Returns
        print(f"\nReturns:")
        print(f"  Total return:       {m.total_return:>12.1%}")
        print(f"  CAGR:               {m.cagr:>12.1%}")
        print(f"  Annualized return:  {m.annualized_return:>12.1%}")

        # Risk
        print(f"\nRisk:")
        print(f"  Volatility:         {m.volatility:>12.1%}")
        print(f"  Downside vol:       {m.downside_volatility:>12.1%}")
        print(f"  Max drawdown:       {m.max_drawdown:>12.1%}")
        print(f"    From:             {m.max_drawdown_start}")
        print(f"    To:               {m.max_drawdown_end}")

        # Risk-adjusted
        print(f"\nRisk-Adjusted:")
        print(f"  Sharpe ratio:       {m.sharpe_ratio:>12.2f}")
        print(f"  Sortino ratio:      {m.sortino_ratio:>12.2f}")
        print(f"  Calmar ratio:       {m.calmar_ratio:>12.2f}")
        print(f"  Omega ratio:        {m.omega_ratio:>12.2f}")
        print(f"  Ulcer index:        {m.ulcer_index:>12.4f}")
        print(f"  Pain index:         {m.pain_index:>12.4f}")
        print(f"  Recovery factor:    {m.recovery_factor:>12.2f}")

        # Recovery & Peak
        print(f"\nRecovery & Peak:")
        print(f"  Current dist to ATH:{m.current_distance_to_ath:>12.1%}")
        print(f"  Avg dist to ATH:    {m.avg_distance_to_ath:>12.1%}")
        print(f"  Time at ATH:        {m.pct_time_at_ath:>12.1%}")
        print(f"  Time near ATH (5%):{m.pct_time_near_ath:>12.1%}")
        print(f"  Max days underwater:{m.max_time_underwater:>12,.0f}")
        print(f"  Avg recovery time:  {m.avg_recovery_time:>12.0f} days")
        print(f"  Lake ratio:         {m.lake_ratio:>12.4f}")

        # Trading
        print(f"\nTrading:")
        print(f"  Num trades:         {m.num_trades:>12,.0f}")
        print(f"  Annual turnover:    {m.annual_turnover:>12,.0f}")
        print(f"  Avg hold period:    {m.avg_holding_period_months:>12.1f} months")
        print(f"  Win rate:           {m.win_rate:>12.1%}")

        # Statistical
        print(f"\nStatistical:")
        print(f"  Skewness:           {m.skewness:>12.2f}")
        print(f"  Kurtosis:           {m.kurtosis:>12.2f}")
        print(f"  VaR (95%):          {m.var_95:>12.2%}")
        print(f"  CVaR (95%):         {m.cvar_95:>12.2%}")
        print(f"  Tail ratio:         {m.tail_ratio:>12.2f}")

    # Verify data integrity
    print(f"\n" + "-" * 80)
    print("DATA INTEGRITY CHECKS")
    print("-" * 80)

    checks_passed = True

    # Check 1: Returns should have data
    if len(result.returns_df) == 0:
        print("  ✗ FAIL: No returns data")
        checks_passed = False
    else:
        print(f"  ✓ Returns data: {len(result.returns_df)} days")

    # Check 2: Trades should have happened
    if len(result.trades) == 0:
        print("  ✗ FAIL: No trades executed")
        checks_passed = False
    else:
        print(f"  ✓ Trades executed: {len(result.trades)}")

    # Check 3: Holdings should have been tracked
    if len(result.holdings_history) == 0:
        print("  ✗ FAIL: No holdings tracked")
        checks_passed = False
    else:
        print(f"  ✓ Holdings tracked: {len(result.holdings_history)} snapshots")

    # Check 4: Final value should be positive
    if result.metadata["final_value"] <= 0:
        print(f"  ✗ FAIL: Final value <= 0: {result.metadata['final_value']}")
        checks_passed = False
    else:
        print(f"  ✓ Final value positive: {result.metadata['final_value']:,.0f}")

    # Check 5: Total return should be reasonable
    total_return = result.metrics.total_return
    if abs(total_return) > 10.0:  # > 1000% seems unreasonable
        print(f"  ✗ FAIL: Total return seems unreasonable: {total_return:.1%}")
        checks_passed = False
    else:
        print(f"  ✓ Total return reasonable: {total_return:.1%}")

    # Check 6: Metrics should be calculated
    if result.metrics is None:
        print("  ✗ FAIL: No performance metrics calculated")
        checks_passed = False
    else:
        print(f"  ✓ Performance metrics calculated: {len([f for f in result.metrics.__dataclass_fields__])} metrics")

    if checks_passed:
        print(f"\n✅ ALL INTEGRITY CHECKS PASSED")
    else:
        print(f"\n❌ SOME CHECKS FAILED")

    return checks_passed


if __name__ == "__main__":
    import polars as pl

    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  BACKTEST INFRASTRUCTURE TEST".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    success = test_simple_backtest()

    if success:
        print("\n" + "=" * 80)
        print("✅ BACKTEST ENGINE WORKS!")
        print("=" * 80)
        print("\nReady to add performance analytics and visualization.")
    else:
        print("\n" + "=" * 80)
        print("❌ BACKTEST TEST FAILED")
        print("=" * 80)
