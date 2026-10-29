"""Universe eligibility rules that do not need the database."""

from decimal import Decimal

from factor_investor.universe.config import UniverseConfig, load_universe_config
from factor_investor.universe.universe_service import UniverseService

GERMANY = 8


def test_excluded_country_is_not_eligible() -> None:
    service = UniverseService(UniverseConfig(exclude_country_ids=[GERMANY]))

    assert service._exclusion_reason(GERMANY, Decimal("100"), "Siemens", "DE0007236101") == "excluded_country"


def test_other_country_is_eligible() -> None:
    service = UniverseService(UniverseConfig(exclude_country_ids=[GERMANY]))

    assert service._exclusion_reason(1, Decimal("100"), "Volvo B", None) is None


def test_low_price_is_eligible_by_default() -> None:
    """Prices are split-adjusted, so a price threshold would exclude stocks
    based on splits made later (Hexagon: 4.75 SEK adjusted in 2008, about
    60 SEK actual). Minimum price is opt-in."""
    assert load_universe_config().min_price is None
    service = UniverseService(UniverseConfig())

    assert service._exclusion_reason(1, Decimal("0.5"), "Hexagon", None) is None


def test_min_price_still_works_when_set() -> None:
    service = UniverseService(UniverseConfig(min_price=5.0))

    assert service._exclusion_reason(1, Decimal("4.99"), "Hexagon", None).startswith("price_too_low")


def test_d_shares_are_not_eligible() -> None:
    """Swedish property companies' D shares are preference-like (capped upside)."""
    service = UniverseService(load_universe_config())

    assert service._exclusion_reason(1, Decimal("200"), "Sagax D", None) == "d_share"
    assert service._exclusion_reason(1, Decimal("200"), "Corem Property D", None) == "d_share"
    assert service._exclusion_reason(1, Decimal("200"), "Sagax B", None) is None
    assert service._exclusion_reason(1, Decimal("200"), "Dometic Group", None) is None


def test_only_german_companies_are_eligible_in_germany() -> None:
    """German listings are mostly secondary listings of foreign companies
    (4,326 of 6,094 report in non-EUR currencies). Only listings with a German
    ISIN are eligible (SAP, Siemens, Allianz)."""
    config = load_universe_config()
    assert GERMANY not in config.exclude_country_ids
    assert config.domestic_only == {GERMANY: "DE"}
    service = UniverseService(config)

    assert service._exclusion_reason(GERMANY, Decimal("200"), "SAP SE", "DE0007164600") is None
    assert (
        service._exclusion_reason(GERMANY, Decimal("200"), "Apple Inc", "US0378331005")
        == "foreign_listing"
    )
    assert service._exclusion_reason(GERMANY, Decimal("200"), "Unknown", None) == "foreign_listing"


def test_domestic_rule_applies_only_to_listed_countries() -> None:
    """Swedish listings of foreign companies (Nokia) stay eligible; benchmarks
    and strategies choose their own universe."""
    service = UniverseService(load_universe_config())
    assert service._exclusion_reason(1, Decimal("50"), "Nokia Oyj", "FI0009000681") is None
