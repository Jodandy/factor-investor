"""Test Piotroski F-Score calculation.

This script validates that the composite score system works correctly
and that Piotroski F-Score produces reasonable results.
"""

from datetime import date

from factor_investor.factors.composites import (
    calculate_composite_score,
    get_composite_config,
    list_available_composites,
)


def test_composite_config():
    """Test that composite config can be loaded."""
    print("\n" + "=" * 80)
    print("COMPOSITE CONFIG TEST")
    print("=" * 80)

    # List available composites
    composites = list_available_composites()
    print(f"\nAvailable composites: {composites}")

    if "piotroski" in composites:
        # Load Piotroski config
        config = get_composite_config("piotroski")

        print(f"\n✓ Loaded: {config['name']}")
        print(f"  Family: {config['family']}")
        print(f"  Components: {len(config['components'])}")
        print(f"  Min required: {config['min_components_required']}")

        # Show components
        print("\n  Components:")
        for component in config["components"]:
            print(f"    • {component['id']:25s} - {component['description']}")

        return True
    else:
        print("✗ ERROR: piotroski config not found")
        return False


def test_piotroski_calculation():
    """Test Piotroski F-Score calculation."""
    print("\n" + "=" * 80)
    print("PIOTROSKI F-SCORE CALCULATION TEST")
    print("=" * 80)

    test_date = date(2024, 1, 31)

    print(f"\nCalculating Piotroski F-Score for {test_date}...")

    # Calculate score
    df = calculate_composite_score("piotroski", test_date)

    if len(df) == 0:
        print("✗ ERROR: No scores calculated")
        return False

    print(f"✓ Calculated {len(df)} scores")

    # Show statistics
    print(f"\nScore distribution:")
    print(f"  Min:    {df['score'].min()}")
    print(f"  Max:    {df['score'].max()}")
    print(f"  Mean:   {df['score'].mean():.2f}")
    print(f"  Median: {df['score'].median():.1f}")

    # Show score label distribution
    print(f"\nScore labels:")
    label_counts = df.group_by("score_label").agg(pl.count().alias("count")).sort("score_label")
    for row in label_counts.iter_rows(named=True):
        pct = row["count"] / len(df) * 100
        print(f"  {row['score_label']:15s}: {row['count']:>6,} ({pct:>5.1f}%)")

    # Show top and bottom scores
    print(f"\nTop 10 scores:")
    top10 = df.sort("score", descending=True).head(10)
    for row in top10.iter_rows(named=True):
        print(
            f"  Instrument {row['instrument_id']:>6}: "
            f"Score {row['score']}/9 ({row['score_label']})"
        )

    print(f"\nBottom 10 scores:")
    bottom10 = df.sort("score").head(10)
    for row in bottom10.iter_rows(named=True):
        print(
            f"  Instrument {row['instrument_id']:>6}: "
            f"Score {row['score']}/9 ({row['score_label']})"
        )

    # Verify score range
    assert 0 <= df["score"].min() <= 9, "Score min outside [0, 9]"
    assert 0 <= df["score"].max() <= 9, "Score max outside [0, 9]"

    # Verify distribution makes sense (should be somewhat normal-ish)
    mean = df["score"].mean()
    assert 2 < mean < 7, f"Mean score {mean:.2f} outside reasonable range [2, 7]"

    print("\n✓ Score distribution looks reasonable")

    return True


def test_manual_spot_check():
    """Manually verify score for a specific instrument."""
    print("\n" + "=" * 80)
    print("MANUAL SPOT-CHECK")
    print("=" * 80)

    test_date = date(2024, 1, 31)
    ins_id = 2  # AAK

    print(f"\nManually checking Piotroski F-Score for instrument {ins_id} on {test_date}...")

    # Get individual components
    from factor_investor.factors.queries import get_factor

    print("\nComponent values:")

    components = [
        ("roe_level_raw", "ROE"),
        ("cash_flow_from_operating_activities_level_raw", "OCF"),
        ("gross_margin_level_raw", "Gross Margin"),
        ("asset_turnover_level_raw", "Asset Turnover"),
        ("net_debt_level_raw", "Net Debt"),
        ("current_ratio_level_raw", "Current Ratio"),
    ]

    for metric, name in components:
        try:
            df = get_factor(metric, test_date, instrument_ids=[ins_id])
            if len(df) > 0:
                value = df["value"][0]
                print(f"  {name:20s}: {value:>12.4f}")
            else:
                print(f"  {name:20s}: No data")
        except Exception as e:
            print(f"  {name:20s}: Error - {e}")

    # Get composite score
    df_score = calculate_composite_score("piotroski", test_date, instrument_ids=[ins_id])

    if len(df_score) > 0:
        score = df_score["score"][0]
        label = df_score["score_label"][0]
        print(f"\n✓ Piotroski F-Score: {score}/9 ({label})")
    else:
        print(f"\n✗ No F-Score calculated for instrument {ins_id}")

    return True


if __name__ == "__main__":
    import polars as pl

    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  PIOTROSKI F-SCORE TEST".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    success = True

    # Run tests
    success = success and test_composite_config()
    success = success and test_piotroski_calculation()
    success = success and test_manual_spot_check()

    if success:
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ SOME TESTS FAILED")
        print("=" * 80)
