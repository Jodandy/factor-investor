"""Parsing /v1/instruments/dividend/calendar responses (shape checked 2026-10-29)."""

from datetime import date

from factor_investor.ingest.sync import parse_dividend_calendar


def value(ex: str | None, amount: float | None, kind: int = 0) -> dict:
    return {
        "amountPaid": amount,
        "currencyShortName": "SEK",
        "distributionFrequency": None,
        "excludingDate": ex,
        "dividendType": kind,
    }


def test_parses_rows_per_instrument() -> None:
    data = {
        "list": [
            {"insId": 236, "values": [value("2026-04-09T00:00:00", 8.5), value("2026-04-09T00:00:00", 4.5, 1)]},
            {"insId": 113, "values": [value("2010-04-15T00:00:00", 4.0)]},
        ]
    }

    rows = parse_dividend_calendar(data)

    assert {(r["ins_id"], r["ex_date"], r["dividend_type"], r["amount_paid"]) for r in rows} == {
        (236, date(2026, 4, 9), 0, 8.5),
        (236, date(2026, 4, 9), 1, 4.5),
        (113, date(2010, 4, 15), 0, 4.0),
    }
    assert all(r["currency"] == "SEK" for r in rows)


def test_same_key_is_summed_and_missing_dates_skipped() -> None:
    data = {
        "list": [
            {
                "insId": 1,
                "values": [
                    value("2020-05-01T00:00:00", 1.0),
                    value("2020-05-01T00:00:00", 0.5),
                    value(None, 9.0),
                ],
            }
        ]
    }

    rows = parse_dividend_calendar(data)

    assert len(rows) == 1
    assert rows[0]["amount_paid"] == 1.5


def test_empty_response() -> None:
    assert parse_dividend_calendar({"list": [{"insId": 1, "values": None}]}) == []
    assert parse_dividend_calendar({}) == []
