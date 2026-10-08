# Backtest Quick Start Guide

## TL;DR

```python
from datetime import date
from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy

# Define strategy (5 lines)
strategy = LongOnlyFactorStrategy(
    name="ROIC Quality",
    factors={"roic_mean_5y_pct": 1.0},
    num_positions=30,
    rebalancing_frequency="annual",
)

# Run backtest (1 line)
engine = BacktestEngine()
result = engine.run(strategy, date(2016, 1, 1), date(2024, 12, 31), 1_000_000)

# Get report (1 line)
result.print_report()  # Shows all ~40 metrics!
```

## Run Pre-built Examples

```bash
# Clean baseline (ROIC only, 2016-2024)
uv run python scripts/run_clean_backtest_2016.py

# Magic Formula (ROIC + FCF Yield)
uv run python scripts/run_magic_formula.py

# Full examples with multiple strategies
uv run python scripts/example_full_backtest.py
```

## Available Factors

Current factors in system:
- `roic_mean_5y_pct` - 5-year average ROIC, percentile normalized
- `fcf_yield_level_pct` - Free cash flow yield, percentile normalized
- More factors: see factor definitions in database

## Strategy Parameters

```python
LongOnlyFactorStrategy(
    name="Strategy Name",
    factors={"factor_id": weight, ...},  # Weights must sum to 1.0
    num_positions=30,                     # Portfolio size
    rebalancing_frequency="annual",       # monthly, quarterly, annual
    position_sizing="equal_weight",       # equal_weight or factor_weighted
    min_market_cap=None,                  # Optional market cap filter (SEK)
    description="...",                    # Optional description
)
```

## Understanding Results

```python
result = engine.run(...)

# Access metrics directly
print(f"CAGR: {result.metrics.cagr:.1%}")
print(f"Sharpe: {result.metrics.sharpe_ratio:.2f}")
print(f"Max DD: {result.metrics.max_drawdown:.1%}")

# Full report
result.print_report()

# Raw data
result.returns_df        # Daily returns
result.trades            # All trades executed
result.holdings_history  # Holdings over time
```

## Performance Metrics (~40 total)

**Returns:** Total return, CAGR, annualized return

**Risk:** Volatility, downside volatility, max drawdown

**Risk-Adjusted:** Sharpe, Sortino, Calmar, Omega, Ulcer, Pain, Recovery factor

**Recovery & Peak:** Distance to ATH, time at ATH, underwater periods, lake ratio

**Trading:** Number of trades, turnover, holding periods, win rate

**Statistical:** Skewness, kurtosis, VaR, CVaR, tail ratio

## Data Quality Issues

Some instruments have corrupt data. They are automatically filtered out.

**View corrupted list:**
```python
from factor_investor.universe.corrupted_instruments import load_corrupted_instruments
corrupted = load_corrupted_instruments()
print(corrupted)
```

**Add to corrupted list:**

Edit `config/corrupted_instruments.yaml`:
```yaml
corrupted_instruments:
  - instrument_id: 12345
    name: "Company Name"
    issue: "Extreme price spike - likely reverse split"
    date_identified: "2025-01-08"
    notes: "Additional context"
```

Or programmatically:
```python
from factor_investor.universe.corrupted_instruments import add_corrupted_instrument
add_corrupted_instrument(12345, "Company Name", "Issue description")
```

## Troubleshooting

**"No data for YYYY-MM-DD after filtering"**
- Normal if factor requires historical data (e.g., 5-year mean)
- Rebalancing skipped if no factor data available

**Extreme returns (>500%)**
- Likely data quality issue (reverse splits, corrupt data)
- Identify outlier instrument and add to corrupted list

**High position concentration (>15%)**
- Check if winner stock grew over time (normal for long-only)
- Or data quality issue - investigate instrument

**Low CAGR vs expectations**
- Check number of rebalancing events (need enough data)
- Single-factor strategies typically lower than multi-factor
- Compare vs benchmark

## Next Steps

1. **Compare strategies:** Run multiple and compare metrics
2. **Visualize:** Build equity curve, drawdown charts (TODO)
3. **Add filters:** Liquidity, market cap (liquidity needs volume data)
4. **Custom strategies:** Implement Strategy ABC for your own logic

## Architecture

For detailed architecture documentation, see:
- `docs/BACKTEST_INFRASTRUCTURE.md` - Complete architecture guide
- Code documentation in each module (docstrings)

## Support

Check example scripts in `scripts/` folder for working examples.
