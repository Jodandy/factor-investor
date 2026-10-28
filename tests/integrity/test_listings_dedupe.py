"""dedupe_listings_v1 on real universe snapshots (needs the database)."""

from datetime import date, timedelta

import polars as pl
import pytest

from factor_investor.universe.fx import usd_rates
from factor_investor.universe.listings import dedupe_listings_v1, load_company_groups
from factor_investor.universe.queries import get_universe

SNAPSHOT = date(2024, 12, 31)
APPLE_US, APPLE_PL = 10214, 59788
VOLVO_A, VOLVO_B = 1640, 236


@pytest.fixture(scope="module")
def deduped() -> pl.DataFrame:
    return dedupe_listings_v1(get_universe(SNAPSHOT, is_eligible=True), SNAPSHOT)


def test_one_listing_per_company(deduped: pl.DataFrame) -> None:
    company = load_company_groups()
    companies = [company.get(i, i) for i in deduped["instrument_id"].to_list()]

    assert len(companies) == len(set(companies))


def test_removes_duplicates_but_keeps_most_of_universe(deduped: pl.DataFrame) -> None:
    eligible = get_universe(SNAPSHOT, is_eligible=True)

    assert 0.9 * len(eligible) < len(deduped) < len(eligible)


def test_keeps_most_liquid_listing(deduped: pl.DataFrame) -> None:
    kept = set(deduped["instrument_id"].to_list())

    assert APPLE_US in kept and APPLE_PL not in kept
    assert VOLVO_B in kept and VOLVO_A not in kept


def test_fx_rates_known_at_date() -> None:
    """Rates are each pair's last close on or before the date."""
    rates = usd_rates(SNAPSHOT)

    assert rates["USD"] == 1.0
    assert rates["SEK"] == pytest.approx(11.0217)
    assert set(rates) >= {"CAD", "CHF", "DKK", "EUR", "GBP", "NOK", "PLN", "SEK"}


def test_fx_rates_never_from_after_date() -> None:
    """With no quote on Sunday, the previous quote is used, not Monday's."""
    sunday = date(2024, 12, 29)

    assert usd_rates(sunday) == usd_rates(sunday - timedelta(days=1))
    assert usd_rates(sunday) != usd_rates(sunday + timedelta(days=1))
