"""Post-build verification script for base_metrics.

Run this after building base metrics to verify data quality.
"""

from datetime import date
from factor_investor.db import get_session
from sqlalchemy import text


def verify_coverage():
    """Check that we have good coverage across metrics."""
    print('\n' + '=' * 90)
    print('COVERAGE CHECK')
    print('=' * 90)

    with get_session() as session:
        # Check fundamental metrics coverage
        result = session.execute(text('''
            SELECT
                metric,
                COUNT(DISTINCT instrument_id) as instruments,
                COUNT(DISTINCT date) as dates,
                COUNT(*) as total_rows,
                MIN(date) as first_date,
                MAX(date) as last_date
            FROM fundamental_metrics
            GROUP BY metric
            ORDER BY total_rows DESC
        '''))

        print('\nFundamental Metrics:')
        print('metric                           | instruments | dates | total_rows | date_range')
        print('-' * 95)

        total_metrics = 0
        for row in result:
            metric, instruments, dates, total_rows, first_date, last_date = row
            print(f'{metric:32s} | {instruments:>11,} | {dates:>5} | {total_rows:>10,} | {first_date} to {last_date}')
            total_metrics += 1

        print(f'\nTotal: {total_metrics} fundamental metrics')

        # Check price metrics coverage
        result = session.execute(text('''
            SELECT
                metric,
                COUNT(DISTINCT instrument_id) as instruments,
                COUNT(*) as total_rows
            FROM price_metrics
            GROUP BY metric
            ORDER BY total_rows DESC
        '''))

        print('\nPrice Metrics:')
        print('metric                           | instruments | total_rows')
        print('-' * 70)

        for row in result:
            metric, instruments, total_rows = row
            print(f'{metric:32s} | {instruments:>11,} | {total_rows:>10,}')

    print('\n✅ Coverage check complete')


def verify_spot_checks():
    """Spot-check specific instruments for correctness."""
    print('\n' + '=' * 90)
    print('SPOT CHECK VERIFICATION')
    print('=' * 90)

    test_date = date(2024, 1, 31)

    # Known values to check
    test_cases = [
        {'ins_id': 2, 'name': 'AAK', 'expected_pe_range': (20, 70)},
        {'ins_id': 3, 'name': 'ABB', 'expected_pe_range': (20, 90)},
        {'ins_id': 195, 'name': 'Sandvik', 'expected_pe_range': (15, 70)},
    ]

    with get_session() as session:
        all_pass = True

        for test_case in test_cases:
            ins_id = test_case['ins_id']
            name = test_case['name']
            expected_pe_range = test_case['expected_pe_range']

            # Get P/E ratio from DB
            result = session.execute(text('''
                SELECT value FROM fundamental_metrics
                WHERE instrument_id = :ins_id AND metric = 'pe_ratio' AND date = :test_date
            '''), {'ins_id': ins_id, 'test_date': test_date})

            row = result.fetchone()

            if row:
                pe_value = float(row[0])
                min_pe, max_pe = expected_pe_range

                status = '✅' if min_pe <= pe_value <= max_pe else '❌'
                print(f'{name:15s} (ID {ins_id:>5}): P/E = {pe_value:>6.2f} | Expected: {min_pe}-{max_pe} | {status}')

                if not (min_pe <= pe_value <= max_pe):
                    all_pass = False
            else:
                print(f'{name:15s} (ID {ins_id:>5}): ❌ NO DATA')
                all_pass = False

    if all_pass:
        print('\n✅ All spot checks passed')
    else:
        print('\n⚠️  Some spot checks failed - review values')

    return all_pass


