"""Universe eligibility rules that do not need the database."""

from decimal import Decimal

from factor_investor.universe.config import UniverseConfig, load_universe_config
from factor_investor.universe.universe_service import UniverseService

GERMANY = 8


def test_excluded_country_is_not_eligible() -> None:
    service = UniverseService(UniverseConfig(exclude_country_ids=[GERMANY]))

    assert service._exclusion_reason(GERMANY, Decimal("100")) == "excluded_country"


def test_other_country_is_eligible() -> None:
    service = UniverseService(UniverseConfig(exclude_country_ids=[GERMANY]))

    assert service._exclusion_reason(1, Decimal("100")) is None


def test_low_price_still_excluded() -> None:
    service = UniverseService(UniverseConfig(min_price=5.0))

    assert service._exclusion_reason(1, Decimal("4.99")).startswith("price_too_low")


def test_germany_excluded_in_settings() -> None:
    """German listings are mostly secondary listings of foreign companies
    (4,326 of 6,094 report in non-EUR currencies); excluded by decision."""
    assert GERMANY in load_universe_config().exclude_country_ids
