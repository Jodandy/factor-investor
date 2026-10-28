"""Which Börsdata instrument types are synced and can enter the universe.

Type meanings are inferred from example names (DATA_AUDIT "Instrument Types").
"""

from factor_investor.settings import price_only_instrument_types, stock_instrument_types

ORDINARY, SHARE_CLASS, ADR = 0, 3, 9
INDEX, SECTOR_INDEX, INDUSTRY_INDEX, FX, US_INDEX, GROSS_INDEX = 2, 4, 5, 6, 11, 13
PREF, COMMODITY, SPAC, UNIT, CRYPTO = 1, 7, 8, 10, 12


def test_stock_types() -> None:
    assert set(stock_instrument_types()) == {ORDINARY, SHARE_CLASS, ADR}


def test_indices_and_fx_are_price_only() -> None:
    assert set(price_only_instrument_types()) == {
        INDEX, SECTOR_INDEX, INDUSTRY_INDEX, FX, US_INDEX, GROSS_INDEX
    }


def test_other_types_are_not_synced() -> None:
    synced = set(stock_instrument_types()) | set(price_only_instrument_types())

    assert synced.isdisjoint({PREF, COMMODITY, SPAC, UNIT, CRYPTO})