def verify_data_quality():
    """Check for data quality issues."""
    print('\n' + '=' * 90)
    print('DATA QUALITY CHECK')
    print('=' * 90)

    with get_session() as session:
        # Check for NULL values
        result = session.execute(text('''
            SELECT COUNT(*) FROM fundamental_metrics WHERE value IS NULL
        '''))
        null_count = result.fetchone()[0]

        if null_count > 0:
            print(f'❌ Found {null_count:,} NULL values in fundamental_metrics')
        else:
            print(f'✅ No NULL values in fundamental_metrics')

        # Check for extreme outliers (potential bugs)
        result = session.execute(text('''
            SELECT
                metric,
                COUNT(*) as count,
                MIN(value) as min_val,
                MAX(value) as max_val
            FROM fundamental_metrics
            WHERE ABS(value) > 10000
            GROUP BY metric
            ORDER BY count DESC
            LIMIT 10
        '''))

        rows = result.fetchall()

        if rows:
            print(f'\n⚠️  Metrics with extreme values (>10,000):')
            print('metric                           | count    | min_val      | max_val')
            print('-' * 80)
            for row in rows:
                print(f'{row[0]:32s} | {row[1]:>8,} | {row[2]:>12,.2f} | {row[3]:>12,.2f}')
        else:
            print(f'\n✅ No extreme outliers detected')

        # Check known_from temporal integrity
        result = session.execute(text('''
            SELECT COUNT(*)
            FROM fundamental_metrics
            WHERE known_from > date
        '''))
        future_data = result.fetchone()[0]

        if future_data > 0:
            print(f'\n❌ Found {future_data:,} rows with known_from > date (LOOKAHEAD BIAS!)')
        else:
            print(f'\n✅ No lookahead bias detected (all known_from <= date)')

    print('\n✅ Data quality check complete')


def verify_consistency():
    """Check consistency between related metrics."""
    print('\n' + '=' * 90)
    print('CONSISTENCY CHECK')
    print('=' * 90)

    test_date = date(2024, 1, 31)

    with get_session() as session:
        # Check that instruments with P/E also have P/B (and vice versa)
        result = session.execute(text('''
            WITH pe_instruments AS (
                SELECT DISTINCT instrument_id
                FROM fundamental_metrics
                WHERE metric = 'pe_ratio' AND date = :test_date
            ),
            pb_instruments AS (
                SELECT DISTINCT instrument_id
                FROM fundamental_metrics
                WHERE metric = 'pb_ratio' AND date = :test_date
            )
            SELECT
                (SELECT COUNT(*) FROM pe_instruments) as pe_count,
                (SELECT COUNT(*) FROM pb_instruments) as pb_count,
                (SELECT COUNT(*) FROM pe_instruments INTERSECT SELECT instrument_id FROM pb_instruments) as both_count
        '''), {'test_date': test_date})

        pe_count, pb_count, both_count = result.fetchone()

        # Handle None values
        pe_count = pe_count or 0
        pb_count = pb_count or 0
        both_count = both_count or 0

        print(f'\nMetric overlap for {test_date}:')
        print(f'  Instruments with P/E:     {pe_count:>6,}')
        print(f'  Instruments with P/B:     {pb_count:>6,}')
        print(f'  Instruments with both:    {both_count:>6,}')
        print(f'  Overlap ratio:            {both_count/max(pe_count,1)*100:>5.1f}%')

        if both_count / max(pe_count, 1) > 0.8:
            print('  ✅ Good overlap between valuation metrics')
        else:
            print('  ⚠️  Low overlap - possible data issues')

    print('\n✅ Consistency check complete')


def main():
    """Run all verification checks."""
    print('\n')
    print('╔' + '═' * 88 + '╗')
    print('║' + ' ' * 88 + '║')
    print('║' + '  BASE METRICS VERIFICATION'.center(88) + '║')
    print('║' + ' ' * 88 + '║')
    print('╚' + '═' * 88 + '╝')

    verify_coverage()
    spot_check_pass = verify_spot_checks()
    verify_data_quality()
    verify_consistency()

    print('\n' + '=' * 90)
    print('VERIFICATION COMPLETE')
    print('=' * 90)

    if spot_check_pass:
        print('✅ All critical checks passed')
        print('✅ Data appears correct and ready to use')
    else:
        print('⚠️  Some checks failed - review output above')

    print('=' * 90)


if __name__ == '__main__':
    main()
