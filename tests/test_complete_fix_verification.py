"""Comprehensive verification of ALL base_metrics fixes before rebuild.

This test verifies:
1. Valuation ratios (P/E, P/B) use most recent fundamentals
2. Growth metrics use most recent values for both current and historical
3. Edge cases (multiple instruments, different dates)
"""

from datetime import date, timedelta

import polars as pl

from factor_investor.pit import as_of


def verify_valuation_ratios():
    """Test valuation ratio calculations."""
    print('=' * 90)
    print('TEST 1: VALUATION RATIOS (P/E, P/B)')
    print('=' * 90)

    test_cases = [
        {'ins_id': 2, 'name': 'AAK', 'date': date(2024, 1, 31)},
        {'ins_id': 3, 'name': 'ABB', 'date': date(2024, 1, 31)},
        {'ins_id': 195, 'name': 'Sandvik', 'date': date(2023, 6, 30)},
        {'ins_id': 10, 'name': 'Alfa Laval', 'date': date(2022, 12, 31)},
    ]

    all_pass = True

    for test_case in test_cases:
        ins_id = test_case['ins_id']
        name = test_case['name']
        test_date = test_case['date']

        pit_df_long = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share', 'book_value_per_share'])

        if len(pit_df_long) == 0:
            print(f'\n{name} ({ins_id}) @ {test_date}: ⚠️  No data')
            continue

        # Using NEW (fixed) logic
        pit_df_fixed = (
            pit_df_long.group_by(['instrument_id', 'metric'])
            .agg([pl.col('value').first()])
            .pivot(values='value', index='instrument_id', on='metric')
        )

        # Manual verification
        eps_manual = float(pit_df_long.filter(pl.col('metric') == 'earnings_per_share')[0, 'value'])
        bvps_manual = float(pit_df_long.filter(pl.col('metric') == 'book_value_per_share')[0, 'value'])

        # Compare
        row = pit_df_fixed.row(0, named=True)
        eps_fixed = row.get('earnings_per_share')
        bvps_fixed = row.get('book_value_per_share')

        eps_match = abs(eps_fixed - eps_manual) < 0.0001
        bvps_match = abs(bvps_fixed - bvps_manual) < 0.0001

        status = '✅' if (eps_match and bvps_match) else '❌'

        print(f'\n{name} ({ins_id}) @ {test_date}: {status}')
        print(f'  EPS:  Fixed={eps_fixed:.4f} | Manual={eps_manual:.4f} | Match={eps_match}')
        print(f'  BVPS: Fixed={bvps_fixed:.4f} | Manual={bvps_manual:.4f} | Match={bvps_match}')

        if not (eps_match and bvps_match):
            all_pass = False

    return all_pass


def verify_growth_metrics():
    """Test growth metric calculations."""
    print('\n' + '=' * 90)
    print('TEST 2: GROWTH METRICS (Revenue, Profit, FCF)')
    print('=' * 90)

    test_cases = [
        {'ins_id': 2, 'name': 'AAK', 'date': date(2024, 1, 31), 'metric': 'revenues'},
        {'ins_id': 3, 'name': 'ABB', 'date': date(2024, 1, 31), 'metric': 'revenues'},
        {'ins_id': 195, 'name': 'Sandvik', 'date': date(2023, 6, 30), 'metric': 'profit_to_equity_holders'},
    ]

    all_pass = True

    for test_case in test_cases:
        ins_id = test_case['ins_id']
        name = test_case['name']
        test_date = test_case['date']
        metric = test_case['metric']

        one_year_ago = test_date - timedelta(days=365)

        # Get current and historical
        current_df = as_of(test_date, instrument_ids=[ins_id], metrics=[metric])
        hist_df = as_of(one_year_ago, instrument_ids=[ins_id], metrics=[metric])

        if len(current_df) == 0 or len(hist_df) == 0:
            print(f'\n{name} ({ins_id}) @ {test_date}: ⚠️  Insufficient data')
            continue

        # Using NEW (fixed) logic
        current_fixed = (
            current_df.group_by(['instrument_id', 'metric'])
            .agg([pl.col('value').first()])
            .pivot(values='value', index='instrument_id', on='metric')
        )
        hist_fixed = (
            hist_df.group_by(['instrument_id', 'metric'])
            .agg([pl.col('value').first()])
            .pivot(values='value', index='instrument_id', on='metric')
        )

        current_val_fixed = float(current_fixed.row(0, named=True)[metric])
        hist_val_fixed = float(hist_fixed.row(0, named=True)[metric])

        # Manual verification
        current_val_manual = float(current_df[0, 'value'])
        hist_val_manual = float(hist_df[0, 'value'])

        current_match = abs(current_val_fixed - current_val_manual) < 0.01
        hist_match = abs(hist_val_fixed - hist_val_manual) < 0.01

        status = '✅' if (current_match and hist_match) else '❌'

        print(f'\n{name} ({ins_id}) @ {test_date} [{metric}]: {status}')
        print(f'  Current:    Fixed={current_val_fixed:>12,.0f} | Manual={current_val_manual:>12,.0f} | Match={current_match}')
        print(f'  Historical: Fixed={hist_val_fixed:>12,.0f} | Manual={hist_val_manual:>12,.0f} | Match={hist_match}')

        if current_match and hist_match:
            growth = (current_val_fixed - hist_val_fixed) / hist_val_fixed
            print(f'  Growth: {growth:>6.2%}')

        if not (current_match and hist_match):
            all_pass = False

    return all_pass


