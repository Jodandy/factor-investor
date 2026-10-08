"""Compare ROIC from fundamentals_pit vs fundamental_metrics.

This checks which source has correct/better ROIC data.
"""

from datetime import date

from sqlalchemy import text

from factor_investor.db import get_session


def compare_roic(ins_id: int, company_name: str, test_date: date):
    """Compare ROIC from both tables."""

    print(f"\n{'=' * 80}")
    print(f"{company_name} (ID: {ins_id})")
    print(f"{'=' * 80}")

    with get_session() as session:
        # Get from fundamentals_pit
        pit_roic = session.execute(
            text("""
                SELECT period_end, value, known_from
                FROM fundamentals_pit
                WHERE instrument_id = :id
                  AND metric = 'roic'
                  AND period_end <= :test_date
                ORDER BY period_end DESC
                LIMIT 5
            """),
            {"id": ins_id, "test_date": test_date}
        ).fetchall()

        # Get from fundamental_metrics
        fm_roic = session.execute(
            text("""
                SELECT date, value, known_from
                FROM fundamental_metrics
                WHERE instrument_id = :id
                  AND metric = 'roic'
                  AND date <= :test_date
                ORDER BY date DESC
                LIMIT 5
            """),
            {"id": ins_id, "test_date": test_date}
        ).fetchall()

        print(f"\nfundamentals_pit (PIT data):")
        print(f"{'Date':<15} {'ROIC':>10} {'Known From':<15}")
        print("-" * 45)
        for row in pit_roic:
            roic_pct = float(row[1]) * 100 if row[1] else None
            print(f"{str(row[0]):<15} {roic_pct:>9.2f}% {str(row[2]):<15}")

        print(f"\nfundamental_metrics (Base metrics table):")
        print(f"{'Date':<15} {'ROIC':>10} {'Known From':<15}")
        print("-" * 45)
        for row in fm_roic:
            roic_pct = float(row[1]) * 100 if row[1] else None
            print(f"{str(row[0]):<15} {roic_pct:>9.2f}% {str(row[2]):<15}")


def main():
    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  ROIC Source Comparison".center(78) + "║")
    print("║" + "  fundamentals_pit vs fundamental_metrics".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    test_date = date(2020, 12, 31)

    companies = [
        (13277, "Insperity Inc"),
        (11187, "InterDigital Inc"),
        (13983, "Texas Pacific Land Corp"),
        (67471, "SOS Ltd"),
        (21383, "Quinsam Capital Corp"),
    ]

    for ins_id, name in companies:
        compare_roic(ins_id, name, test_date)

    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)
    print("""
If fundamentals_pit has ROIC but fundamental_metrics doesn't (or has different values):
→ The issue is with how we built fundamental_metrics in Fas 4.1

SOLUTION:
Either:
1. Use fundamentals_pit directly (it's already PIT data with roic)
2. Copy ALL metrics from fundamentals_pit to fundamental_metrics
3. Fix the fundamental_metrics build process to include all needed inputs
    """)


if __name__ == "__main__":
    main()
