"""Debug what we get from PIT query."""

from datetime import date

from factor_investor.pit.queries import as_of

# Test one company
test_date = date(2020, 12, 31)
test_company = 21383  # Quinsam Capital

print("\n" + "=" * 80)
print(f"DEBUG: PIT query for Quinsam Capital (ID: {test_company})")
print("=" * 80)

# Get PIT data
pit_df = as_of(
    as_of_date=test_date,
    instrument_ids=[test_company],
    metrics=["roic"],
    history_years=5,
)

print(f"\nPIT data as of {test_date}:")
print(pit_df)

print("\n" + "=" * 80)
print("EXPECTED: Should see ~307% for period_end 2020-06-30")
print("=" * 80 + "\n")
