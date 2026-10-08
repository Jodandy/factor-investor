# Data Sync Guide

Quick reference for keeping factor-investor data up to date.

---

## Initial Setup (One-Time)

Run these commands **once** to build the full historical dataset:

```bash
# 1. Sync all instruments metadata (~1 minute)
uv run factor-investor sync-instruments

# 2. Sync all price data (~5-10 minutes)
uv run factor-investor sync-prices

# 3. Sync all reports (fundamentals) (~30-60 minutes)
uv run factor-investor sync-reports

# 4. Build point-in-time fundamentals (~10 minutes)
uv run factor-investor build-pit

# 5. Build total returns with dividends (~1.5 hours - LONG!)
uv run factor-investor build-returns

# 6. Build investable universe (~15-20 minutes)
uv run factor-investor build-universe --from-date 2016-01-01

# 7. Build base metrics (factors) (~90 minutes)
uv run factor-investor build-base-metrics --from-date 2016-01-01
```

**Total time:** ~4-5 hours (one-time setup)

> **💡 Tip:** For adding individual factors later without rebuilding everything, see [Incremental Factor Sync](./incremental-factor-sync.md)

---

## Regular Updates (Weekly/Monthly)

Run these to stay current with new data:

```bash
# 1. Update instruments (new listings) - WEEKLY
uv run factor-investor sync-instruments

# 2. Update prices (new trading days) - WEEKLY
uv run factor-investor sync-prices

# 3. Update reports (new quarterly/annual reports) - MONTHLY
uv run factor-investor sync-reports

# 4. Rebuild PIT fundamentals (incremental) - MONTHLY
uv run factor-investor build-pit

# 5. Update total returns (only new data) - MONTHLY
uv run factor-investor build-returns

# 6. Update universe (new month-ends) - MONTHLY
uv run factor-investor build-universe --from-date $(date -v-3m +%Y-%m-%d)

# 7. Update base metrics (new month-ends) - MONTHLY
uv run factor-investor build-base-metrics --from-date $(date -v-3m +%Y-%m-%d)
```

**Total time:** ~20-40 minutes (incremental updates)

> **⚡ Fast incremental updates:** Use `--metrics` to update specific factors only. See [Incremental Factor Sync](./incremental-factor-sync.md)

---

## Command Reference

### Sync Commands (fetch data from Börsdata API)

| Command | What It Does | Frequency | Time |
|---------|-------------|-----------|------|
| `sync-instruments` | Fetch all instruments metadata (names, tickers, sectors, countries) | Weekly | ~1 min |
| `sync-prices` | Fetch daily OHLCV price data for all instruments | Weekly | ~5-10 min |
| `sync-reports` | Fetch quarterly & annual financial reports (balance sheet, income statement, cash flow) | Monthly | ~30-60 min |

**Flags:**
- `--force`: Re-fetch all data (ignores existing data)
- `--verbose` / `-v`: Show detailed logging

**Examples:**
```bash
# Update instruments with verbose logging
uv run factor-investor sync-instruments -v

# Force re-sync all prices (full rebuild)
uv run factor-investor sync-prices --force

# Update only reports from last 3 months
uv run factor-investor sync-reports --from-date 2024-07-01
```

---

### Build Commands (process data into derived tables)

| Command | What It Does | Frequency | Time | Dependencies |
|---------|-------------|-----------|------|--------------|
| `build-pit` | Build point-in-time fundamentals (temporal integrity, no lookahead) | After sync-reports | ~10 min | sync-reports |
| `build-returns` | Calculate total return indices with reinvested dividends | After sync-prices | ~1.5h initial, ~5min incremental | sync-prices, sync-reports |
| `build-universe` | Build monthly investable universe with eligibility filters | After build-returns, build-pit | ~15-20 min | build-pit, build-returns |
| `build-base-metrics` | Build fundamental + price base metrics (monthly snapshots) | After build-pit, build-returns | ~90 min initial, ~5min incremental | build-pit, build-returns |

**Flags:**
- `--force`: Delete existing data and rebuild from scratch
- `--from-date YYYY-MM-DD`: Build only from this date forward
- `--to-date YYYY-MM-DD`: Build only up to this date
- `--metrics METRIC1,METRIC2`: Build only specific metrics (incremental sync)
- `--verbose` / `-v`: Show detailed logging

