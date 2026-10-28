"""One listing per company: group listings and pick one per snapshot date.

A company can be listed several times: on several exchanges (Apple in the US,
Warsaw and Milan), as an ADR next to its home listing, or with several share
classes (Volvo A and B). Holding more than one of them doubles the position
in the same company without anyone deciding to.
"""

import re
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date
from functools import cache

import polars as pl
from sqlalchemy import text

from factor_investor.db import get_session
from factor_investor.settings import stock_instrument_types
from factor_investor.universe.fx import usd_rates

# Share class and depositary receipt suffixes: "Volvo B", "Zenith Energy SDR"
SHARE_CLASS_SUFFIX = re.compile(r"\s+(?:A|B|C|D|R|K|SDR|SDB)$")

# Names shared by different companies (Börsdata truncates long names)
NOT_SAME_COMPANY_V1 = frozenset({"Caisse Regionale de Credit"})


@dataclass(frozen=True)
class Listing:
    ins_id: int
    name: str
    country_id: int
    isin: str | None


def company_groups(
    listings: list[Listing], not_same_company: frozenset[str] = frozenset()
) -> dict[int, int]:
    """Group listings of the same company.

    Two listings belong to the same company if they share an ISIN, have the
    same name, or have the same name apart from a share class suffix in the
    same country. Groups chain (Stora Enso A and R in Stockholm and Helsinki
    are one company). Names in not_same_company are not linked by name.

    Uses instrument metadata only, never prices or returns.

    Returns:
        ins_id -> company id (the smallest ins_id in its group)
    """
    parent = {listing.ins_id: listing.ins_id for listing in listings}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def link_by(key: Callable[[Listing], Hashable | None]) -> None:
        first: dict[Hashable, int] = {}
        for listing in listings:
            k = key(listing)
            if k is None:
                continue
            if k in first:
                a, b = find(first[k]), find(listing.ins_id)
                parent[max(a, b)] = min(a, b)
            else:
                first[k] = listing.ins_id

    def by_name(listing: Listing) -> str | None:
        return None if listing.name in not_same_company else listing.name

    def by_share_class(listing: Listing) -> tuple[str, int] | None:
        if listing.name in not_same_company:
            return None
        return (SHARE_CLASS_SUFFIX.sub("", listing.name), listing.country_id)

    link_by(lambda listing: listing.isin or None)
    link_by(by_name)
    link_by(by_share_class)
    return {ins_id: find(ins_id) for ins_id in parent}


def select_one_listing_per_company(
    candidates: pl.DataFrame, company: dict[int, int]
) -> pl.DataFrame:
    """Keep one listing per company among candidates.

    Preference: highest turnover_usd (missing last), then listings trading in
    the company's reporting currency, then the lowest instrument_id.
    Instruments not in company are their own company. Row order is kept.

    Args:
        candidates: instrument_id, turnover_usd, trades_in_report_currency
            (other columns are kept)
        company: ins_id -> company id

    Returns:
        candidates with at most one row per company
    """
    mapping = pl.DataFrame(
        {"instrument_id": list(company), "_company": list(company.values())},
        schema={"instrument_id": candidates.schema["instrument_id"], "_company": pl.Int64},
    )
    return (
        candidates.with_row_index("_row")
        .join(mapping, on="instrument_id", how="left")
        .with_columns(pl.col("_company").fill_null(pl.col("instrument_id").cast(pl.Int64)))
        .sort(
            ["_company", "turnover_usd", "trades_in_report_currency", "instrument_id"],
            descending=[False, True, True, False],
            nulls_last=True,
        )
        .unique(subset="_company", keep="first")
        .sort("_row")
        .drop("_row", "_company")
    )


@cache
def _load_listings() -> tuple[tuple[Listing, ...], dict[int, tuple[str | None, str | None]]]:
    query = text("""
        SELECT ins_id, name, country_id, isin, stock_price_currency, report_currency
        FROM instruments WHERE instrument_type = ANY(:types)
    """)
    with get_session() as session:
        rows = session.execute(query, {"types": stock_instrument_types()}).fetchall()
    listings = tuple(Listing(r[0], r[1], r[2], r[3]) for r in rows)
    currencies = {r[0]: (r[4], r[5]) for r in rows}
    return listings, currencies


def load_company_groups() -> dict[int, int]:
    """Company groups for all stock listings in the database (v1 rules)."""
    listings, _ = _load_listings()
    return company_groups(list(listings), NOT_SAME_COMPANY_V1)


def dedupe_listings_v1(universe: pl.DataFrame, as_of_date: date) -> pl.DataFrame:
    """Universe filter: one listing per company, the most liquid one.

    Liquidity is the 60-day median turnover from the universe snapshot,
    converted to USD at as_of_date's exchange rates. Both are known at
    as_of_date.

    Args:
        universe: Snapshot rows with instrument_id and median_turnover_60d
        as_of_date: Snapshot date

    Returns:
        universe with at most one listing per company
    """
    _, currencies = _load_listings()
    rates = usd_rates(as_of_date)
    ids = universe["instrument_id"].to_list()
    price_ccy = [currencies.get(i, (None, None))[0] for i in ids]
    report_ccy = [currencies.get(i, (None, None))[1] for i in ids]

    candidates = universe.with_columns(
        pl.Series("_rate", [rates.get(c) if c else None for c in price_ccy], dtype=pl.Float64),
        pl.Series(
            "trades_in_report_currency",
            [p is not None and p == r for p, r in zip(price_ccy, report_ccy, strict=True)],
        ),
    ).with_columns((pl.col("median_turnover_60d") / pl.col("_rate")).alias("turnover_usd"))

    kept = select_one_listing_per_company(candidates, load_company_groups())
    return kept.drop("_rate", "trades_in_report_currency", "turnover_usd")
