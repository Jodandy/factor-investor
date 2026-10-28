"""Grouping listings into companies and keeping one listing per company."""

import polars as pl

from factor_investor.universe.listings import (
    Listing,
    company_groups,
    select_one_listing_per_company,
)

SWEDEN, FINLAND, USA, ITALY, POLAND, FRANCE = 1, 3, 5, 12, 17, 9


def groups_of(
    listings: list[Listing], not_same_company: frozenset[str] = frozenset()
) -> set[frozenset[int]]:
    company = company_groups(listings, not_same_company)
    members: dict[int, set[int]] = {}
    for ins_id, company_id in company.items():
        members.setdefault(company_id, set()).add(ins_id)
    return {frozenset(m) for m in members.values()}


class TestCompanyGroups:
    def test_cross_listings_with_same_name_are_one_company(self) -> None:
        """Apple's Warsaw and Milan listings have no ISIN."""
        listings = [
            Listing(10214, "Apple Inc", USA, "US0378331005"),
            Listing(65843, "Apple Inc", ITALY, None),
            Listing(59788, "Apple Inc", POLAND, None),
        ]
        assert groups_of(listings) == {frozenset({10214, 65843, 59788})}

    def test_same_isin_is_one_company_even_with_different_names(self) -> None:
        listings = [
            Listing(224, "Tieto", SWEDEN, "FI0009000277"),
            Listing(698, "TietoEVRY", FINLAND, "FI0009000277"),
        ]
        assert groups_of(listings) == {frozenset({224, 698})}

    def test_share_classes_in_same_country_are_one_company(self) -> None:
        listings = [
            Listing(1640, "Volvo A", SWEDEN, "SE0000115420"),
            Listing(236, "Volvo B", SWEDEN, "SE0000115446"),
        ]
        assert groups_of(listings) == {frozenset({1640, 236})}

    def test_share_classes_and_cross_listings_chain(self) -> None:
        """Stora Enso A and R, each listed in Stockholm and Helsinki with
        exchange-specific ISINs."""
        listings = [
            Listing(1, "Stora Enso A", SWEDEN, "FI0009007603"),
            Listing(2, "Stora Enso R", SWEDEN, "FI0009007611"),
            Listing(3, "Stora Enso A", FINLAND, "FI0009005953"),
            Listing(4, "Stora Enso R", FINLAND, "FI0009005961"),
        ]
        assert groups_of(listings) == {frozenset({1, 2, 3, 4})}

    def test_depositary_receipt_suffix_is_a_share_class(self) -> None:
        listings = [
            Listing(1, "Zenith Energy", SWEDEN, None),
            Listing(2, "Zenith Energy SDR", SWEDEN, None),
        ]
        assert groups_of(listings) == {frozenset({1, 2})}

    def test_share_class_suffix_in_different_countries_is_not_merged(self) -> None:
        listings = [
            Listing(1, "Atlas A", SWEDEN, None),
            Listing(2, "Atlas B", FINLAND, None),
        ]
        assert groups_of(listings) == {frozenset({1}), frozenset({2})}

    def test_truncated_names_of_different_companies_can_be_kept_apart(self) -> None:
        listings = [
            Listing(1, "Caisse Regionale de Credit", FRANCE, "FR0000045528"),
            Listing(2, "Caisse Regionale de Credit", FRANCE, "FR0010483768"),
        ]
        separate = groups_of(listings, frozenset({"Caisse Regionale de Credit"}))

        assert separate == {frozenset({1}), frozenset({2})}

    def test_unrelated_listings_stay_separate(self) -> None:
        listings = [Listing(1, "AAK", SWEDEN, None), Listing(2, "ABB", SWEDEN, None)]
        assert groups_of(listings) == {frozenset({1}), frozenset({2})}


def candidates(rows: list[tuple[int, float | None, bool]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "instrument_id": pl.Int64,
            "turnover_usd": pl.Float64,
            "trades_in_report_currency": pl.Boolean,
        },
        orient="row",
    )


COMPANY = {10214: 10214, 59788: 10214, 65843: 10214, 2: 2}


class TestSelectOneListing:
    def test_keeps_most_liquid_listing(self) -> None:
        df = candidates(
            [(10214, 1e10, True), (59788, 1e6, False), (65843, 2e6, False), (2, 5e5, True)]
        )

        kept = select_one_listing_per_company(df, COMPANY)

        assert sorted(kept["instrument_id"].to_list()) == [2, 10214]

    def test_missing_turnover_prefers_report_currency(self) -> None:
        df = candidates([(59788, None, False), (10214, None, True)])

        assert select_one_listing_per_company(df, COMPANY)["instrument_id"].to_list() == [10214]

    def test_known_turnover_beats_missing(self) -> None:
        df = candidates([(10214, None, True), (59788, 1e3, False)])

        assert select_one_listing_per_company(df, COMPANY)["instrument_id"].to_list() == [59788]

    def test_instrument_without_group_is_its_own_company(self) -> None:
        df = candidates([(999, None, True), (2, 1.0, True)])

        assert sorted(select_one_listing_per_company(df, COMPANY)["instrument_id"].to_list()) == [
            2,
            999,
        ]

    def test_tie_is_deterministic(self) -> None:
        df = candidates([(65843, 5.0, False), (59788, 5.0, False)])

        assert select_one_listing_per_company(df, COMPANY)["instrument_id"].to_list() == [59788]

    def test_keeps_other_columns(self) -> None:
        df = candidates([(2, 1.0, True)]).with_columns(pl.lit(42).alias("score"))

        assert select_one_listing_per_company(df, COMPANY)["score"].to_list() == [42]
