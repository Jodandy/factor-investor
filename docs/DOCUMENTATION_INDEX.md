# Documentation Index

Complete guide to all documentation in the project.

## 📚 Getting Started

**New to the project?** Start here:

1. **[BACKTEST_QUICKSTART.md](BACKTEST_QUICKSTART.md)** - Quick start guide
   - TL;DR example (3 lines of code)
   - Run pre-built examples
   - Basic usage patterns
   - Troubleshooting

2. **[Example Scripts](../scripts/)** - Working examples
   - `run_clean_backtest_2016.py` - Clean baseline example
   - `run_magic_formula.py` - Multi-factor strategy
   - `example_full_backtest.py` - Complete workflow

## 🏗️ Architecture & Design

**Understanding the system:**

1. **[BACKTEST_INFRASTRUCTURE.md](BACKTEST_INFRASTRUCTURE.md)** - Complete architecture
   - Design principles (separation of concerns)
   - Architecture overview (Strategy → Engine → Analytics)
   - Usage examples (single-factor, multi-factor, comparison)
   - Key design decisions
   - Performance characteristics
   - Benefits and trade-offs

2. **[src/factor_investor/backtest/README.md](../src/factor_investor/backtest/README.md)** - Module details
   - Strategy interface specification
   - Portfolio class details
   - BacktestEngine internals
   - Data flow diagrams
   - Transaction cost modeling
   - Known limitations

3. **[STRATEGY_EXPERIMENTATION.md](STRATEGY_EXPERIMENTATION.md)** - Experimentation workflow
   - File logging system
   - Recommended workflow
   - Report format
   - Tips for experimentation
   - Future cataloging system

## 📖 API Documentation

**Code-level documentation:**

All modules have comprehensive docstrings:

- **`backtest/strategy.py`** - Strategy ABC, TargetPortfolio, LongOnlyFactorStrategy
- **`backtest/portfolio.py`** - Portfolio, Trade classes
- **`backtest/engine.py`** - BacktestEngine, BacktestResult
- **`analytics/metrics.py`** - PerformanceMetrics, calculate_performance_metrics
- **`analytics/reports.py`** - Report generation functions
- **`universe/corrupted_instruments.py`** - Data quality filtering

Read docstrings with:
```python
from factor_investor.backtest import BacktestEngine
help(BacktestEngine)
```

## 🔧 Operations & Maintenance

**Working with the system:**

1. **Data Quality Management:**
   - **[config/corrupted_instruments.yaml](../config/corrupted_instruments.yaml)** - Corrupt instruments list
   - **[universe/corrupted_instruments.py](../src/factor_investor/universe/corrupted_instruments.py)** - Filter API
   - How to add instruments (edit YAML or use programmatic API)
   - How filters are applied automatically

2. **Troubleshooting:**
   - See "Troubleshooting" section in [BACKTEST_QUICKSTART.md](BACKTEST_QUICKSTART.md)
   - Debug scripts in `scripts/debug_*.py`
   - Test scripts in `scripts/test_*.py`

## 🔮 Future Plans

**Planned improvements:**

1. **[TODO_LIQUIDITY_FILTER.md](TODO_LIQUIDITY_FILTER.md)** - Liquidity filtering
   - Problem description
   - Implementation plan
   - Database changes needed
   - Timeline estimate

## 📝 Change History

**What's been built:**

1. **[CHANGELOG.md](CHANGELOG.md)** - Complete change history
   - Latest session (2025-01-08): Backtest infrastructure complete
   - Major features added
   - Technical achievements
   - Known issues
   - Test results

## 📊 Performance Metrics

**Understanding metrics:**

All ~40 performance metrics are documented in:
- [BACKTEST_INFRASTRUCTURE.md](BACKTEST_INFRASTRUCTURE.md) - Overview
- [src/factor_investor/backtest/README.md](../src/factor_investor/backtest/README.md) - Detailed list
- `analytics/metrics.py` - Implementation and calculation details

**Metric Categories:**
1. Returns (3 metrics)
2. Risk (5 metrics)
3. Risk-Adjusted (7 metrics)
4. Recovery & Peak (7 metrics)
5. Market-Relative (5 metrics, optional)
6. Up/Down Capture (4 metrics, optional)
7. Trading (4 metrics)
8. Statistical (5 metrics)

