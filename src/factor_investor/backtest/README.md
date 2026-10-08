# Backtest Module

Generic backtesting framework for quantitative trading strategies.

## Design Principles

### 1. Separation of Concerns

The framework separates three distinct responsibilities:

**Strategy** (What to trade, When to rebalance)
- Implements `Strategy` ABC
- Returns `TargetPortfolio` with desired holdings
- Defines rebalancing schedule

**Engine** (How to simulate trading)
- Completely strategy-agnostic
- Handles portfolio tracking, rebalancing, costs
- Iterates through time, applies strategy signals

**Analytics** (Performance measurement)
- Calculates ~40 comprehensive metrics
- Works with any `BacktestResult`
- Generates professional reports

### 2. Generic Infrastructure

The engine and analytics work with **ANY** strategy type:
- Factor-based strategies ✅
- Technical strategies ✅
- ML-based strategies ✅
- Market-neutral strategies ✅
- Alternative strategies ✅

Just implement the `Strategy` ABC interface.

### 3. Automatic Metrics

Every backtest automatically calculates ~40 metrics:
```python
result = engine.run(strategy, from_date, to_date)
# result.metrics now has ALL ~40 metrics!
```

No manual calculation. No forgetting important metrics. Consistent across all strategies.

## Module Structure

```
backtest/
├── strategy.py       # Strategy ABC, TargetPortfolio, LongOnlyFactorStrategy
├── portfolio.py      # Portfolio tracking, Trade execution
├── engine.py         # BacktestEngine, BacktestResult
└── README.md         # This file
```

## Strategy Interface

All strategies must implement:

```python
class Strategy(ABC):
    @abstractmethod
    def generate_signals(self, as_of_date, current_holdings) -> TargetPortfolio:
        """Return target portfolio for rebalancing date."""
        pass

    @abstractmethod
    def get_rebalancing_dates(self, from_date, to_date) -> list[date]:
        """Return all rebalancing dates in period."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for reporting."""
        pass
```

Optional properties:
- `description` - Strategy description
- `transaction_cost_bps` - Transaction cost (default: 10 bps)
- `max_position_weight` - Max position size (default: 10%)

## Example: Factor Strategy

```python
from factor_investor.backtest import LongOnlyFactorStrategy

strategy = LongOnlyFactorStrategy(
    name="Magic Formula",
    factors={
        "roic_mean_5y_pct": 0.5,      # 50% quality
        "fcf_yield_level_pct": 0.5,   # 50% value
    },
    num_positions=30,
    rebalancing_frequency="annual",
)
```

## Example: Custom Strategy

```python
from factor_investor.backtest import Strategy, TargetPortfolio

class MyCustomStrategy(Strategy):
    def generate_signals(self, as_of_date, current_holdings):
        # Your custom logic here
        # Load data, calculate signals, rank instruments, etc.

        holdings = pl.DataFrame({
            "instrument_id": [1, 2, 3],
            "weight": [0.4, 0.35, 0.25],
        })

        return TargetPortfolio(holdings=holdings)

    def get_rebalancing_dates(self, from_date, to_date):
        # Your custom schedule
        return [date(2020, 1, 31), date(2021, 1, 31), ...]

    @property
    def name(self):
        return "My Custom Strategy"
```

## Portfolio Class

Tracks holdings, cash, and portfolio value. Handles rebalancing with transaction costs.

**Key Methods:**
- `update_prices()` - Update holdings with current prices, calculate daily return
- `rebalance()` - Rebalance to target weights, execute trades
- `get_holdings_df()` - Get current holdings with values and weights

**Trade Execution:**
- Sells executed first (to free cash)
- Buys executed after (with available cash)
- Transaction costs applied (basis points per trade)
- Tracks all trades for analysis

## BacktestEngine

Orchestrates the simulation:

```python
engine = BacktestEngine()
result = engine.run(
    strategy=strategy,
    from_date=date(2016, 1, 1),
    to_date=date(2024, 12, 31),
    initial_capital=1_000_000,
)
```

**Process:**
1. Get rebalancing dates from strategy
2. Get trading days from database
3. For each day:
   - Update portfolio prices
   - Calculate daily return
   - Rebalance if scheduled
