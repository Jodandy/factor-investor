"""Quick verification that ROIC fix is working."""

from datetime import date

from factor_investor.factors.queries import get_factor

# Test specific date and companies
test_date = date(2020, 12, 31)
test_companies = [
    21383,  # Quinsam Capital - should be ~307% (not 29,233%)
    13277,  # Insperity - should be reasonable
    11187,  # InterDigital - should be reasonable
]

print("\n" + "=" * 80)
print("VERIFICATION: ROIC values from new code (using fundamentals_pit)")
print("=" * 80)

# Get ROIC raw values
roic_raw = get_factor("roic_mean_5y_raw", test_date, instrument_ids=test_companies)

print(f"\nDate: {test_date}")
print(f"Factor: roic_mean_5y_raw (5-year mean)")
print(f"\n{'Instr ID':>10} {'ROIC Mean 5Y':>15}")
print("-" * 30)

for row in roic_raw.iter_rows(named=True):
    roic_pct = row['value'] * 100  # Convert to %
    print(f"{row['instrument_id']:>10} {roic_pct:>14.2f}%")

print("\n" + "=" * 80)
print("EXPECTED values (from fundamentals_pit):")
print("  Quinsam Capital (21383): ~307% for 2020-06-30")
print("  Insperity (13277): reasonable values (not 3913%)")
print("  InterDigital (11187): ~10-20% range")
print("\nIf values above match expectations → FIX SUCCESSFUL!")
print("=" * 80 + "\n")
