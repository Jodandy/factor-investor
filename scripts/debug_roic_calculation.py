"""Debug ROIC calculation for specific companies.

This script investigates why ROIC values seem too low by:
1. Checking raw fundamental data (operating_income, tax, equity, debt)
2. Seeing how ROIC is calculated step-by-step
3. Comparing with expected values
"""

from datetime import date
from decimal import Decimal

import polars as pl
from sqlalchemy import select, text

from factor_investor.db import get_session
from factor_investor.factors.queries import get_factor


def debug_company(ins_id: int, test_date: date):
    """Debug ROIC calculation for a specific company."""

    with get_session() as session:
        # Get company name
        name_result = session.execute(
            text("SELECT name FROM instruments WHERE ins_id = :id"),
            {"id": ins_id}
        ).fetchone()

        if not name_result:
            print(f"❌ Instrument {ins_id} not found")
            return

        company_name = name_result[0]

        print("\n" + "=" * 80)
        print(f"Debugging: {company_name} (ID: {ins_id})")
        print("=" * 80)

        # Get fundamental_metrics for this company around test_date
        query = text("""
            SELECT metric, date, value, known_from
            FROM fundamental_metrics
            WHERE instrument_id = :id
              AND date <= :test_date
              AND metric IN ('roic', 'operating_income', 'profit_to_equity_holders',
                           'profit_before_tax', 'total_equity', 'net_debt')
            ORDER BY date DESC
            LIMIT 50
        """)

        result = session.execute(query, {"id": ins_id, "test_date": test_date})
        rows = result.fetchall()

        if not rows:
            print(f"❌ No fundamental metrics found for {company_name}")
            return

        # Organize by date
        by_date = {}
        for metric, dt, value, known_from in rows:
            if dt not in by_date:
                by_date[dt] = {}
            by_date[dt][metric] = value

        print(f"\nFundamental Data (last 5 dates):")
        print("-" * 80)

        for dt in sorted(by_date.keys(), reverse=True)[:5]:
            data = by_date[dt]
            print(f"\nDate: {dt}")
            print(f"  ROIC:                    {data.get('roic', 'N/A')}")
            print(f"  Operating Income:        {data.get('operating_income', 'N/A')}")
            print(f"  Profit (to equity):      {data.get('profit_to_equity_holders', 'N/A')}")
            print(f"  Profit Before Tax:       {data.get('profit_before_tax', 'N/A')}")
            print(f"  Total Equity:            {data.get('total_equity', 'N/A')}")
            print(f"  Net Debt:                {data.get('net_debt', 'N/A')}")

            # Manual recalculation
            if all(k in data for k in ['operating_income', 'profit_to_equity_holders',
                                       'profit_before_tax', 'total_equity', 'net_debt']):
                operating_income = data['operating_income']
                profit = data['profit_to_equity_holders']
                profit_before_tax = data['profit_before_tax']
                equity = data['total_equity']
                net_debt = data['net_debt']

                print("\n  Manual ROIC Calculation:")

                if profit_before_tax and profit_before_tax > 0:
                    eff_tax = 1 - (profit / profit_before_tax)
                    print(f"    Effective Tax Rate:    {eff_tax:.2%}")

                    if 0 <= eff_tax <= 1:
                        nopat = operating_income * (1 - eff_tax)
                        invested_cap = equity + net_debt

                        print(f"    NOPAT:                 {nopat:,.0f}")
                        print(f"    Invested Capital:      {invested_cap:,.0f}")

                        if invested_cap > 0:
                            roic_calc = nopat / invested_cap
                            print(f"    Calculated ROIC:       {roic_calc:.4f} ({roic_calc:.2%})")
                            print(f"    Stored ROIC:           {data.get('roic', 'N/A')}")
                        else:
                            print(f"    ❌ Invested Capital <= 0")
                    else:
                        print(f"    ❌ Tax Rate out of range [0,1]")
                else:
                    print(f"    ❌ Profit Before Tax <= 0")

        # Get factor values (transformed)
        print("\n" + "=" * 80)
        print("Factor Values (5-year mean, percentile)")
        print("=" * 80)

        try:
            roic_mean_raw = get_factor("roic_mean_5y_raw", test_date, instrument_ids=[ins_id])
            roic_mean_pct = get_factor("roic_mean_5y_pct", test_date, instrument_ids=[ins_id])

            if len(roic_mean_raw) > 0:
                raw_val = roic_mean_raw[0]["value"]
                pct_val = roic_mean_pct[0]["value"] if len(roic_mean_pct) > 0 else "N/A"

                print(f"\nroic_mean_5y_raw:  {raw_val:.4f} ({raw_val:.2%})")
                print(f"roic_mean_5y_pct:  {pct_val}")
            else:
                print("\n❌ No factor data found")
        except Exception as e:
            print(f"\n❌ Error loading factors: {e}")


def main():
    """Debug ROIC for several known companies."""

    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  ROIC Calculation Debugger".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    test_date = date(2020, 12, 31)

    # Companies to investigate (from our backtest)
    companies = [
        13277,  # Insperity (user mentioned this)
        11187,  # InterDigital
        13983,  # Texas Pacific Land Corp
        67471,  # SOS Ltd
        20619,  # Marine Petroleum Trust
    ]

    for ins_id in companies:
        debug_company(ins_id, test_date)

    print("\n" + "=" * 80)
    print("Summary of potential issues:")
    print("=" * 80)
    print("""
Common reasons for None/0 ROIC:
1. profit_before_tax <= 0        → Can't calculate tax rate
2. effective_tax_rate not in [0,1] → Tax calc failed
3. invested_capital <= 0         → Can't divide by zero
4. Missing fundamental data      → Any input is None

Check above to see which case applies to each company.
    """)


if __name__ == "__main__":
    main()