## 🧪 Examples & Tests

**Learning by example:**

**Example Scripts** (`scripts/`):
- `run_clean_backtest_2016.py` - Clean baseline (recommended first run)
- `run_magic_formula.py` - Multi-factor strategy
- `example_full_backtest.py` - Multiple examples in one script
- `test_corrupted_filter.py` - Data quality verification
- `debug_position_sizing.py` - Debugging tools

**Test Files** (`tests/`):
- Unit tests for each module
- Integration tests for end-to-end workflows
- Temporal integrity tests (no lookahead bias)

## 🗂️ File Organization

```
factor-investor/
├── docs/                           # Documentation (you are here)
│   ├── DOCUMENTATION_INDEX.md      # This file
│   ├── BACKTEST_QUICKSTART.md      # Quick start guide
│   ├── BACKTEST_INFRASTRUCTURE.md  # Architecture guide
│   ├── TODO_LIQUIDITY_FILTER.md    # Future plans
│   └── CHANGELOG.md                # Change history
│
├── src/factor_investor/
│   ├── backtest/                   # Backtest module
│   │   ├── README.md               # Module documentation
│   │   ├── strategy.py             # Strategy interface
│   │   ├── portfolio.py            # Portfolio tracking
│   │   └── engine.py               # Backtest engine
│   │
│   ├── analytics/                  # Performance analytics
│   │   ├── metrics.py              # Metrics calculation
│   │   └── reports.py              # Report generation
│   │
│   └── universe/                   # Universe & data quality
│       └── corrupted_instruments.py # Filter corrupt data
│
├── config/
│   └── corrupted_instruments.yaml  # Corrupt instruments list
│
├── scripts/                        # Example scripts
│   ├── run_clean_backtest_2016.py
│   ├── run_magic_formula.py
│   ├── example_full_backtest.py
│   ├── test_corrupted_filter.py
│   └── debug_position_sizing.py
│
└── tests/                          # Test files
    └── (various test files)
```

## 💡 Common Tasks

**How do I...**

### Run a backtest?
See [BACKTEST_QUICKSTART.md](BACKTEST_QUICKSTART.md)

### Create a new strategy?
1. Read Strategy interface in [src/factor_investor/backtest/README.md](../src/factor_investor/backtest/README.md)
2. Look at `LongOnlyFactorStrategy` as example
3. Implement `Strategy` ABC

### Add a corrupted instrument?
Edit `config/corrupted_instruments.yaml` or use:
```python
from factor_investor.universe.corrupted_instruments import add_corrupted_instrument
add_corrupted_instrument(12345, "Name", "Issue description")
```

### Understand a metric?
1. Check [BACKTEST_INFRASTRUCTURE.md](BACKTEST_INFRASTRUCTURE.md) for overview
2. Read docstring in `analytics/metrics.py` for details
3. See calculation code in `analytics/metrics.py`

### Debug data quality issues?
1. Run `scripts/debug_position_sizing.py` to identify outliers
2. Add to `config/corrupted_instruments.yaml`
3. Re-run backtest

### Compare strategies?
See example in `scripts/example_full_backtest.py` - `example_compare_strategies()`

## 🔍 Search Tips

**Finding specific information:**

- **Architecture questions:** Start with [BACKTEST_INFRASTRUCTURE.md](BACKTEST_INFRASTRUCTURE.md)
- **How-to questions:** Start with [BACKTEST_QUICKSTART.md](BACKTEST_QUICKSTART.md)
- **Implementation details:** Check module READMEs and docstrings
- **Examples:** Look in `scripts/` folder
- **Changes:** Check [CHANGELOG.md](CHANGELOG.md)

## 📞 Getting Help

1. Check this documentation index
2. Read relevant docs (quickstart, infrastructure, module README)
3. Look at example scripts
4. Check docstrings in code
5. Review test files for usage patterns

## 🚀 Next Steps

After reading documentation:

1. **Run examples:** Start with `run_clean_backtest_2016.py`
2. **Experiment:** Modify strategy parameters, try different factors
3. **Build:** Create your own strategy
4. **Analyze:** Compare multiple strategies
5. **Extend:** Add new metrics, visualizations, or strategy types

Happy backtesting! 📈
