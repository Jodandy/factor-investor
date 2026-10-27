"""Integrity tests for point-in-time fundamentals layer.

These tests verify that the PIT layer correctly prevents lookahead bias
and maintains temporal integrity of financial data.
"""

import random
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from factor_investor.db import get_session
from factor_investor.pit import PITService, as_of


@pytest.mark.integrity
class TestPITTemporal:
    """Temporal integrity tests for PIT fundamentals."""

    def test_no_lookahead_bias_random_dates(self) -> None:
        """Verify no value in as_of(date) has known_from > date.

        This is the MOST CRITICAL test in the entire project.
        If this fails, all downstream analysis is invalid.
        """
        # Sample random dates across the data range
        start_date = date(2020, 1, 1)
        end_date = date(2024, 12, 31)
        num_samples = 50

        random.seed(42)  # Reproducible
        test_dates = []
        for _ in range(num_samples):
            days_offset = random.randint(0, (end_date - start_date).days)
            test_date = start_date + timedelta(days=days_offset)
            test_dates.append(test_date)

        # Test each date
        for test_date in test_dates:
            df = as_of(as_of_date=test_date)

            # Skip if no data
            if len(df) == 0:
                continue

            # Verify ALL known_from <= as_of_date
            max_known = df["known_from"].max()
            assert max_known <= test_date, (
                f"Lookahead bias detected! "
                f"as_of({test_date}) returned data with known_from={max_known}"
            )

    def test_no_lookahead_bias_specific_instrument(self) -> None:
        """Verify temporal integrity for a specific instrument."""
        # Get a test instrument
        with get_session() as session:
            result = session.execute(text("SELECT instrument_id FROM fundamentals_pit LIMIT 1"))
            row = result.fetchone()
            if not row:
                pytest.skip("No data in fundamentals_pit")
            ins_id = row[0]

        # Test multiple dates for this instrument
        test_dates = [
            date(2020, 1, 1),
            date(2021, 6, 30),
            date(2022, 12, 31),
            date(2023, 6, 30),
            date(2024, 1, 1),
        ]

        for test_date in test_dates:
            df = as_of(as_of_date=test_date, instrument_ids=[ins_id])

            if len(df) == 0:
                continue

            # Verify no future data
            violations = df.filter(df["known_from"] > test_date)
            assert len(violations) == 0, (
                f"Found {len(violations)} rows with future known_from dates for "
                f"instrument {ins_id} as of {test_date}"
            )

    def test_future_data_isolation(self) -> None:
        """Verify that future reports don't affect past queries.

        Insert a synthetic report with known_from = D.
        Verify it doesn't appear in as_of(D-1) but DOES appear in as_of(D+1).
        """
        # Get a test instrument
        with get_session() as session:
            result = session.execute(text("SELECT instrument_id FROM fundamentals_pit LIMIT 1"))
            row = result.fetchone()
            if not row:
                pytest.skip("No data in fundamentals_pit")
            ins_id = row[0]

        # Create synthetic report
        test_metric = "test_future_metric"
        test_period_end = date(2023, 12, 31)
        test_known_from = date(2024, 3, 15)
        test_value = 999.99

        with get_session() as session:
            # Insert synthetic report
            session.execute(
                text("""
                    INSERT INTO fundamentals_pit
                    (instrument_id, metric, period_end, period_type, value, known_from)
                    VALUES (:ins_id, :metric, :period_end, 'year', :value, :known_from)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "ins_id": ins_id,
                    "metric": test_metric,
                    "period_end": test_period_end,
                    "value": test_value,
                    "known_from": test_known_from,
                },
            )
            session.commit()

        try:
            # Query BEFORE known_from: should NOT appear
            df_before = as_of(
                as_of_date=test_known_from - timedelta(days=1),
                instrument_ids=[ins_id],
                metrics=[test_metric],
            )
            assert len(df_before.filter(df_before["metric"] == test_metric)) == 0, (
                "Future report appeared in query before its known_from date!"
            )

            # Query AFTER known_from: SHOULD appear
            df_after = as_of(
                as_of_date=test_known_from + timedelta(days=1),
                instrument_ids=[ins_id],
                metrics=[test_metric],
            )
            assert len(df_after.filter(df_after["metric"] == test_metric)) > 0, (
                "Report did not appear in query after its known_from date"
            )

        finally:
            # Cleanup: remove synthetic report
            with get_session() as session:
                session.execute(
                    text("DELETE FROM fundamentals_pit WHERE metric = :metric"),
                    {"metric": test_metric},
                )
                session.commit()

    def test_known_from_calculation_logic(self) -> None:
        """Verify known_from dates are calculated correctly."""
        pit_service = PITService()

        # Test with actual publication date
        actual_pub_date = date(2024, 2, 15)
        period_end = date(2023, 12, 31)

        known, is_fallback = pit_service.calculate_known_from(
            report_date=actual_pub_date,
            period_end=period_end,
            period_type="year",
        )

        # Should use actual date + buffer (1 day)
        assert known == date(2024, 2, 16), f"Expected 2024-02-16, got {known}"
        assert not is_fallback, "Should use actual publication date, not fallback"

        # Test with missing publication date (fallback)
        known, is_fallback = pit_service.calculate_known_from(
            report_date=None, period_end=period_end, period_type="year"
        )

        # Should use fallback: period_end + 90 days (annual) + 1 day buffer = +91 days
        expected = date(2024, 3, 31)  # 2023-12-31 + 91 days
        assert known == expected, f"Expected {expected}, got {known}"
        assert is_fallback, "Should use fallback when publication date missing"

        # Test with Börsdata's "missing" indicator (1899-12-30)
        known, is_fallback = pit_service.calculate_known_from(
            report_date=date(1899, 12, 30),
            period_end=period_end,
            period_type="year",
        )

        # Should treat as missing and use fallback
        assert known == expected, "Should use fallback for 1899 dates"
        assert is_fallback, "Should use fallback for 1899-12-30 date"