**Examples:**
```bash
# Rebuild PIT from scratch (if you suspect data issues)
uv run factor-investor build-pit --force

# Update total returns incrementally (fast - only new instruments)
uv run factor-investor build-returns

# Build universe for last 3 months only
uv run factor-investor build-universe --from-date 2024-07-01

# Build all base metrics (initial)
uv run factor-investor build-base-metrics --from-date 2016-01-01

# Add only specific metrics (incremental - FAST!)
uv run factor-investor build-base-metrics --metrics pe_ratio,pb_ratio

# Backfill missing metrics for early dates
uv run factor-investor build-base-metrics \
  --metrics cash_flow_from_operating_activities \
  --from-date 2016-01-01 --to-date 2019-04-30
```

> **⚡ For more on incremental factor syncs, see [Incremental Factor Sync](./incremental-factor-sync.md)**

---

## Data Flow

```
Börsdata API
    ↓
┌───────────────────────────────────────────┐
│ RAW DATA (sync commands)                  │
├───────────────────────────────────────────┤
│ instruments  ← sync-instruments           │
│ stock_prices ← sync-prices                │
│ reports_*    ← sync-reports                │
└───────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────┐
│ DERIVED DATA (build commands)             │
├───────────────────────────────────────────┤
│ fundamentals_pit ← build-pit              │
│ dividends        ← build-returns          │
│ total_returns    ← build-returns          │
│ universe_*       ← build-universe         │
└───────────────────────────────────────────┘
    ↓
Ready for factor calculation & backtesting!
```

---

## Quick Start (After Fresh Clone)

If you're setting up on a new machine or after a fresh database:

```bash
# 1. Start database
docker-compose up -d db

# 2. Run migrations
uv run alembic upgrade head

# 3. Run all sync commands (in order)
uv run factor-investor sync-instruments
uv run factor-investor sync-prices
uv run factor-investor sync-reports

# 4. Run all build commands (in order)
uv run factor-investor build-pit
uv run factor-investor build-returns
uv run factor-investor build-universe --from-date 2016-01-01

# Done! (~2-3 hours total)
```

---

## Troubleshooting

### "No data found" errors

**Problem:** Commands fail because they depend on earlier steps.

**Solution:** Ensure you run commands in order:
1. sync-instruments (first!)
2. sync-prices
3. sync-reports
4. build-pit
5. build-returns
6. build-universe

### Slow performance

**Problem:** `build-returns` or `build-universe` takes very long.

**Solutions:**
- Use incremental updates (don't use `--force` unless needed)
- `build-returns` initial run: ~1.5h (one-time), incremental: ~5 min
- `build-universe`: Only build recent months with `--from-date`

### Out of memory errors

**Problem:** Docker container runs out of RAM during large builds.

**Solution:** Increase Docker memory limit:
```bash
# In Docker Desktop: Settings → Resources → Memory → 8GB+
```

### API rate limits

**Problem:** Börsdata API returns 429 Too Many Requests.

**Solution:** Sync commands automatically handle rate limits with exponential backoff. Just let them run - they'll retry automatically.

---

## Data Freshness

Börsdata updates:
- **Prices:** Daily (after market close)
- **Reports:** As companies publish (quarterly/annual)
- **Instruments:** As new companies list or existing ones delist

**Recommended sync schedule:**
- **Daily:** Not needed (overkill, API limits)
- **Weekly:** sync-instruments, sync-prices (stay current with trading)
- **Monthly:** Full sync chain (catch new reports, rebuild universe)
- **Quarterly:** Good enough for research (reports are quarterly anyway)

---

## Example: Monthly Update Workflow

```bash
# First Monday of each month at 9 AM:

# 1. Sync latest data from Börsdata (~40 min)
uv run factor-investor sync-instruments
uv run factor-investor sync-prices
uv run factor-investor sync-reports

# 2. Rebuild derived data (~25 min)
uv run factor-investor build-pit
uv run factor-investor build-returns  # Incremental, only new data
uv run factor-investor build-universe --from-date $(date -v-3m +%Y-%m-%d)

# 3. Verify in pgAdmin
# - Check universe_constituents has latest month-end
# - Check total_returns is up to date
# - Check fundamentals_pit has recent reports

# Total time: ~1 hour
# Data is now current!
```

---

## Next Steps

After data is synced and built:
- **Fas 4:** Calculate factors (value, quality, momentum, etc.)
- **Fas 5:** Build benchmark indices
- **Fas 6:** Backtest strategies on historical data
- **Fas 7:** Walk-forward optimization
- **Fas 8:** Generate performance reports

See `docs/WORK_ORDER.md` for the full roadmap.
