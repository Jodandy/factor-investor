# TODO: Liquidity/Volume Filter

## Problem

Currently we have no liquidity filter, which means:
- Strategies can select ultra-low liquidity stocks
- Impossible to actually trade in reality (100k SEK order would move the price 50%)
- Backtest returns are unrealistic

## Example Issue

Some instruments have:
- Daily volume: 1,000 SEK (extremely illiquid!)
- Chart looks great: +500% return
- But in reality: Can't execute trades without massive slippage

## Solution

Add minimum daily liquidity filter:
- **Minimum daily volume: 100,000 SEK** (default)
- Calculate as: `avg_volume_30d * price`
- Applied in strategy.generate_signals() before ranking

## Implementation Plan

### 1. Add Volume Data to Database

**Migration:** Add volume column to `total_returns`
```sql
ALTER TABLE total_returns
ADD COLUMN volume BIGINT,  -- Trading volume in shares
ADD COLUMN volume_sek NUMERIC(24, 2);  -- Volume in SEK (volume * close_price)
```

**Update universe pipeline** to fetch volume from Borsdata API

### 2. Calculate Liquidity Metrics

**New base metric:** `liquidity_30d` in `price_metrics`
```python
def calculate_liquidity_metrics(session, rebal_date, instrument_ids):
    # Get last 30 days of volume
    volumes = get_volumes(rebal_date - 30d, rebal_date)

    # Calculate average daily volume in SEK
    avg_volume_sek = (volumes * prices).mean()

    return {
        "metric": "liquidity_30d",
        "value": avg_volume_sek,
    }
```

### 3. Add Filter to Strategy

**Update LongOnlyFactorStrategy:**
```python
def __init__(self, min_liquidity_sek: float = 100_000, ...):
    self.min_liquidity_sek = min_liquidity_sek

def generate_signals(self, as_of_date, current_holdings):
    # ... existing factor combination ...

    # Filter by liquidity
    if self.min_liquidity_sek is not None:
        liquidity_df = get_factor("liquidity_30d_level_raw", as_of_date)
        liquid_instruments = liquidity_df.filter(
            pl.col("value") >= self.min_liquidity_sek
        )["instrument_id"].to_list()

        combined = combined.filter(
            pl.col("instrument_id").is_in(liquid_instruments)
        )
```

### 4. Testing

**Verify:**
- Filters out illiquid stocks correctly
- Backtest returns become more realistic
- No 1000%+ outliers from micro-caps

**Spot check:**
- Get list of filtered instruments
- Manually verify on Börsdata/Avanza that they are indeed illiquid

## Expected Impact

**Before filter:**
- Magic Formula: 2,748% return (unrealistic)
- Driven by illiquid micro-caps with +689x returns

**After filter:**
- More realistic returns (~200-300% over 4 years?)
- Only tradeable instruments
- Positions can actually be filled in reality

## Priority

**HIGH** - Critical for realistic backtests

Without liquidity filter, backtest results are fantasy numbers that can't be replicated in real trading.

## Dependencies

1. Add volume to universe pipeline (Fas 2 update)
2. Add volume column to total_returns table (migration)
3. Add liquidity_30d to price_metrics calculation
4. Implement filter in strategy

## Timeline Estimate

- **Volume in database:** 2-3 days (need to update universe pipeline)
- **Liquidity metric:** 1 day (similar to existing price metrics)
- **Filter implementation:** 1 hour (trivial once data exists)
- **Testing:** 1 day

**Total: ~4-5 days of work**

## Alternative: Manual Blacklist (Temporary)

While waiting for volume data:
- Manually identify illiquid stocks
- Add to `corrupted_instruments.yaml`
- Mark as "illiquid" rather than "corrupted"

Example:
```yaml
corrupted_instruments:
  - instrument_id: 20346
    name: "Example Illiquid Co"
    issue: "Extremely low liquidity - avg daily volume <100k SEK"
    notes: "Manual identification - replace with automatic filter when volume data available"
```
