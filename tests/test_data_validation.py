"""Test that data validation catches potential issues."""

from datetime import date, timedelta
import polars as pl
from factor_investor.pit import as_of
from factor_investor.factors.base_metrics import calculate_fundamental_metrics
from factor_investor.db import get_session


def test_no_future_data():
    """Verify we never use data from the future (critical lookahead check)."""
    test_date = date(2024, 1, 31)

    with get_session() as session:
        metrics = calculate_fundamental_metrics(session, test_date, instrument_ids=[2, 3, 10])

    # Every metric should have known_from <= test_date
    for m in metrics:
        known_from = m.get('known_from')
        if known_from:
            assert known_from <= test_date, (
                f"CRITICAL: Future data! Metric {m['metric']} for instrument {m['instrument_id']} "
                f"has known_from {known_from} > test_date {test_date}"
            )

    print(f"✅ No future data detected for {len(metrics)} metrics")


def test_data_sorting():
    """Verify as_of() returns data sorted by period_end DESC."""
    test_date = date(2024, 1, 31)
    ins_id = 2

    pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])

    # Filter to one period_type to check sorting
    for ptype in ['quarter', 'r12', 'year']:
        ptype_data = pit_df.filter(pl.col('period_type') == ptype)
        if len(ptype_data) > 1:
            # Check that data is sorted DESC
            for i in range(len(ptype_data) - 1):
                current_period = ptype_data[i, 'period_end']
                next_period = ptype_data[i + 1, 'period_end']
                assert current_period >= next_period, (
                    f"Data NOT sorted correctly for {ptype}: "
                    f"row {i} period={current_period}, row {i+1} period={next_period}"
                )

    print(f"✅ Data sorting verified for {len(pit_df)} rows")


def test_reasonable_data_age():
    """Verify we're not using extremely old data for recent dates."""
    test_date = date(2024, 1, 31)

    with get_session() as session:
        metrics = calculate_fundamental_metrics(session, test_date, instrument_ids=[2, 3, 10, 195])

    # For these major companies in 2024, data shouldn't be >5 years old
    max_age_days = 5 * 365

    for m in metrics:
        known_from = m.get('known_from')
        if known_from:
            age_days = (test_date - known_from).days
            # This is a soft check - some companies might have old data
            if age_days > max_age_days:
                print(f"⚠️  Old data: {m['metric']} for {m['instrument_id']}: {age_days} days old")

    print(f"✅ Data age check complete for {len(metrics)} metrics")


def test_period_end_matches_period_type():
    """Verify period_end aligns with period_type (year data has year-end dates)."""
    test_date = date(2024, 1, 31)
    ins_id = 2

    pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])

    # Year data should have period_end on 12-31 (or close to it)
    year_data = pit_df.filter(pl.col('period_type') == 'year')
    for row in year_data.iter_rows(named=True):
        period_end = row['period_end']
        # Most year periods end on 12-31, some on 12-30
        assert period_end.month == 12, (
            f"Year period {period_end} doesn't end in December (unexpected)"
        )
        assert period_end.day >= 28, (
            f"Year period {period_end} doesn't end near month-end (unexpected)"
        )

    print(f"✅ Period type consistency verified for year data")


def test_first_row_is_most_recent():
    """Verify .first() gives us the most recent data, not oldest."""
    test_date = date(2024, 1, 31)
    ins_id = 2

    pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])

    # For each period_type, verify first row has latest period_end
    for ptype in ['quarter', 'r12', 'year']:
        ptype_data = pit_df.filter(pl.col('period_type') == ptype)
        if len(ptype_data) > 1:
            # Get first and last (extract values properly)
            first_period = ptype_data[0, 'period_end']
            last_period = ptype_data[-1, 'period_end']

            # First should be MORE RECENT (greater date) than last
            assert first_period >= last_period, (
                f"{ptype}: .first() gives {first_period}, .last() gives {last_period}. "
                f"First should be >= last!"
            )

            print(f"✅ {ptype:7s}: .first()={first_period} (most recent) > .last()={last_period} (oldest)")


if __name__ == '__main__':
    print('\n' + '=' * 80)
    print('DATA VALIDATION TESTS')
    print('=' * 80 + '\n')

    test_no_future_data()
    test_data_sorting()
    test_reasonable_data_age()
    test_period_end_matches_period_type()
    test_first_row_is_most_recent()

    print('\n' + '=' * 80)
    print('✅ ALL VALIDATION TESTS PASSED')
    print('=' * 80)
