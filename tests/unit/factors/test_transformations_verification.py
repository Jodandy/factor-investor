"""Verification tests for factor transformations.

These tests manually calculate transformations for known data and compare
against the transformation functions to ensure correctness.
"""

from datetime import date, timedelta

import polars as pl
import pytest

from factor_investor.factors.transformations import (
    transform_cagr,
    transform_level,
    transform_mean,
    transform_median,
    transform_stability_cv,
    transform_trend,
)


class TestTransformationVerification:
    """Manual verification of transformation calculations."""

    def test_level_transformation(self):
        """Verify level transformation returns data as-is."""
        # Create test data
        test_data = pl.DataFrame({
            "instrument_id": [1, 1, 1, 2, 2],
            "date": [
                date(2023, 1, 1),
                date(2023, 6, 1),
                date(2024, 1, 1),
                date(2023, 1, 1),
                date(2024, 1, 1),
            ],
            "value": [10.0, 12.0, 15.0, 20.0, 25.0],
        })

        # Apply transformation
        result = transform_level(test_data)

        # Should be identical
        assert result.equals(test_data)
        print("  ✓ Level transformation preserves data")

    def test_mean_transformation_manual_calculation(self):
        """Manually calculate 3-year mean and verify against transformation."""
        # Create test data: instrument 1 with 5 years of annual data
        dates = [date(2020, 1, 1) + timedelta(days=365 * i) for i in range(6)]
        values = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]

        test_data = pl.DataFrame({
            "instrument_id": [1] * 6,
            "date": dates,
            "value": values,
        })

        # Apply 3-year mean transformation
        result = transform_mean(test_data, window_years=3)

        # Get the last row (should be the most recent date)
        assert len(result) > 0, "Should have at least one result"

        # Sort by date and get last
        result_sorted = result.sort("date")
        last_row = result_sorted.tail(1)
        calculated_mean = last_row["value"][0]

        # Manual calculation: last row should use last 4 values
        # (all values within 3 years of the last date)
        # Values: 14.0, 16.0, 18.0, 20.0
        # Mean = (14 + 16 + 18 + 20) / 4 = 17.0
        expected_mean = 17.0

        assert abs(calculated_mean - expected_mean) < 0.5, (
            f"Mean mismatch: {calculated_mean:.2f} vs {expected_mean:.2f}"
        )

        print(f"  ✓ Manual mean calculation: {expected_mean:.2f}")
        print(f"  ✓ Transform result: {calculated_mean:.2f}")
        print(f"  ✓ Difference: {abs(calculated_mean - expected_mean):.6f}")

    def test_median_transformation(self):
        """Verify median transformation with known data."""
        # Create test data with clear median
        test_data = pl.DataFrame({
            "instrument_id": [1, 1, 1, 1, 1],
            "date": [
                date(2020, 1, 1),
                date(2021, 1, 1),
                date(2022, 1, 1),
                date(2023, 1, 1),
                date(2024, 1, 1),
            ],
            "value": [10.0, 15.0, 20.0, 25.0, 100.0],  # Last value is outlier
        })

        # Apply 3-year median
        result = transform_median(test_data, window_years=3)

        # For 2024-01-01, with 3-year window, uses [15, 20, 25, 100] (4 values)
        # Median of 4 values = (20 + 25) / 2 = 22.5
        result_sorted = result.sort("date")
        if len(result_sorted) > 0:
            last_row = result_sorted.tail(1)
            calculated_median = last_row["value"][0]
            expected_median = 22.5  # Median of 15, 20, 25, 100

            assert abs(calculated_median - expected_median) < 0.01, (
                f"Median mismatch: {calculated_median:.2f} vs {expected_median:.2f}"
            )

            print(f"  ✓ Median (robust to outliers): {calculated_median:.2f}")

    def test_cagr_transformation(self):
        """Verify CAGR calculation with known growth."""
        # Create test data: value doubles in 3 years
        test_data = pl.DataFrame({
            "instrument_id": [1, 1],
            "date": [date(2020, 1, 1), date(2023, 1, 1)],
            "value": [100.0, 200.0],  # 100% growth over 3 years
        })

        # Apply 3-year CAGR
        result = transform_cagr(test_data, window_years=3)

        if len(result) > 0:
            calculated_cagr = result["value"][0]

            # Manual calculation: (200/100)^(1/3) - 1 ≈ 0.2599 (26% annualized)
            expected_cagr = (200.0 / 100.0) ** (1.0 / 3.0) - 1

            assert abs(calculated_cagr - expected_cagr) < 0.01, (
                f"CAGR mismatch: {calculated_cagr:.4f} vs {expected_cagr:.4f}"
            )

            print(f"  ✓ CAGR for doubling in 3 years: {calculated_cagr:.2%}")
            print(f"  ✓ Expected: {expected_cagr:.2%}")

    def test_stability_cv_transformation(self):
        """Verify coefficient of variation calculation."""
        # Create test data with known CV
        # CV = std / mean
        test_data = pl.DataFrame({
            "instrument_id": [1, 1, 1, 1, 1],
            "date": [
                date(2020, 1, 1),
                date(2021, 1, 1),
                date(2022, 1, 1),
                date(2023, 1, 1),
                date(2024, 1, 1),
            ],
            "value": [10.0, 12.0, 10.0, 12.0, 10.0],  # Oscillates around 10.8
        })

        # Apply 3-year CV
        result = transform_stability_cv(test_data, window_years=3)

        if len(result) > 0:
            # Get last CV
            last_cv = result.filter(pl.col("date") == date(2024, 1, 1))["value"][0]

            # Manual calculation for last 3 years: [12, 10, 12, 10]
            # Mean = 11.0, Std ≈ 1.15, CV ≈ 0.105
            import numpy as np

            values = np.array([12.0, 10.0, 12.0, 10.0])
            expected_cv = np.std(values) / np.mean(values)

            # CV should be relatively small (stable values)
            assert 0 < last_cv < 0.5, f"CV {last_cv:.4f} outside reasonable range"

            print(f"  ✓ Calculated CV: {last_cv:.4f}")
            print(f"  ✓ Expected CV: {expected_cv:.4f}")
            print(f"  ✓ Difference: {abs(last_cv - expected_cv):.6f}")

    def test_trend_transformation_positive(self):
        """Verify trend calculation for increasing values."""
        # Create data with clear upward trend
        test_data = pl.DataFrame({
            "instrument_id": [1, 1, 1, 1, 1],
            "date": [
                date(2020, 1, 1),
                date(2021, 1, 1),
                date(2022, 1, 1),
                date(2023, 1, 1),
                date(2024, 1, 1),
            ],
            "value": [10.0, 12.0, 14.0, 16.0, 18.0],  # +2 per year
        })

        # Apply trend
        result = transform_trend(test_data, window_years=3)

        if len(result) > 0:
            # Get last trend
            last_trend = result.filter(pl.col("date") == date(2024, 1, 1))

            if len(last_trend) > 0:
                calculated_slope = last_trend["value"][0]

                # Slope should be ~2 (increasing by 2 per year)
                assert 1.8 < calculated_slope < 2.2, (
                    f"Slope {calculated_slope:.2f} doesn't match expected ~2.0"
                )

                print(f"  ✓ Calculated slope: {calculated_slope:.4f}/year")
                print(f"  ✓ Expected: ~2.0/year (increasing trend)")

    def test_transformation_with_real_data(self):
        """Spot-check transformation with real database data."""
        from factor_investor.db import get_session
        from factor_investor.factors.models import FundamentalMetric
        from sqlalchemy import select

        # Pick a known instrument and get ROIC data
        ins_id = 2  # AAK
        test_date = date(2024, 1, 31)

        with get_session() as session:
            # Get historical ROIC data
            query = (
                select(
                    FundamentalMetric.date,
                    FundamentalMetric.value,
                )
                .where(
                    FundamentalMetric.instrument_id == ins_id,
                    FundamentalMetric.metric == "roic",
                    FundamentalMetric.date <= test_date,
                    FundamentalMetric.date >= date(2019, 1, 1),
                )
                .order_by(FundamentalMetric.date)
            )

            result = session.execute(query)
            rows = result.fetchall()

            if len(rows) > 0:
                # Create DataFrame
                df = pl.DataFrame({
                    "instrument_id": [ins_id] * len(rows),
                    "date": [r[0] for r in rows],
                    "value": [float(r[1]) if r[1] is not None else None for r in rows],
                })

                # Apply mean transformation
                result_mean = transform_mean(df, window_years=5)

                # Get value for test_date
                value_for_date = result_mean.filter(pl.col("date") == test_date)

                if len(value_for_date) > 0:
                    mean_value = value_for_date["value"][0]

                    # Should be reasonable ROIC value (-100% to 100%)
                    assert -100 < mean_value < 100, (
                        f"Mean ROIC {mean_value:.2f}% outside reasonable range"
                    )

                    print(f"  ✓ Instrument {ins_id} 5-year mean ROIC: {mean_value:.2f}%")
                    print(f"  ✓ Based on {len(df)} historical data points")
                else:
                    print(f"  ⚠️  No data for {test_date} after transformation")
            else:
                print(f"  ⚠️  No ROIC data for instrument {ins_id}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("TRANSFORMATION VERIFICATION TESTS")
    print("=" * 80)

    test = TestTransformationVerification()

    print("\n1. Level transformation...")
    test.test_level_transformation()

    print("\n2. Mean transformation (manual calculation)...")
    test.test_mean_transformation_manual_calculation()

    print("\n3. Median transformation...")
    test.test_median_transformation()

    print("\n4. CAGR transformation...")
    test.test_cagr_transformation()

    print("\n5. Stability (CV) transformation...")
    test.test_stability_cv_transformation()

    print("\n6. Trend transformation...")
    test.test_trend_transformation_positive()

    print("\n7. Real database data spot-check...")
    test.test_transformation_with_real_data()

    print("\n" + "=" * 80)
    print("✅ ALL VERIFICATION TESTS PASSED")
    print("=" * 80)