4. Calculate comprehensive metrics
5. Return `BacktestResult`

## BacktestResult

Contains all simulation data + metrics:

```python
result.returns_df         # Daily returns [date, portfolio_return]
result.holdings_history   # Holdings over time [date, instrument_id, weight, value]
result.trades             # All trades [date, instrument_id, action, shares, price, cost]
result.metrics            # PerformanceMetrics (~40 metrics)
result.metadata           # Backtest metadata (initial_capital, final_value, etc.)

# Convenience methods
result.print_report()     # Print comprehensive performance report
```

## Performance Metrics

Calculated automatically for every backtest:

**Returns (3)**
- Total return, CAGR, Annualized return

**Risk (5)**
- Volatility, Downside volatility, Max drawdown (with dates)

**Risk-Adjusted (7)**
- Sharpe, Sortino, Calmar, Omega ratios
- Ulcer index, Pain index, Recovery factor

**Recovery & Peak (7)**
- Current/average distance to ATH
- Time at/near ATH
- Max/average underwater periods
- Lake ratio

**Market-Relative (5, optional)**
- Beta, Alpha, Tracking error, Information ratio, Correlation

**Up/Down Capture (4, optional)**
- Upside/downside capture ratios
- Up/down ratio, Batting average

**Trading (4)**
- Number of trades, Annual turnover
- Average holding period, Win rate

**Statistical (5)**
- Skewness, Kurtosis
- VaR (95%), CVaR (95%), Tail ratio

See `analytics/metrics.py` for implementation details.

## Data Flow

```
Strategy.generate_signals(date)
    ↓
TargetPortfolio {instrument_id, weight}
    ↓
Portfolio.rebalance(target_weights, prices)
    ↓
Trades {instrument_id, action, shares, price, cost}
    ↓
Portfolio state updated (holdings, cash)
    ↓
Daily return calculated
    ↓
Repeat for all trading days
    ↓
BacktestResult {returns_df, trades, holdings_history}
    ↓
calculate_performance_metrics()
    ↓
PerformanceMetrics (~40 metrics)
```

## Transaction Costs

Modeled as basis points per trade:
- Default: 10 bps (0.10%)
- Applied to gross trade value
- Reduces cash for buys, reduces proceeds for sells

Example:
- Buy 100 shares @ 50 SEK = 5,000 SEK
- Cost @ 10 bps = 5 SEK
- Total cash outflow = 5,005 SEK

## Position Sizing

**At Rebalancing:**
- Target weights normalized to sum to 1.0
- Max position weight enforced (default: 10%)
- Equal weight or factor-weighted

**Between Rebalancing:**
- Positions drift naturally with price movements
- No rebalancing until next scheduled date
- Winner positions can grow >10% (normal for long-only)

## Known Limitations

**No Features:**
- Short selling (long-only only)
- Leverage
- Options/derivatives
- Margin
- Slippage modeling (only fixed transaction costs)
- Market impact

**Data Requirements:**
- Needs total return index (dividend-adjusted prices)
- Factors must be available at rebalancing dates
- Missing data causes skipped rebalancing

**Performance:**
- Backtest speed depends on:
  - Number of instruments in universe
  - Rebalancing frequency
  - Factor calculation complexity
- Typical: seconds to minutes for 8 years

## Best Practices

**Strategy Design:**
1. Keep factor weights simple (sum to 1.0)
2. Test single-factor first, then combine
3. Use percentile-normalized factors for comparability
4. Document strategy logic clearly

**Backtesting:**
1. Start with clean data period (check for outliers)
2. Use reasonable time period (8+ years if possible)
3. Check data quality (extreme returns, concentration)
4. Compare vs benchmark
5. Document assumptions

**Analysis:**
1. Look at all metrics, not just returns
2. Check recovery metrics (time underwater)
3. Verify win rate and holding periods
4. Review max drawdown context (dates)
5. Compare multiple strategies consistently

## See Also

- `analytics/` - Performance metrics and reporting
- `../factors/` - Factor calculation and queries
- `../universe/` - Universe and price data
- `docs/BACKTEST_INFRASTRUCTURE.md` - Complete architecture guide
- `docs/BACKTEST_QUICKSTART.md` - Quick start guide
