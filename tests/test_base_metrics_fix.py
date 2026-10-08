"""Test to verify the base_metrics .last() -> .first() fix."""

from datetime import date

import polars as pl

from factor_investor.pit import as_of


def calculate_metrics_OLD_BUGGY(test_date: date, ins_id: int, price: float) -> dict:
    """OLD BUGGY VERSION: Using .last() - returns OLDEST data."""
    pit_df_long = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share', 'book_value_per_share'])

    # OLD BUGGY: Using .last()
    pit_df = (
        pit_df_long.group_by(['instrument_id', 'metric'])
        .agg([pl.col('value').last(), pl.col('known_from').last()])
        .pivot(values='value', index='instrument_id', on='metric')
    )

    if len(pit_df) == 0:
        return {}

    row = pit_df.row(0, named=True)
    eps = row.get('earnings_per_share')
    bvps = row.get('book_value_per_share')

    result = {}
    if eps and eps > 0.001:
        result['pe_ratio'] = price / eps
    if bvps and bvps > 0.001:
        result['pb_ratio'] = price / bvps

    result['eps'] = eps
    result['bvps'] = bvps

    return result


def calculate_metrics_NEW_FIXED(test_date: date, ins_id: int, price: float) -> dict:
    """NEW FIXED VERSION: Using .first() - returns MOST RECENT data."""
    pit_df_long = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share', 'book_value_per_share'])

    # NEW FIXED: Using .first()
    pit_df = (
        pit_df_long.group_by(['instrument_id', 'metric'])
        .agg([pl.col('value').first(), pl.col('known_from').first()])
        .pivot(values='value', index='instrument_id', on='metric')
    )

    if len(pit_df) == 0:
        return {}

    row = pit_df.row(0, named=True)
    eps = row.get('earnings_per_share')
    bvps = row.get('book_value_per_share')

    result = {}
    if eps and eps > 0.001:
        result['pe_ratio'] = price / eps
    if bvps and bvps > 0.001:
        result['pb_ratio'] = price / bvps

    result['eps'] = eps
    result['bvps'] = bvps

    return result


def calculate_metrics_MANUAL(test_date: date, ins_id: int, price: float) -> dict:
    """MANUAL VERIFICATION: Explicitly get most recent period."""
    pit_df_long = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share', 'book_value_per_share'])

    result = {}

    # Manually get most recent EPS
    eps_df = pit_df_long.filter(pl.col('metric') == 'earnings_per_share')
    if len(eps_df) > 0:
        eps = float(eps_df[0, 'value'])
        result['eps'] = eps
        if eps > 0.001:
            result['pe_ratio'] = price / eps

    # Manually get most recent BVPS
    bvps_df = pit_df_long.filter(pl.col('metric') == 'book_value_per_share')
    if len(bvps_df) > 0:
        bvps = float(bvps_df[0, 'value'])
        result['bvps'] = bvps
        if bvps > 0.001:
            result['pb_ratio'] = price / bvps

    return result


