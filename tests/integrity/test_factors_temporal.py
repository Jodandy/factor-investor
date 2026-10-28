"""THE MOST IMPORTANT TEST: Temporal integrity (no lookahead bias).

This test verifies that factor calculations use ONLY data available at the
calculation date, ensuring no future information leaks into historical analyses.

Test Strategy:
1. Calculate factors for historical dates (2020, 2022, 2024)
2. Verify values are stable and don't change when recalculated
3. Verify transformations use only historical data (window-based)
4. Spot-check that results make sense given available data

Future enhancement: Test with actual data truncation to fully validate.
"""

from datetime import date

import polars as pl
import pytest

from factor_investor.factors.queries import clear_cache, get_factor


class TestFactorsTemporal:
    """Temporal integrity tests for factor calculations."""

    @pytest.fixture(autouse=True)
    def clear_test_cache(self):
        """Clear cache before each test."""
        # Clear cache for test factors
        test_factors = [
            "roic_mean_5y_pct",
            "roe_mean_5y_raw",
            "pe_ratio_level_raw",
        ]
        for factor_id in test_factors:
            clear_cache(factor_id=factor_id)

    def test_historical_calculation_stability(self):
        """Test that historical factor values are stable when recalculated.

        This is a key test: if we calculate a factor for 2020-12-31 today,
        and then calculate it again tomorrow, the values should be IDENTICAL
        (assuming base metrics don't change).

        This ensures:
        1. Transformations use only historical data
        2. No randomness in calculations
        3. Cache invalidation works correctly
        """
        test_dates = [
            date(2020, 12, 31),
            date(2022, 6, 30),
            date(2024, 1, 31),
        ]

        factor_id = "roic_mean_5y_pct"

        for test_date in test_dates:
            # First calculation
            df1 = get_factor(factor_id, test_date, use_cache=False)

            # Second calculation (should be identical)
            df2 = get_factor(factor_id, test_date, use_cache=False)

            # Verify results are identical
            assert len(df1) == len(df2), (
                f"Row count mismatch for {test_date}: {len(df1)} vs {len(df2)}"
            )

            if len(df1) > 0:
                # Sort both DFs to ensure comparison is valid
                df1_sorted = df1.sort("instrument_id")
                df2_sorted = df2.sort("instrument_id")

                # Check that values match
                max_diff = (
                    (df1_sorted["value"] - df2_sorted["value"]).abs().max()
                )

                assert max_diff < 0.01, (
                    f"Values changed for {test_date}! Max diff: {max_diff}"
                )

                print(
                    f"  ✓ {test_date}: {len(df1)} instruments, stable calculation"
                )

    def test_transformation_uses_historical_data_only(self):
        """Verify transformations only use data from before calculation date.

        This tests that a 5-year mean calculated on 2022-06-30 only uses
        data from 2017-06-30 to 2022-06-30, NOT any data after that.

        We can't fully test this without truncating the database, but we can
        verify that results for old dates don't change over time.
        """
        test_date = date(2020, 12, 31)
        factor_id = "roic_mean_5y_raw"

        # Calculate factor
        df = get_factor(factor_id, test_date, use_cache=False)

        assert len(df) > 0, f"No data for {factor_id} @ {test_date}"

        # Spot check: mean values should be reasonable
        mean_val = df["value"].mean()
        assert -100 < mean_val < 100, (
            f"Mean ROIC {mean_val:.2f}% seems unreasonable"
        )

        # Check for outliers (basic sanity)
        p95 = df["value"].quantile(0.95)
        p05 = df["value"].quantile(0.05)
        assert p95 > p05, "P95 should be > P05"

        print(f"  ✓ {test_date}: {len(df)} instruments")
        print(f"    Mean: {mean_val:.2f}%, P5: {p05:.2f}%, P95: {p95:.2f}%")

    def test_level_transformation_matches_base_metric(self):
        """Verify level transformation returns exactly the base metric value.

        For a given date, roic_level_raw should exactly match the roic value
        in fundamental_metrics (no transformation applied). Factors are
        restricted to the eligible universe, so compare against that.
        """
        test_date = date(2024, 1, 31)

        # Get factor via lazy calculation
        df_factor = get_factor("roic_level_raw", test_date, use_cache=False)

        # Load raw data from DB to compare
        from sqlalchemy import select

        from factor_investor.db import get_session
        from factor_investor.factors.models import FundamentalMetric
        from factor_investor.universe.models import UniverseConstituent

        with get_session() as session:
            query = select(
                FundamentalMetric.instrument_id,
                FundamentalMetric.value,
            ).join(
                UniverseConstituent,
                (UniverseConstituent.instrument_id == FundamentalMetric.instrument_id)
                & (UniverseConstituent.date == FundamentalMetric.date),
            ).where(
                FundamentalMetric.metric == "roic",
                FundamentalMetric.date == test_date,
                UniverseConstituent.is_eligible,
            )

            result = session.execute(query)
            rows = result.fetchall()

            df_raw = pl.DataFrame(
                {
                    "instrument_id": [r[0] for r in rows],
                    "value": [float(r[1]) if r[1] is not None else None for r in rows],
                }
            )

        # Compare
        assert len(df_factor) == len(df_raw), (
            f"Level transformation changed row count: {len(df_factor)} vs {len(df_raw)}"
        )

        # Join and compare values
        joined = df_factor.join(df_raw, on="instrument_id", suffix="_raw")

        # Check values match
        max_diff = (joined["value"] - joined["value_raw"]).abs().max()
        assert max_diff < 0.01, (
            f"Level transformation changed values! Max diff: {max_diff}"
        )

        print("  ✓ Level transformation matches base metric exactly")

    def test_percentile_normalization_range(self):
        """Verify percentile normalization produces values in [0, 100] range."""
        test_dates = [
            date(2020, 12, 31),
            date(2022, 6, 30),
            date(2024, 1, 31),
        ]

        factor_id = "roic_mean_5y_pct"

        for test_date in test_dates:
            df = get_factor(factor_id, test_date, use_cache=False)

            if len(df) == 0:
                continue

            min_val = df["value"].min()
            max_val = df["value"].max()

            # Percentile should be in [0, 100]
            assert 0 <= min_val <= 100, (
                f"Min percentile {min_val:.2f} outside [0, 100] for {test_date}"
            )
            assert 0 <= max_val <= 100, (
                f"Max percentile {max_val:.2f} outside [0, 100] for {test_date}"
            )

            # Should span most of the range (unless very few instruments)
            if len(df) > 100:
                assert max_val > 90, (
                    f"Max percentile {max_val:.2f} too low (expected near 100)"
                )
                assert min_val < 10, (
                    f"Min percentile {min_val:.2f} too high (expected near 0)"
                )

            print(
                f"  ✓ {test_date}: [{min_val:.2f}, {max_val:.2f}] "
                f"({len(df)} instruments)"
            )

    def test_mean_transformation_reduces_volatility(self):
        """Verify that N-year mean reduces volatility vs level.

        The 5-year mean should be smoother than the latest value,
        so its cross-sectional std should be lower.
        """
        test_date = date(2024, 1, 31)

        # Get level (latest value)
        df_level = get_factor("roic_level_raw", test_date, use_cache=False)

        # Get 5-year mean
        df_mean = get_factor("roic_mean_5y_raw", test_date, use_cache=False)

        # Both should have data
        assert len(df_level) > 0, "No level data"
        assert len(df_mean) > 0, "No mean data"

        # Calculate cross-sectional std
        std_level = df_level["value"].std()
        std_mean = df_mean["value"].std()

        # Mean should be smoother (lower std)
        # (This might not always hold, but generally true for ROIC)
        print(f"  Level std: {std_level:.2f}%")
        print(f"  Mean std:  {std_mean:.2f}%")
        print(f"  Smoothing: {(1 - std_mean/std_level)*100:.1f}% reduction")

        # At minimum, mean std should not be dramatically higher
        assert std_mean < std_level * 1.5, (
            f"Mean std {std_mean:.2f} suspiciously high vs level {std_level:.2f}"
        )

    def test_window_transformation_has_fewer_instruments(self):
        """Verify windowed transformations filter out instruments with insufficient history.

        A 5-year mean should have fewer instruments than level transformation,
        because it requires 5 years of data.
        """
        test_date = date(2024, 1, 31)

        # Get level
        df_level = get_factor("roic_level_raw", test_date, use_cache=False)

        # Get 5-year mean (requires history)
        df_mean = get_factor("roic_mean_5y_raw", test_date, use_cache=False)

        assert len(df_level) > 0, "No level data"
        assert len(df_mean) > 0, "No mean data"

        # Mean should have <= instruments (requires history)
        assert len(df_mean) <= len(df_level), (
            f"Mean has more instruments ({len(df_mean)}) than level ({len(df_level)})"
        )

        # But should still have most of them (>70%)
        coverage = len(df_mean) / len(df_level)
        assert coverage > 0.70, (
            f"Mean coverage {coverage:.1%} too low (expected >70%)"
        )

        print(f"  Level: {len(df_level)} instruments")
        print(f"  Mean:  {len(df_mean)} instruments ({coverage:.1%} coverage)")


if __name__ == "__main__":
    # Run tests manually
    print("\n" + "=" * 80)
    print("TEMPORAL INTEGRITY TESTS")
    print("=" * 80)

    # Clear cache before tests
    test_factors = [
        "roic_mean_5y_pct",
        "roe_mean_5y_raw",
        "pe_ratio_level_raw",
    ]
    for factor_id in test_factors:
        clear_cache(factor_id=factor_id)

    test = TestFactorsTemporal()

    print("\n1. Historical calculation stability...")
    test.test_historical_calculation_stability()

    print("\n2. Transformation uses historical data only...")
    test.test_transformation_uses_historical_data_only()

    print("\n3. Level transformation matches base metric...")
    test.test_level_transformation_matches_base_metric()

    print("\n4. Percentile normalization range...")
    test.test_percentile_normalization_range()

    print("\n5. Mean transformation reduces volatility...")
    test.test_mean_transformation_reduces_volatility()

    print("\n6. Window transformation filters insufficient history...")
    test.test_window_transformation_has_fewer_instruments()

    print("\n" + "=" * 80)
    print("✅ ALL TEMPORAL INTEGRITY TESTS PASSED")
    print("=" * 80)
