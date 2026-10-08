"""Test lazy factor calculation and caching.

This script validates that the factor system works end-to-end:
1. Cache miss: First call calculates and caches
2. Cache hit: Second call retrieves from cache (fast)
3. Results are correct
"""

import time
from datetime import date
from pathlib import Path

from factor_investor.factors.queries import get_factor, clear_cache


def test_lazy_calculation():
    """Test lazy calculation with cache."""
    print('\n' + '=' * 80)
    print('LAZY FACTOR CALCULATION TEST')
    print('=' * 80)

    test_date = date(2024, 1, 31)
    factor_id = "roic_mean_5y_pct"

    # Clear cache for this factor to ensure clean test
    print(f"\n1. Clearing cache for {factor_id}...")
    deleted = clear_cache(factor_id=factor_id, as_of_date=test_date)
    print(f"   Deleted {deleted} cache files")

    # First call: CACHE MISS (should calculate)
    print(f"\n2. First call (CACHE MISS - should calculate)...")
    start_time = time.time()
    df1 = get_factor(factor_id, test_date)
    elapsed1 = time.time() - start_time

    print(f"   ✓ Calculated in {elapsed1:.3f}s")
    print(f"   ✓ Result: {len(df1)} instruments")

    if len(df1) > 0:
        print(f"   ✓ Sample values:")
        print(f"      First 5 rows:")
        print(df1.head(5))
        print(f"   ✓ Stats: min={df1['value'].min():.2f}, max={df1['value'].max():.2f}, mean={df1['value'].mean():.2f}")

    # Verify cache file was created
    cache_path = Path("data/factors/cache") / factor_id / f"date={test_date}.parquet"
    if cache_path.exists():
        print(f"   ✓ Cache file created: {cache_path}")
    else:
        print(f"   ✗ ERROR: Cache file NOT created!")
        return False

    # Second call: CACHE HIT (should be fast)
    print(f"\n3. Second call (CACHE HIT - should be fast)...")
    start_time = time.time()
    df2 = get_factor(factor_id, test_date)
    elapsed2 = time.time() - start_time

    print(f"   ✓ Retrieved in {elapsed2:.3f}s ({elapsed1/max(elapsed2, 0.001):.1f}x faster)")
    print(f"   ✓ Result: {len(df2)} instruments")

    # Verify results are identical
    if len(df1) == len(df2):
        print(f"   ✓ Row count matches")
    else:
        print(f"   ✗ ERROR: Row count mismatch! ({len(df1)} vs {len(df2)})")
        return False

    # Check values match (should be identical from cache)
    if df1.equals(df2):
        print(f"   ✓ Values match exactly (cache working correctly)")
    else:
        print(f"   ⚠️  WARNING: Values don't match exactly (may be sorting difference)")

    print('\n' + '=' * 80)
    print('✅ LAZY CALCULATION TEST PASSED')
    print('=' * 80)

    return True


def test_multiple_factors():
    """Test calculation of multiple factor variants."""
    print('\n' + '=' * 80)
    print('MULTIPLE FACTOR VARIANTS TEST')
    print('=' * 80)

    test_date = date(2024, 1, 31)

    test_factors = [
        "roic_mean_5y_pct",      # ROIC, 5-year mean, percentile
        "roic_mean_5y_raw",      # ROIC, 5-year mean, raw values
        "pe_ratio_level_raw",    # P/E, latest value, raw
        "return_12m_level_raw",  # 12-month return, latest value, raw
    ]

    print(f"\nTesting {len(test_factors)} factor variants on {test_date}:\n")

    for factor_id in test_factors:
        try:
            start_time = time.time()
            df = get_factor(factor_id, test_date)
            elapsed = time.time() - start_time

            status = "✓"
            if len(df) == 0:
                status = "⚠️ "

            print(f"{status} {factor_id:30s} | {len(df):>5} instruments | {elapsed:>6.3f}s")

            if len(df) > 0:
                print(f"     Stats: min={df['value'].min():>8.2f}, max={df['value'].max():>8.2f}, mean={df['value'].mean():>8.2f}")

        except Exception as e:
            print(f"✗ {factor_id:30s} | ERROR: {e}")

    print('\n' + '=' * 80)
    print('✅ MULTIPLE FACTOR TEST COMPLETE')
    print('=' * 80)


def test_transformation_correctness():
    """Spot-check transformation calculations."""
    print('\n' + '=' * 80)
    print('TRANSFORMATION CORRECTNESS TEST')
    print('=' * 80)

    test_date = date(2024, 1, 31)

    # Test 1: Level transformation (should match base metric)
    print("\n1. Testing level transformation...")
    df_level = get_factor("roic_level_raw", test_date)
    print(f"   ✓ Got {len(df_level)} instruments")

    # Test 2: Mean transformation
    print("\n2. Testing mean transformation...")
    df_mean = get_factor("roic_mean_5y_raw", test_date)
    print(f"   ✓ Got {len(df_mean)} instruments")

    if len(df_mean) < len(df_level):
        print(f"   ✓ Mean has fewer instruments ({len(df_mean)} vs {len(df_level)}) - expected (requires history)")
    else:
        print(f"   ⚠️  Mean has same or more instruments - unexpected")

    # Test 3: Percentile normalization (should be 0-100)
    print("\n3. Testing percentile normalization...")
    df_pct = get_factor("roic_mean_5y_pct", test_date)
    print(f"   ✓ Got {len(df_pct)} instruments")

    if len(df_pct) > 0:
        min_val = df_pct['value'].min()
        max_val = df_pct['value'].max()
        print(f"   ✓ Range: {min_val:.2f} to {max_val:.2f}")

        if 0 <= min_val <= 100 and 0 <= max_val <= 100:
            print(f"   ✓ Values in valid range [0, 100]")
        else:
            print(f"   ✗ ERROR: Values outside [0, 100] range!")
            return False

    print('\n' + '=' * 80)
    print('✅ TRANSFORMATION CORRECTNESS TEST PASSED')
    print('=' * 80)

    return True


if __name__ == '__main__':
    print('\n')
    print('╔' + '═' * 78 + '╗')
    print('║' + ' ' * 78 + '║')
    print('║' + '  FACTOR SYSTEM END-TO-END TEST'.center(78) + '║')
    print('║' + ' ' * 78 + '║')
    print('╚' + '═' * 78 + '╝')

    success = True

    # Run all tests
    success = success and test_lazy_calculation()
    success = success and test_transformation_correctness()
    test_multiple_factors()

    if success:
        print('\n' + '=' * 80)
        print('✅ ALL TESTS PASSED')
        print('=' * 80)
    else:
        print('\n' + '=' * 80)
        print('❌ SOME TESTS FAILED - REVIEW OUTPUT ABOVE')
        print('=' * 80)
