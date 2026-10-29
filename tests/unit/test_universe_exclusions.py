"""Universe eligibility rules that do not need the database."""

from decimal import Decimal

from factor_investor.universe.config import UniverseConfig, load_universe_config
from factor_investor.universe.universe_service import UniverseService

GERMANY = 8


def test_excluded_country_is_not_eligible() -> None:
    service = UniverseService(UniverseConfig(exclude_country_ids=[GERMANY]))

    assert service._exclusion_reason(GERMANY, Decimal("100"), "Siemens") == "excluded_country"


def test_other_country_is_eligible() -> None:
    service = UniverseService(UniverseConfig(exclude_country_ids=[GERMANY]))

    assert service._exclusion_reason(1, Decimal("100"), "Volvo B") is None


def test_low_price_is_eligible_by_default() -> None:
    """Prices are split-adjusted, so a price threshold would exclude stocks
    based on splits made later (Hexagon: 4.75 SEK adjusted in 2008, about
    60 SEK actual). Minimum price is opt-in."""
    assert load_universe_config().min_price is None
    service = UniverseService(UniverseConfig())

    assert service._exclusion_reason(1, Decimal("0.5"), "Hexagon") is None


def test_min_price_still_works_when_set() -> None:
    service = UniverseService(UniverseConfig(min_price=5.0))

    assert service._exclusion_reason(1, Decimal("4.99"), "Hexagon").startswith("price_too_low")


def test_d_shares_are_not_eligible() -> None:
    """Swedish property companies' D shares are preference-like (capped upside)."""
    service = UniverseService(load_universe_config())

    assert service._exclusion_reason(1, Decimal("200"), "Sagax D") == "d_share"
    assert service._exclusion_reason(1, Decimal("200"), "Corem Property D") == "d_share"
    assert service._exclusion_reason(1, Decimal("200"), "Sagax B") is None
    assert service._exclusion_reason(1, Decimal("200"), "Dometic Group") is None


def test_germany_excluded_in_settings() -> None:
    """German listings are mostly secondary listings of foreign companies
    (4,326 of 6,094 report in non-EUR currencies); excluded by decision."""
    assert GERMANY in load_universe_config().exclude_country_ids