if __name__ == '__main__':
    # Test cases
    test_cases = [
        {'ins_id': 2, 'name': 'AAK', 'date': date(2024, 1, 31), 'price': 235.00},
        {'ins_id': 3, 'name': 'ABB', 'date': date(2024, 1, 31), 'price': 441.80},
        {'ins_id': 10, 'name': 'Alfa Laval', 'date': date(2024, 1, 31), 'price': 384.10},
        {'ins_id': 195, 'name': 'Sandvik', 'date': date(2024, 1, 31), 'price': 219.40},
        {'ins_id': 3, 'name': 'ABB', 'date': date(2022, 6, 30), 'price': 300.00},  # Different date
    ]

    print('=' * 100)
    print('VERIFICATION: OLD (buggy) vs NEW (fixed) vs MANUAL')
    print('=' * 100)

    all_match = True

    for test_case in test_cases:
        ins_id = test_case['ins_id']
        name = test_case['name']
        test_date = test_case['date']
        price = test_case['price']

        print(f'\n{name} (ID {ins_id}) on {test_date} @ {price:.2f} SEK')
        print('-' * 100)

        old_metrics = calculate_metrics_OLD_BUGGY(test_date, ins_id, price)
        new_metrics = calculate_metrics_NEW_FIXED(test_date, ins_id, price)
        manual_metrics = calculate_metrics_MANUAL(test_date, ins_id, price)

        if not old_metrics or not new_metrics or not manual_metrics:
            print('  ⚠️  Insufficient data')
            continue

        # Compare EPS
        print(f'\nEPS:')
        print(f'  OLD (buggy):  {old_metrics.get("eps", 0):.4f}')
        print(f'  NEW (fixed):  {new_metrics.get("eps", 0):.4f}')
        print(f'  MANUAL:       {manual_metrics.get("eps", 0):.4f}')

        if abs(new_metrics.get('eps', 0) - manual_metrics.get('eps', 0)) < 0.0001:
            print(f'  ✅ NEW matches MANUAL')
        else:
            print(f'  ❌ NEW does NOT match MANUAL')
            all_match = False

        # Compare BVPS
        print(f'\nBVPS:')
        print(f'  OLD (buggy):  {old_metrics.get("bvps", 0):.4f}')
        print(f'  NEW (fixed):  {new_metrics.get("bvps", 0):.4f}')
        print(f'  MANUAL:       {manual_metrics.get("bvps", 0):.4f}')

        if abs(new_metrics.get('bvps', 0) - manual_metrics.get('bvps', 0)) < 0.0001:
            print(f'  ✅ NEW matches MANUAL')
        else:
            print(f'  ❌ NEW does NOT match MANUAL')
            all_match = False

        # Compare P/E
        if 'pe_ratio' in new_metrics and 'pe_ratio' in manual_metrics:
            print(f'\nP/E Ratio:')
            print(f'  OLD (buggy):  {old_metrics.get("pe_ratio", 0):>8.2f}')
            print(f'  NEW (fixed):  {new_metrics.get("pe_ratio", 0):>8.2f}')
            print(f'  MANUAL:       {manual_metrics.get("pe_ratio", 0):>8.2f}')

            diff_pct = abs(new_metrics['pe_ratio'] - manual_metrics['pe_ratio']) / manual_metrics['pe_ratio'] * 100
            if diff_pct < 0.1:
                print(f'  ✅ NEW matches MANUAL (diff: {diff_pct:.3f}%)')
            else:
                print(f'  ❌ NEW does NOT match MANUAL (diff: {diff_pct:.3f}%)')
                all_match = False

        # Compare P/B
        if 'pb_ratio' in new_metrics and 'pb_ratio' in manual_metrics:
            print(f'\nP/B Ratio:')
            print(f'  OLD (buggy):  {old_metrics.get("pb_ratio", 0):>8.2f}')
            print(f'  NEW (fixed):  {new_metrics.get("pb_ratio", 0):>8.2f}')
            print(f'  MANUAL:       {manual_metrics.get("pb_ratio", 0):>8.2f}')

            diff_pct = abs(new_metrics['pb_ratio'] - manual_metrics['pb_ratio']) / manual_metrics['pb_ratio'] * 100
            if diff_pct < 0.1:
                print(f'  ✅ NEW matches MANUAL (diff: {diff_pct:.3f}%)')
            else:
                print(f'  ❌ NEW does NOT match MANUAL (diff: {diff_pct:.3f}%)')
                all_match = False

        # Show impact
        if 'pe_ratio' in old_metrics and 'pe_ratio' in new_metrics:
            old_pe = old_metrics['pe_ratio']
            new_pe = new_metrics['pe_ratio']
            error_pct = abs((old_pe - new_pe) / new_pe * 100)
            print(f'\n🔴 BUG IMPACT: P/E was off by {error_pct:.1f}%')

    print('\n' + '=' * 100)
    if all_match:
        print('✅ ✅ ✅  ALL TESTS PASSED - FIX IS VERIFIED  ✅ ✅ ✅')
    else:
        print('❌ ❌ ❌  SOME TESTS FAILED - FIX NEEDS REVIEW  ❌ ❌ ❌')
    print('=' * 100)
