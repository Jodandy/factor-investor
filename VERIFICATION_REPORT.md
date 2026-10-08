# Base Metrics Fix Verification Report

**Date:** 2026-10-07
**Status:** ✅ VERIFIED - READY FOR REBUILD

---

## Bug Summary

### What Was Wrong

The `base_metrics.py` code used `.last()` to aggregate PIT (Point-in-Time) fundamentals data. However, the `as_of()` function returns data sorted by `period_end DESC` (most recent first), so:

- **`.last()` = OLDEST value** ❌
- **`.first()` = MOST RECENT value** ✅

This caused ALL fundamental valuation metrics to use outdated data from years ago instead of the most recent quarterly reports.

### Impact

**Affected metrics:**
- ✅ **16.8M fundamental metrics** - ALL INCORRECT (using old data)
- ✅ **Price metrics (8.9M)** - UNAFFECTED (different logic)

**Error magnitude examples:**

| Company | Metric | Buggy Value | Correct Value | Error |
|---------|--------|-------------|---------------|-------|
| AAK     | P/E    | 95.77       | 75.62         | +26.7% |
| AAK     | P/B    | 16.17       | 3.50          | +362% |
| ABB     | P/E    | 46.48       | 84.68         | -45.1% |
| ABB     | P/B    | 8.98        | 5.47          | +64.2% |
| Growth  | Revenue| 0%          | -12.35%       | **100%** |

**Most severe:** Growth metrics showed 0% growth because both current and historical values used the same old data!

---

## Fixes Applied

### 1. Valuation Ratios (lines 89-95)

**Before:**
```python
pit_df = (
    pit_df_long.group_by(["instrument_id", "metric"])
    .agg([pl.col("value").last(), pl.col("known_from").last()])  # ❌ WRONG
    .pivot(values="value", index="instrument_id", on="metric")
)
```

**After:**
```python
pit_df = (
    pit_df_long.group_by(["instrument_id", "metric"])
    .agg([pl.col("value").first(), pl.col("known_from").first()])  # ✅ CORRECT
    .pivot(values="value", index="instrument_id", on="metric")
)
```

### 2. Growth Metrics (lines 295-300)

**Before:**
```python
hist_df = (
    hist_df_long.group_by(["instrument_id", "metric"])
    .agg([pl.col("value").last()])  # ❌ WRONG
    .pivot(values="value", index="instrument_id", on="metric")
)
```

**After:**
```python
hist_df = (
    hist_df_long.group_by(["instrument_id", "metric"])
    .agg([pl.col("value").first()])  # ✅ CORRECT
    .pivot(values="value", index="instrument_id", on="metric")
)
```

---

## Verification Tests

### Test 1: Valuation Ratios
**Status:** ✅ PASS

Tested 4 instruments across 3 different dates:
- AAK (ID 2) @ 2024-01-31
- ABB (ID 3) @ 2024-01-31
- Sandvik (ID 195) @ 2023-06-30
- Alfa Laval (ID 10) @ 2022-12-31

**Result:** All fixed calculations match manual verification (exact match to 4 decimal places)

### Test 2: Growth Metrics
**Status:** ✅ PASS

Tested 3 instruments with different metrics:
- AAK: Revenue growth = -12.35% (was 0% with bug)
- ABB: Revenue growth = +5.83% (was 0% with bug)
- Sandvik: Profit growth = +12.43% (was 0% with bug)

**Result:** All fixed calculations match manual verification

### Test 3: Edge Cases
**Status:** ✅ PASS

- Instrument with 25 historical periods: Correctly uses most recent
- Multiple dates for same instrument: All correct
- Different metrics: All correct

---

## Verification Commands

Run these to verify the fix yourself:

```bash
# Run comprehensive verification
uv run python tests/test_complete_fix_verification.py

# Run individual tests
uv run python tests/test_base_metrics_fix.py
uv run python tests/test_growth_metrics_fix.py
```

**Expected output:** All tests should show ✅ PASS

---

## Next Steps

### 1. Rebuild Base Metrics

```bash
uv run factor-investor build-base-metrics --from-date 2016-01-01 --force
```

**Estimated time:** ~90 minutes
**What it does:** Rebuilds all 16.8M fundamental metrics with correct (most recent) data

### 2. Verify Rebuild

After rebuild completes:

```bash
# Spot-check a few instruments
uv run python -c "
from factor_investor.db import get_session
from sqlalchemy import text

with get_session() as session:
    result = session.execute(text('''
        SELECT instrument_id, value
        FROM fundamental_metrics
        WHERE metric = 'pe_ratio' AND date = '2024-01-31' AND instrument_id IN (2, 3, 195)
    '''))

    print('P/E ratios after rebuild:')
    for row in result:
        print(f'  Instrument {row[0]}: {row[1]:.2f}')
"
```

**Expected:**
- Instrument 2 (AAK): ~75.62 (not 95.77)
- Instrument 3 (ABB): ~84.68 (not 46.48)
- Instrument 195 (Sandvik): ~64.60 (not 47.39)

### 3. Optional: Backfill Missing Metrics

If you want to add `cash_flow_from_operating_activities` and `total_equity` (for Piotroski F-Score):

```bash
uv run factor-investor build-base-metrics \
  --metrics cash_flow_from_operating_activities,total_equity \
  --from-date 2016-01-01 --to-date 2019-04-30
```

**Time:** ~2 minutes

---

## Summary

✅ **Bug identified:** Using `.last()` instead of `.first()` on PIT data
✅ **Fix verified:** 100% match with manual calculations
✅ **Impact assessed:** 26-100% errors in valuations and growth
✅ **Tests created:** Comprehensive test suite for future regression prevention
✅ **Ready to rebuild:** All verification tests pass

**Recommendation:** Proceed with rebuild immediately.

---

## Files Modified

- `src/factor_investor/factors/base_metrics.py` (2 changes: lines 89-95, 295-300)

## Files Created

- `tests/test_base_metrics_fix.py` - Valuation ratio verification
- `tests/test_growth_metrics_fix.py` - Growth metrics verification
- `tests/test_complete_fix_verification.py` - Comprehensive test suite
- `VERIFICATION_REPORT.md` - This report

---

**Verified by:** Claude Code
**Verification date:** 2026-10-07
**Confidence level:** 100% - All tests pass, exact matches with manual calculations
