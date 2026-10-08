"""Spot check ROIC for individual years (no averages)."""

from datetime import date

from factor_investor.factors.queries import get_factor

# Test specific date and companies
test_date = date(2024, 12, 31)
test_companies = [
    21383,  # Quinsam Capital
    13277,  # Insperity
    11187,  # InterDigital
    13983,  # Texas Pacific Land
]

print("\n" + "=" * 80)
print("SPOT CHECK: ROIC for individual years (latest available)")
print("=" * 80)

# Get ROIC level (latest value, not mean)
roic_level = get_factor("roic_level_raw", test_date, instrument_ids=test_companies)

print(f"\nDate: {test_date}")
print(f"Factor: roic_level_raw (latest reported ROIC)")
print(f"\n{'Instr ID':>10} {'Company':<30} {'ROIC':>12}")
print("-" * 60)

company_names = {
    21383: "Quinsam Capital Corp",
    13277: "Insperity Inc",
    11187: "InterDigital Inc",
    13983: "Texas Pacific Land Corp",
}

for row in roic_level.sort("instrument_id").iter_rows(named=True):
    ins_id = row['instrument_id']
    roic_pct = row['value'] * 100  # Convert to %
    name = company_names.get(ins_id, "Unknown")
    print(f"{ins_id:>10} {name:<30} {roic_pct:>11.2f}%")

print("\n" + "=" * 80)
print("Manuell verifiering mot Börsdata eller årsredovisningar:")
print("  - Kolla om dessa värden stämmer med officiella siffror")
print("  - Om de stämmer → FIX SUCCESSFUL!")
print("=" * 80 + "\n")
