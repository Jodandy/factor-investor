"""Test to verify growth metrics fix (.last() -> .first())."""

from datetime import date, timedelta

import polars as pl

from factor_investor.pit import as_of


def test_growth_calculation():
    """Verify growth metrics use correct (most recent) values."""
    test_date = date(2024, 1, 31)
    one_year_ago = test_date - timedelta(days=365)
    ins_id = 2  # AAK

    print('=' * 80)
    print('GROWTH METRICS VERIFICATION')
    print('=' * 80)

    # Get current revenue
    current_df = as_of(test_date, instrument_ids=[ins_id], metrics=['revenues'])
    print(f'\nCurrent date: {test_date}')
    print(f'Current revenues (first 3 periods):')
    for i, row in enumerate(current_df.head(3).iter_rows(named=True)):
        marker = '← SHOULD USE THIS' if i == 0 else ''
        print(f'  {row["period_end"]} | {row["value"]:>12,.0f} | known_from={row["known_from"]} {marker}')

    # Get historical revenue
    hist_df = as_of(one_year_ago, instrument_ids=[ins_id], metrics=['revenues'])
    print(f'\nHistorical date: {one_year_ago}')
    print(f'Historical revenues (first 3 periods):')
    for i, row in enumerate(hist_df.head(3).iter_rows(named=True)):
        marker = '← SHOULD USE THIS' if i == 0 else ''
        print(f'  {row["period_end"]} | {row["value"]:>12,.0f} | known_from={row["known_from"]} {marker}')

    # Calculate OLD way (buggy)
    current_buggy = (
        current_df.group_by(['instrument_id', 'metric'])
        .agg([pl.col('value').last()])
        .pivot(values='value', index='instrument_id', on='metric')
    )
    hist_buggy = (
        hist_df.group_by(['instrument_id', 'metric'])
        .agg([pl.col('value').last()])
        .pivot(values='value', index='instrument_id', on='metric')
    )

    current_val_buggy = float(current_buggy.row(0, named=True)['revenues'])
    hist_val_buggy = float(hist_buggy.row(0, named=True)['revenues'])
    growth_buggy = (current_val_buggy - hist_val_buggy) / hist_val_buggy

    print(f'\nOLD (buggy) calculation using .last():')
    print(f'  Current:     {current_val_buggy:>12,.0f}')
    print(f'  Historical:  {hist_val_buggy:>12,.0f}')
    print(f'  Growth:      {growth_buggy:>11.2%}')

    # Calculate NEW way (fixed)
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

    current_val_fixed = float(current_fixed.row(0, named=True)['revenues'])
    hist_val_fixed = float(hist_fixed.row(0, named=True)['revenues'])
    growth_fixed = (current_val_fixed - hist_val_fixed) / hist_val_fixed

    print(f'\nNEW (fixed) calculation using .first():')
    print(f'  Current:     {current_val_fixed:>12,.0f}')
    print(f'  Historical:  {hist_val_fixed:>12,.0f}')
    print(f'  Growth:      {growth_fixed:>11.2%}')

    # Manual verification
    current_val_manual = float(current_df[0, 'value'])
    hist_val_manual = float(hist_df[0, 'value'])
    growth_manual = (current_val_manual - hist_val_manual) / hist_val_manual

    print(f'\nMANUAL verification (explicit first row):')
    print(f'  Current:     {current_val_manual:>12,.0f}')
    print(f'  Historical:  {hist_val_manual:>12,.0f}')
    print(f'  Growth:      {growth_manual:>11.2%}')

    print(f'\n{"=" * 80}')

    if abs(growth_fixed - growth_manual) < 0.0001:
        print('✅ NEW (fixed) matches MANUAL')
    else:
        print('❌ NEW (fixed) does NOT match MANUAL')

    if abs(growth_buggy - growth_manual) > 0.01:
        error_pct = abs((growth_buggy - growth_manual) / growth_manual * 100)
        print(f'🔴 BUG IMPACT: Growth was off by {error_pct:.1f}%')

    print('=' * 80)


if __name__ == '__main__':
    test_growth_calculation()
