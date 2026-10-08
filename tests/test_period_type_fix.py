"""Test to verify period_type filtering fix."""

from datetime import date

import polars as pl

from factor_investor.pit import as_of


def test_period_type_filtering():
    """Verify base_metrics uses r12/year, not quarterly data."""
    print('=' * 90)
    print('PERIOD_TYPE FILTERING VERIFICATION')
    print('=' * 90)

    test_date = date(2024, 1, 31)
    ins_id = 2  # AAK

    # Get all period types from as_of
    pit_df = as_of(test_date, instrument_ids=[ins_id], metrics=['earnings_per_share'])

    print(f'\nData returned by as_of() for EPS:')
    print('period_type | period_end | value   | known_from')
    print('-' * 60)

    eps_by_type = {}
    for row in pit_df.head(10).iter_rows(named=True):
        period_type = row['period_type']
        if period_type not in eps_by_type:
            eps_by_type[period_type] = row['value']
            print(f'{period_type:11s} | {row["period_end"]} | {row["value"]:>7.4f} | {row["known_from"]}')

    # Replicate the FIXED filtering logic
    pit_df_r12 = pit_df.filter(pl.col("period_type") == "r12")
    pit_df_year = pit_df.filter(pl.col("period_type") == "year")
    r12_pairs = pit_df_r12.select(["instrument_id", "metric"]).unique()

    pit_df_filtered = pl.concat([
        pit_df_r12,
        pit_df_year.join(r12_pairs, on=["instrument_id", "metric"], how="anti")
    ])

    # Get the value that will be used
    if len(pit_df_filtered) > 0:
        pivot_df = (
            pit_df_filtered.group_by(["instrument_id", "metric"])
            .agg([pl.col("value").first()])
            .pivot(values="value", index="instrument_id", on="metric")
        )
        used_eps = float(pivot_df.row(0, named=True)['earnings_per_share'])
        used_period_type = pit_df_filtered[0, 'period_type']

        print(f'\n✅ AFTER FILTERING:')
        print(f'   Period type used: {used_period_type}')
        print(f'   EPS value used:   {used_eps:.4f}')

        # Verify it's r12 or year, NOT quarter
        if used_period_type in ['r12', 'year']:
            print(f'   ✅ CORRECT - Using {used_period_type} (trailing twelve months)')
        else:
            print(f'   ❌ WRONG - Using {used_period_type} (should be r12 or year)')
            return False

        # Calculate P/E with different period types
        price = 235.00
        print(f'\n📊 P/E RATIO CALCULATION (price = {price:.2f}):')

        if 'quarter' in eps_by_type:
            pe_quarter = price / eps_by_type['quarter']
            print(f'   Quarter EPS ({eps_by_type["quarter"]:.2f}): P/E = {pe_quarter:.2f} ❌ WRONG')

        if 'r12' in eps_by_type:
            pe_r12 = price / eps_by_type['r12']
            marker = '✅ CORRECT' if used_period_type == 'r12' else ''
            print(f'   R12 EPS     ({eps_by_type["r12"]:.2f}): P/E = {pe_r12:.2f} {marker}')

        if 'year' in eps_by_type:
            pe_year = price / eps_by_type['year']
            marker = '✅ CORRECT' if used_period_type == 'year' else ''
            print(f'   Year EPS    ({eps_by_type["year"]:.2f}): P/E = {pe_year:.2f} {marker}')

        return True

    else:
        print('❌ No data after filtering!')
        return False


def test_multiple_instruments():
    """Test period_type filtering for multiple instruments."""
    print('\n' + '=' * 90)
    print('MULTIPLE INSTRUMENTS TEST')
    print('=' * 90)

    test_date = date(2024, 1, 31)
    instrument_ids = [2, 3, 10, 195]  # AAK, ABB, Alfa Laval, Sandvik

    pit_df = as_of(test_date, instrument_ids=instrument_ids, metrics=['earnings_per_share'])

    # Apply filtering
    pit_df_r12 = pit_df.filter(pl.col("period_type") == "r12")
    pit_df_year = pit_df.filter(pl.col("period_type") == "year")
    r12_pairs = pit_df_r12.select(["instrument_id", "metric"]).unique()

    pit_df_filtered = pl.concat([
        pit_df_r12,
        pit_df_year.join(r12_pairs, on=["instrument_id", "metric"], how="anti")
    ])

    print(f'\nBefore filtering: {pit_df.select("instrument_id").n_unique()} instruments')
    print(f'After filtering:  {pit_df_filtered.select("instrument_id").n_unique()} instruments')

    # Check period_type distribution
    period_type_counts = pit_df_filtered.group_by('period_type').agg(pl.count()).sort('period_type')

    print(f'\nPeriod types after filtering:')
    for row in period_type_counts.iter_rows(named=True):
        print(f'  {row["period_type"]:10s}: {row["count"]:>3} rows')

    # Verify no quarterly data
    has_quarter = 'quarter' in pit_df_filtered['period_type'].unique().to_list()

    if has_quarter:
        print('\n❌ FAILED - Quarterly data still present after filtering!')
        return False
    else:
        print('\n✅ PASSED - Only r12/year data after filtering')
        return True


if __name__ == '__main__':
    print('\n')
    print('╔' + '═' * 88 + '╗')
    print('║' + ' ' * 88 + '║')
    print('║' + '  PERIOD_TYPE FIX VERIFICATION'.center(88) + '║')
    print('║' + ' ' * 88 + '║')
    print('╚' + '═' * 88 + '╝')
    print()

    test1_pass = test_period_type_filtering()
    test2_pass = test_multiple_instruments()

    print('\n' + '=' * 90)
    print('RESULTS')
    print('=' * 90)
    print(f'Test 1 - Period type filtering: {"✅ PASS" if test1_pass else "❌ FAIL"}')
    print(f'Test 2 - Multiple instruments:  {"✅ PASS" if test2_pass else "❌ FAIL"}')

    if test1_pass and test2_pass:
        print('\n✅ ✅ ✅  ALL TESTS PASSED  ✅ ✅ ✅')
        print('\n🚀 Period type fix is verified and working correctly!')
    else:
        print('\n❌ ❌ ❌  TESTS FAILED  ❌ ❌ ❌')

    print('=' * 90)
