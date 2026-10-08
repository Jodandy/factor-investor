"""Investigate ROIC value format in fundamentals_pit."""

from datetime import date

from sqlalchemy import text

from factor_investor.db import get_session

# Check Quinsam Capital across multiple dates
ins_id = 21383

query = text("""
    SELECT period_end, period_type, value, known_from
    FROM fundamentals_pit
    WHERE instrument_id = :ins_id
      AND metric = 'roic'
    ORDER BY period_end DESC
    LIMIT 20
""")

print("\n" + "=" * 80)
print(f"ROIC values in fundamentals_pit for instrument {ins_id}")
print("=" * 80)

with get_session() as session:
    result = session.execute(query, {"ins_id": ins_id})
    rows = result.fetchall()

    print(f"\n{'Period End':<12} {'Type':<8} {'Value':>15} {'Value * 100':>15} {'Known From':<12}")
    print("-" * 80)

    for row in rows:
        period_end, period_type, value, known_from = row
        value_float = float(value) if value else 0
        value_pct = value_float * 100

        print(
            f"{str(period_end):<12} {period_type:<8} {value_float:>15.2f} "
            f"{value_pct:>15.2f}% {str(known_from):<12}"
        )

print("\n" + "=" * 80)
print("ANALYSIS:")
print("  If value * 100 gives reasonable % (10-500%) → value is in decimal format")
print("  If value is already % → data format inconsistency!")
print("=" * 80 + "\n")
