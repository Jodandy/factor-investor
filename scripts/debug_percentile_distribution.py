"""Debug script to investigate percentile distribution.

This checks if percentile calculation is working correctly by looking at
the actual distribution of ROIC values in the universe.
"""

from datetime import date

import polars as pl

from factor_investor.factors.queries import get_factor


def main():
    """Investigate ROIC percentile distribution."""

    print("\n" + "=" * 80)
    print("DEBUG: ROIC Percentile Distribution")
    print("=" * 80)

    # Pick a date to investigate
    test_date = date(2020, 12, 31)

    print(f"\nInvestigating date: {test_date}")
    print("-" * 80)

    # Get both raw and percentile ROIC
    print("\nLoading ROIC data...")
    roic_mean_raw = get_factor("roic_mean_5y_raw", test_date)
    roic_mean_pct = get_factor("roic_mean_5y_pct", test_date)

    print(f"  Raw ROIC: {len(roic_mean_raw)} instruments")
    print(f"  Percentile ROIC: {len(roic_mean_pct)} instruments")

    if len(roic_mean_raw) == 0:
        print("\n❌ No data found!")
        return

    # Join them
    combined = roic_mean_raw.join(
        roic_mean_pct, on=["instrument_id", "date"], suffix="_pct"
    ).rename({"value": "roic_raw", "value_pct": "roic_pct"})

    # Show distribution of RAW values
    print("\n" + "=" * 80)
    print("RAW ROIC Distribution (5-year mean)")
    print("=" * 80)

    roic_stats = combined["roic_raw"].describe()
    print(roic_stats)

    # Count by ranges
    print("\nROIC Value Ranges:")
    print(f"  Negative (<0%):       {(combined['roic_raw'] < 0).sum():>6,} instruments")
    print(f"  0-5%:                 {((combined['roic_raw'] >= 0) & (combined['roic_raw'] < 5)).sum():>6,} instruments")
    print(f"  5-10%:                {((combined['roic_raw'] >= 5) & (combined['roic_raw'] < 10)).sum():>6,} instruments")
    print(f"  10-20%:               {((combined['roic_raw'] >= 10) & (combined['roic_raw'] < 20)).sum():>6,} instruments")
    print(f"  20-50%:               {((combined['roic_raw'] >= 20) & (combined['roic_raw'] < 50)).sum():>6,} instruments")
    print(f"  50%+:                 {(combined['roic_raw'] >= 50).sum():>6,} instruments")
    print(f"  Total:                {len(combined):>6,} instruments")

    # Show percentile breakdown
    print("\n" + "=" * 80)
    print("Percentile Breakdown (what ROIC value corresponds to each percentile?)")
    print("=" * 80)

    percentiles = [0, 10, 25, 50, 75, 90, 95, 99, 100]
    print(f"\n{'Percentile':<12} {'ROIC Value':>12}")
    print("-" * 30)
    for pct in percentiles:
        val = combined["roic_raw"].quantile(pct / 100)
        print(f"P{pct:<10}   {val:>12.1f}%")

    # Show top 30 (what our strategy would pick)
    print("\n" + "=" * 80)
    print("Top 30 Companies by ROIC Percentile (what strategy picks)")
    print("=" * 80)

    top_30 = combined.sort("roic_pct", descending=True).head(30)

    print(f"\n{'Rank':<6} {'Instr ID':>8} {'ROIC Pct':>10} {'ROIC Raw':>10}")
    print("-" * 40)
    for i, row in enumerate(top_30.iter_rows(named=True), 1):
        print(
            f"{i:<6} {row['instrument_id']:>8} "
            f"{row['roic_pct']:>10.1f} {row['roic_raw']:>10.1f}%"
        )

    # Check if percentile matches raw ranking
    print("\n" + "=" * 80)
    print("Verification: Does percentile match actual ranking?")
    print("=" * 80)

    # Add rank based on raw value
    combined_ranked = combined.with_columns(
        pl.col("roic_raw").rank(descending=True).alias("rank_by_raw")
    ).with_columns(
        ((pl.col("rank_by_raw") / len(combined)) * 100).alias("expected_pct")
    )

    # Compare top 30
    comparison = combined_ranked.sort("roic_pct", descending=True).head(30).select(
        ["instrument_id", "roic_raw", "roic_pct", "expected_pct"]
    )

    print(f"\n{'Instr ID':>8} {'ROIC Raw':>10} {'Actual Pct':>11} {'Expected Pct':>12} {'Diff':>8}")
    print("-" * 60)
    for row in comparison.iter_rows(named=True):
        diff = row["roic_pct"] - row["expected_pct"]
        print(
            f"{row['instrument_id']:>8} {row['roic_raw']:>10.1f}% "
            f"{row['roic_pct']:>11.1f} {row['expected_pct']:>12.1f} "
            f"{diff:>8.1f}"
        )

    # Summary
    max_diff = abs(comparison["roic_pct"] - comparison["expected_pct"]).max()
    print(f"\nMax difference: {max_diff:.1f} percentile points")

    if max_diff < 1:
        print("✅ Percentile calculation looks correct!")
    elif max_diff < 5:
        print("⚠️  Small discrepancies in percentile calculation")
    else:
        print("❌ Percentile calculation has issues!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