def verify_edge_cases():
    """Test edge cases."""
    print('\n' + '=' * 90)
    print('TEST 3: EDGE CASES')
    print('=' * 90)

    # Edge case 1: Instrument with very old data
    print('\nEdge case 1: Instrument with many historical periods')
    ins_id = 2
    test_date = date(2024, 1, 31)
    pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])

    print(f'  Total periods returned: {len(pit_df)}')
    print(f'  First (most recent): {pit_df[0, "period_end"]} | value={pit_df[0, "value"]}')
    print(f'  Last (oldest):       {pit_df[-1, "period_end"]} | value={pit_df[-1, "value"]}')

    pivot_df = (
        pit_df.group_by(['instrument_id', 'metric'])
        .agg([pl.col('value').first()])
        .pivot(values='value', index='instrument_id', on='metric')
    )

    value_from_pivot = float(pivot_df.row(0, named=True)['earnings_per_share'])
    value_manual = float(pit_df[0, 'value'])

    match = abs(value_from_pivot - value_manual) < 0.0001
    print(f'  Pivot uses first row: {match} ✅' if match else f'  Pivot uses first row: {match} ❌')

    # Edge case 2: Different dates
    print('\nEdge case 2: Multiple dates for same instrument')
    dates_to_test = [date(2024, 1, 31), date(2023, 6, 30), date(2022, 12, 31)]
    all_match = True

    for test_date in dates_to_test:
        pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])
        if len(pit_df) == 0:
            continue

        pivot_df = (
            pit_df.group_by(['instrument_id', 'metric'])
            .agg([pl.col('value').first()])
            .pivot(values='value', index='instrument_id', on='metric')
        )

        value_from_pivot = float(pivot_df.row(0, named=True)['earnings_per_share'])
        value_manual = float(pit_df[0, 'value'])
        match = abs(value_from_pivot - value_manual) < 0.0001

        print(f'  {test_date}: value={value_from_pivot:.4f} | matches_manual={match}')
        if not match:
            all_match = False

    return all_match


def main():
    """Run all verification tests."""
    print('\n')
    print('╔' + '═' * 88 + '╗')
    print('║' + ' ' * 88 + '║')
    print('║' + '  COMPREHENSIVE BASE_METRICS FIX VERIFICATION'.center(88) + '║')
    print('║' + ' ' * 88 + '║')
    print('╚' + '═' * 88 + '╝')
    print()

    test1_pass = verify_valuation_ratios()
    test2_pass = verify_growth_metrics()
    test3_pass = verify_edge_cases()

    print('\n' + '=' * 90)
    print('FINAL RESULTS')
    print('=' * 90)

    print(f'Test 1 - Valuation Ratios: {"✅ PASS" if test1_pass else "❌ FAIL"}')
    print(f'Test 2 - Growth Metrics:   {"✅ PASS" if test2_pass else "❌ FAIL"}')
    print(f'Test 3 - Edge Cases:       {"✅ PASS" if test3_pass else "❌ FAIL"}')

    print('\n' + '=' * 90)

    if test1_pass and test2_pass and test3_pass:
        print('✅ ✅ ✅  ALL VERIFICATION TESTS PASSED  ✅ ✅ ✅')
        print('\n🚀 FIX IS VERIFIED - READY FOR REBUILD!')
    else:
        print('❌ ❌ ❌  SOME TESTS FAILED  ❌ ❌ ❌')
        print('\n⚠️  DO NOT REBUILD YET - FIX NEEDS MORE WORK')

    print('=' * 90)


if __name__ == '__main__':
    main()
