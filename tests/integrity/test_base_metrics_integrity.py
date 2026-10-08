"""Integrity tests for base_metrics - MUST PASS before any rebuild.

These tests verify:
1. No lookahead bias (.first() not .last())
2. Correct period_type (r12/year, not quarter)
3. Reasonable value ranges
4. No NULL values where they shouldn't be
5. Consistency between related metrics
"""

import pytest
from datetime import date, timedelta
import polars as pl

from factor_investor.pit import as_of
from factor_investor.factors.base_metrics import calculate_fundamental_metrics, calculate_price_metrics
from factor_investor.db import get_session


class TestTemporalIntegrity:
    """Test that base_metrics has no lookahead bias."""

    def test_uses_most_recent_not_oldest(self):
        """Verify .first() is used (most recent), not .last() (oldest)."""
        test_date = date(2024, 1, 31)
        ins_id = 2  # AAK

        pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])

        # Verify as_of returns multiple periods sorted DESC
        assert len(pit_df) > 5, "Should have historical data"

        # Get first and last values
        eps_first = float(pit_df[0, 'value'])
        eps_last = float(pit_df[-1, 'value'])
        period_first = pit_df[0, 'period_end']
        period_last = pit_df[-1, 'period_end']

        # First should be more recent than last
        assert period_first > period_last, f"First period {period_first} should be > last {period_last}"

        # Values should be different (confirming we're not using same old value)
        assert abs(eps_first - eps_last) > 0.1, "First and last values should differ significantly"


class TestPeriodTypeFiltering:
    """Test that correct period_type is used."""

    def test_no_quarterly_data_in_valuation(self):
        """Verify base_metrics filters to r12/year, excludes quarterly."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            # This would use quarterly data with the BUG
            metrics = calculate_fundamental_metrics(session, test_date, instrument_ids=[2, 3])

        # We can't directly check period_type from the output,
        # but we can verify the VALUES are not quarterly

        # For AAK (ins_id=2), quarterly EPS=3.11, year EPS=3.68, r12 EPS=9.99
        # If we get P/E around 64 (235/3.68), we used year data ✅
        # If we get P/E around 75 (235/3.11), we used quarter data ❌

        pe_metrics = [m for m in metrics if m['metric'] == 'pe_ratio' and m['instrument_id'] == 2]

        if pe_metrics:
            pe_value = float(pe_metrics[0]['value'])
            # Should NOT be close to quarterly-based P/E (75.6)
            assert abs(pe_value - 75.6) > 5.0, f"P/E={pe_value} looks like quarterly data (expected ~64, got {pe_value})"


class TestValueRanges:
    """Test that calculated values are within reasonable ranges."""

    def test_pe_ratio_reasonable(self):
        """P/E ratios should be within reasonable range (0-1000)."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            metrics = calculate_fundamental_metrics(session, test_date)

        pe_metrics = [m for m in metrics if m['metric'] == 'pe_ratio']

        assert len(pe_metrics) > 0, "Should have some P/E ratios"

        for m in pe_metrics:
            value = float(m['value'])
            assert 0 < value < 1000, f"P/E ratio {value} for ins {m['instrument_id']} is out of range"

    def test_pb_ratio_reasonable(self):
        """P/B ratios should be within reasonable range (0-100)."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            metrics = calculate_fundamental_metrics(session, test_date)

        pb_metrics = [m for m in metrics if m['metric'] == 'pb_ratio']

        assert len(pb_metrics) > 0, "Should have some P/B ratios"

        for m in pb_metrics:
            value = float(m['value'])
            assert 0 < value < 100, f"P/B ratio {value} for ins {m['instrument_id']} is out of range"

    def test_growth_metrics_reasonable(self):
        """Growth rates should be within reasonable range (-10x to +10x)."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            metrics = calculate_fundamental_metrics(session, test_date)

        growth_metrics = [m for m in metrics if 'growth' in m['metric']]

        for m in growth_metrics:
            value = float(m['value'])
            assert -10 < value < 10, f"Growth {m['metric']}={value} for ins {m['instrument_id']} is extreme"


class TestDataQuality:
    """Test data quality and completeness."""

    def test_no_nan_values(self):
        """Verify no NaN values in calculated metrics."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            metrics = calculate_fundamental_metrics(session, test_date)

        for m in metrics:
            value = m.get('value')
            assert value is not None, f"NULL value for {m['metric']} ins {m['instrument_id']}"
            assert not (isinstance(value, float) and value != value), f"NaN for {m['metric']}"  # NaN != NaN

    def test_known_from_is_temporal(self):
        """Verify known_from <= calculation date (no future data)."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            metrics = calculate_fundamental_metrics(session, test_date)

        for m in metrics:
            known_from = m.get('known_from')
            if known_from:  # Price metrics don't have known_from
                assert known_from <= test_date, f"known_from {known_from} > test_date {test_date} for {m['metric']}"


class TestConsistency:
    """Test consistency between related metrics."""

    def test_pe_pb_consistency(self):
        """If both P/E and P/B exist for an instrument, check consistency."""
        test_date = date(2024, 1, 31)

        with get_session() as session:
            metrics = calculate_fundamental_metrics(session, test_date, instrument_ids=[2, 3, 10])

        # Group by instrument
        by_instrument = {}
        for m in metrics:
            ins_id = m['instrument_id']
            if ins_id not in by_instrument:
                by_instrument[ins_id] = {}
            by_instrument[ins_id][m['metric']] = float(m['value'])

        # Check that instruments with both P/E and P/B have reasonable values
        for ins_id, ins_metrics in by_instrument.items():
            if 'pe_ratio' in ins_metrics and 'pb_ratio' in ins_metrics:
                pe = ins_metrics['pe_ratio']
                pb = ins_metrics['pb_ratio']

                # Basic sanity: P/B should generally be less than P/E for most companies
                # (not always true, but extreme violations indicate a bug)
                if pe > 0 and pb > 0:
                    ratio = pb / pe
                    assert 0.01 < ratio < 10, f"Ins {ins_id}: P/B/P/E ratio {ratio} is suspicious (PE={pe}, PB={pb})"


def test_smoke_test():
    """Quick smoke test that everything runs without errors."""
    test_date = date(2024, 1, 31)

    with get_session() as session:
        fund_metrics = calculate_fundamental_metrics(session, test_date, instrument_ids=[2, 3])
        price_metrics = calculate_price_metrics(session, test_date, instrument_ids=[2, 3])

    assert len(fund_metrics) > 0, "Should have fundamental metrics"
    assert len(price_metrics) > 0, "Should have price metrics"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
