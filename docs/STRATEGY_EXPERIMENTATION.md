# Strategy Experimentation Guide

Guide för att experimentera med olika strategier under utvecklingsfasen.

## TL;DR

```python
from factor_investor.backtest import BacktestEngine, LongOnlyFactorStrategy

# Define strategy
strategy = LongOnlyFactorStrategy(
    name="My Strategy",
    factors={"roic_mean_5y_pct": 0.7, "fcf_yield_level_pct": 0.3},
    num_positions=30,
)

# Run backtest
engine = BacktestEngine()
result = engine.run(strategy, from_date, to_date, initial_capital)

# Save complete report to file (overwrites each time)
result.save_report()  # → latest_backtest_result.txt
```

## File Logging System

### During Experimentation Phase

**Approach:** Overwrite samma fil varje körning

**Benefits:**
- ✅ Inga cluttrande filer
- ✅ Enkelt att hitta senaste resultatet
- ✅ Snabbt att iterera

**File:** `latest_backtest_result.txt`

**Contents:**
- Strategy configuration (factors, parameters)
- All ~40 performance metrics
- ALL trades with details (date, instrument, shares, price, value, cost)
- Top/bottom daily returns
- Holdings summary
- Concentration metrics

### Example Usage

```python
# Test Strategy 1
result = engine.run(strategy1, ...)
result.save_report()  # Overwrites latest_backtest_result.txt
# → Open file and review

# Test Strategy 2
result = engine.run(strategy2, ...)
result.save_report()  # Overwrites latest_backtest_result.txt
# → Open file and review

# Test Strategy 3
result = engine.run(strategy3, ...)
result.save_report("my_favorite_strategy.txt")  # Save to custom file
```

## Recommended Workflow

### 1. Quick Iteration (Use Default File)

```bash
# Run test
uv run python scripts/experiment_strategies.py

# Review results
cat latest_backtest_result.txt | less

# Modify strategy, run again
# (file is overwritten automatically)
```

### 2. Save Important Results

```python
# Found a good strategy? Save to custom file
result.save_report("magic_formula_70_30_BEST.txt")
```

### 3. Compare Multiple Strategies

```python
# Run all strategies and save each
results = {}

for name, factors in strategy_configs.items():
    strategy = LongOnlyFactorStrategy(name=name, factors=factors)
    result = engine.run(strategy, ...)
    results[name] = result
    result.save_report(f"{name}_results.txt")  # Save each separately

# Later: build comparison table
from factor_investor.analytics import generate_summary_table
metrics = {name: r.metrics for name, r in results.items()}
table = generate_summary_table(metrics)
print(table)
```

## Report Format

### Section 1: Strategy Configuration

```
STRATEGY CONFIGURATION
Name:                Magic Formula 70/30
Description:         Quality-focused: 70% ROIC, 30% FCF Yield

Factors:
  - roic_mean_5y_pct                          70.0%
  - fcf_yield_level_pct                       30.0%

Portfolio Parameters:
  Number of Positions:     30
  Rebalancing Frequency:   annual
  Position Sizing:         equal_weight

Transaction Costs:
  Basis Points per Trade:  10

Risk Management:
  Max Position Weight:     10.0%

Backtest Period:
  From:                    2018-01-01
  To:                      2024-12-31
  Trading Days:            2,557
  Rebalancing Events:      7
```

### Section 2: Performance Metrics

All ~40 metrics automatically calculated and displayed:
- Returns (3): Total return, CAGR, Annualized return
- Risk (5): Volatility, Downside volatility, Max drawdown (with dates)
- Risk-Adjusted (7): Sharpe, Sortino, Calmar, Omega, Ulcer, Pain, Recovery factor
- Recovery & Peak (7): Distance to ATH, Time at ATH, Underwater periods
- Trading (4): Number of trades, Turnover, Holding periods, Win rate
- Statistical (5): Skewness, Kurtosis, VaR, CVaR, Tail ratio

### Section 3: Top/Bottom Daily Returns

```
TOP 10 DAILY RETURNS
Date             Return
-------------------------
2021-10-20      10.55%
2021-02-16       8.83%
...

BOTTOM 10 DAILY RETURNS
Date             Return
-------------------------
2020-03-12      -8.45%
...
```

### Section 4: ALL TRADES

Complete trade history with details:

```
Date         Action Instr ID     Shares      Price           Value       Cost
2020-12-31   buy       67471     14,414       2.31          33,333      33.33
2020-12-31   buy       31967      4,331       7.70          33,333      33.33
...

TRADE SUMMARY
Total Buys:      103    Value:         999,990 SEK
Total Sells:      73    Value:         722,345 SEK
Total Costs:              Value:           1,723 SEK
```

### Section 5: Holdings Summary

Final holdings with concentration metrics:

```
Final Holdings (as of 2024-12-31):
Instr ID    Weight          Value
   23459     5.1%         120,456
   18364     4.8%         113,234
   ...

Concentration:
  Number of Positions:     30
  Max Position Weight:     5.1%
  Top 5 Weight:            19.4%
  Top 10 Weight:           31.8%
```

## Next: Build Cataloging System

When experimentation matures, build a system to:

1. **Auto-name files**: `{strategy_name}_{date}_{hash}.txt`
2. **Database catalog**: Store metadata, parameters, metrics
3. **Comparison tools**: Load and compare multiple saved results
4. **Version control**: Track parameter changes over time
5. **Best-of tracking**: Mark and tag best-performing strategies

Example future system:

```python
# Save with auto-cataloging
catalog = StrategyCatalog()
catalog.save(result, tags=["magic_formula", "quality_focused", "v2"])

# Later: query and compare
best_strategies = catalog.query(
    min_sharpe=1.0,
    max_drawdown=(-0.30, 0),
    tags=["magic_formula"]
)

comparison = catalog.compare(best_strategies)
print(comparison)
```

## Tips

**During Experimentation:**
- Use `latest_backtest_result.txt` as scratch space
- Review file after each run
- Save good results to custom files manually
- Focus on understanding what works, not cataloging

**When You Find Winners:**
- Save to named files: `strategy_v1_GOOD.txt`, `strategy_v2_BETTER.txt`
- Add notes in commit messages
- Build comparison table manually

**When Ready for Production:**
- Build cataloging system
- Add version control
- Track all parameters
- Build automated comparison tools

## See Also

- `scripts/experiment_strategies.py` - Example workflow
- `scripts/test_file_logging.py` - Basic test
- `docs/BACKTEST_QUICKSTART.md` - Backtest basics
- `src/factor_investor/analytics/reports.py` - Report generation code
