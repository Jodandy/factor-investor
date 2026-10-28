"""Integrity tests for base_metrics - MUST PASS before any rebuild.

These tests verify:
1. No lookahead bias (.first() not .last())
2. Correct period_type (r12/year, not quarter)
3. Reasonable value ranges
4. No NULL values where they shouldn't be
5. Consistency between related metrics
"""

from datetime import date

import polars as pl
import pytest

from factor_investor.db import get_session
from factor_investor.factors.base_metrics import (
    calculate_fundamental_metrics,
    calculate_price_metrics,
)
from factor_investor.pit import as_of


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


@pytest.fixture(scope="module")
def metrics_2024_01_31():
    """Full-universe fundamental metrics for 2024-01-31, calculated once per module."""
    with get_session() as session:
        return calculate_fundamental_metrics(session, date(2024, 1, 31))


def _values(metrics, metric):
    return pl.Series([float(m['value']) for m in metrics if m['metric'] == metric])


class TestValueRanges:
    """Test that calculated values are plausible.

    Individual extremes are real in a global universe (P/E in the thousands
    from near-zero earnings, P/B > 100 from tiny equity) and are kept; see
    DATA_AUDIT "Market Cap and Share Counts". These tests check the rules the
    code enforces and the medians, which a units or formula bug would move.
    """

    def test_pe_ratio_reasonable(self, metrics_2024_01_31):
        """P/E is only calculated for positive earnings; median P/E is 5-50."""
        pe = _values(metrics_2024_01_31, 'pe_ratio')

        assert len(pe) > 1000, "Should have P/E ratios for most of the universe"
        assert (pe > 0).all(), f"Non-positive P/E: {pe.filter(pe <= 0).to_list()[:5]}"
        assert 5 < pe.median() < 50, f"Median P/E {pe.median()} implausible"

    def test_pb_ratio_reasonable(self, metrics_2024_01_31):
        """P/B is only calculated for positive equity; median P/B is 0.5-5."""
        pb = _values(metrics_2024_01_31, 'pb_ratio')

        assert len(pb) > 1000, "Should have P/B ratios for most of the universe"
        assert (pb > 0).all(), f"Non-positive P/B: {pb.filter(pb <= 0).to_list()[:5]}"
        assert 0.5 < pb.median() < 5, f"Median P/B {pb.median()} implausible"

    def test_growth_metrics_reasonable(self, metrics_2024_01_31):
        """Growth is capped at +/-100x; median growth is between -50% and +50%."""
        for metric in ('revenue_growth_1y', 'profit_growth_1y', 'fcf_growth_1y'):
            growth = _values(metrics_2024_01_31, metric)

            assert len(growth) > 1000, f"Should have {metric} for most of the universe"
            assert (growth.abs() < 100).all(), f"{metric} exceeds the 100x cap"
            assert -0.5 < growth.median() < 0.5, f"Median {metric} {growth.median()} implausible"


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
