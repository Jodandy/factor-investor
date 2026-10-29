"""Index-like benchmarks over one market's investable universe.

Benchmarks are ordinary strategies run through the same engine as research
strategies, so they get the same T+1 execution and costs:

- `equal_weight_v1`: every investable name, equal weight, rebalanced monthly.
  The primary benchmark (HYPOTHESES.md).
- `cap_weight_v1`: weighted by market cap, like an index fund, with guards
  against Börsdata share-count errors (DATA_AUDIT "Market Cap and Share
  Counts") and a cap per name.
- `random_pick_v1`: k random investable names, equal weight, seeded.

The investable universe on date T is the eligible universe snapshot for T,
restricted to one country's domestic companies (listed there, trading in its
currency, with its ISIN country code), with one listing per company
(`dedupe_listings_v1`). A region is several such markets in one base
currency: market caps are converted with the exchange rates of date T, and
the backtest runs on prices converted to the base currency
(`load_price_panel(currency=...)`). Everything is read from snapshots and
quotes dated T or earlier.

Benchmarks are not strategy trials: they are not selected by a search, so
they are not logged in the trial registry and do not count towards deflated
Sharpe or PBO.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache

import polars as pl
from sqlalchemy import text

from factor_investor.backtest.strategy import Strategy, TargetPortfolio
from factor_investor.dates import month_end_dates
from factor_investor.db import get_session
from factor_investor.universe.fx import usd_rates
from factor_investor.universe.listings import dedupe_listings_v1
from factor_investor.universe.queries import get_universe

# cap_weight_v1 parameters
MAX_WEIGHT = 0.10
SHARE_JUMP = 10.0  # implied share count vs its trailing median
SHARE_HISTORY_DAYS = 370  # ~12 monthly snapshots, about four quarterly reports
# Market caps above this are data errors (reverse splits applied to prices but
# not to share counts give values up to 4.5e18 USD); the largest company ever
# was worth about 5e12 USD.
MAX_MARKET_CAP_USD = 1e13

WEIGHTS_SCHEMA = {"instrument_id": pl.Int32, "weight": pl.Float64}

WEIGHTINGS = {"equal": "equal_weight_v1", "cap": "cap_weight_v1", "random": "random_pick_v1"}


@dataclass(frozen=True)
class Market:
    """One country's domestic companies: listings in that country, trading in
    its currency, with an ISIN from that country. Foreign companies' local
    listings (Nokia, AstraZeneca and ABB in Stockholm) are left out: their
    market cap is the whole company's, so they would dominate the weights."""

    code: str
    country_id: int
    currency: str


SWEDEN = Market("SE", 1, "SEK")
NORWAY = Market("NO", 2, "NOK")
FINLAND = Market("FI", 3, "EUR")
DENMARK = Market("DK", 4, "DKK")
NORDICS = (SWEDEN, NORWAY, FINLAND, DENMARK)
US = Market("US", 5, "USD")


@dataclass(frozen=True)
class Region:
    """Several markets in one base currency."""

    code: str
    markets: tuple[Market, ...]
    currency: str


# Like Stoxx Europe 600: the Nordics, UK, Switzerland, Poland and the
# Eurozone countries in Börsdata. UK companies with Jersey or Guernsey ISINs
# (Glencore, WPP) are not domestic by the ISIN rule.
EUROPE = Region(
    "EU",
    (
        *NORDICS,
        Market("GB", 7, "GBP"),
        Market("DE", 8, "EUR"),
        Market("FR", 9, "EUR"),
        Market("ES", 10, "EUR"),
        Market("PT", 11, "EUR"),
        Market("IT", 12, "EUR"),
        Market("CH", 13, "CHF"),
        Market("BE", 14, "EUR"),
        Market("NL", 15, "EUR"),
        Market("PL", 17, "PLN"),
    ),
    "EUR",
)


@cache
def _instrument_markets() -> pl.DataFrame:
    with get_session() as session:
        rows = session.execute(
            text("SELECT ins_id, country_id, stock_price_currency, left(isin, 2) FROM instruments")
        ).all()
    return pl.DataFrame(
        rows,
        schema={
            "instrument_id": pl.Int32,
            "country_id": pl.Int64,
            "currency": pl.Utf8,
            "isin_country": pl.Utf8,
        },
        orient="row",
    )


def with_base_currency(universe: pl.DataFrame, rates: dict[str, float], base: str) -> pl.DataFrame:
    """Add `to_base` (base currency per unit of the name's currency) from
    units-per-USD rates; names whose currency has no rate are dropped."""
    to_base = {c: rates[base] / r for c, r in rates.items()} if base in rates else {}
    return universe.with_columns(
        pl.col("currency")
        .replace_strict(to_base, default=None, return_dtype=pl.Float64)
        .alias("to_base")
    ).drop_nulls("to_base")


@cache
def investable_universe(as_of_date: date, area: Market | Region) -> pl.DataFrame:
    """Eligible domestic names in `area` on as_of_date, one listing per company,
    with `to_base` for converting market caps to the area's currency.

    Cached per process: random-pick runs with different seeds share it.
    """
    eligible = get_universe(as_of_date, is_eligible=True)
    if eligible.is_empty():
        return eligible
    markets = area.markets if isinstance(area, Region) else (area,)
    domestic = pl.lit(False)
    for market in markets:
        domestic = domestic | (
            (pl.col("country_id") == market.country_id)
            & (pl.col("currency") == market.currency)
            & (pl.col("isin_country") == market.code)
        )
    in_area = eligible.with_columns(pl.col("instrument_id").cast(pl.Int32)).join(
        _instrument_markets().filter(domestic).drop("isin_country"), on="instrument_id"
    )
    universe = dedupe_listings_v1(in_area, as_of_date).sort("instrument_id")
    if isinstance(area, Market):
        return universe.with_columns(pl.lit(1.0).alias("to_base"))
    return with_base_currency(universe, usd_rates(as_of_date), area.currency)


def trailing_median_shares(as_of_date: date, instrument_ids: list[int]) -> pl.DataFrame:
    """Median implied share count (market cap / price) over the snapshots in
    the SHARE_HISTORY_DAYS before as_of_date, excluding as_of_date itself."""
    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT instrument_id,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY market_cap_local / price)
                FROM universe_constituents
                WHERE date < :as_of AND date >= :oldest
                  AND price > 0 AND market_cap_local > 0
                  AND instrument_id = ANY(:ids)
                GROUP BY instrument_id
            """),
            {
                "as_of": as_of_date,
                "oldest": as_of_date - timedelta(days=SHARE_HISTORY_DAYS),
                "ids": instrument_ids,
            },
        ).all()
    return pl.DataFrame(
        rows, schema={"instrument_id": pl.Int32, "median_shares": pl.Float64}, orient="row"
    )


def equal_weights(universe: pl.DataFrame) -> pl.DataFrame:
    n = len(universe)
    return universe.select(
        pl.col("instrument_id").cast(pl.Int32), pl.lit(1 / n if n else 0.0).alias("weight")
    )


def cap_at(weights: pl.DataFrame, max_weight: float) -> pl.DataFrame:
    """Cap weights at max_weight, handing the excess to the uncapped names in
    proportion to their weight, until none exceeds the cap (if possible)."""
    w = weights["weight"].to_list()
    if not w or max_weight * len(w) < 1:
        return weights
    capped = [False] * len(w)
    while True:
        over = [i for i, x in enumerate(w) if x > max_weight + 1e-12]
        if not over:
            break
        for i in over:
            capped[i] = True
            w[i] = max_weight
        free = [i for i in range(len(w)) if not capped[i]]
        room = 1 - max_weight * sum(capped)
        free_total = sum(w[i] for i in free)
        for i in free:
            w[i] = w[i] / free_total * room
    return weights.with_columns(pl.Series("weight", w, dtype=pl.Float64))


def cap_weights(
    universe: pl.DataFrame, median_shares: pl.DataFrame, max_market_cap: float | None = None
) -> pl.DataFrame:
    """cap_weight_v1 weights from snapshot rows and trailing median share counts.

    Drops names whose market cap is missing, smaller than one day's median
    turnover (impossible, so a data error), whose median turnover is zero (not
    investable; also catches reverse splits applied to prices but not to share
    counts, which inflate market cap by many orders of magnitude), whose market
    cap in the base currency is above `max_market_cap`, or whose implied share
    count is
    more than SHARE_JUMP times away from its trailing median (a report with a
    share count in the wrong unit). Names without history are kept.
    """
    rows = (
        universe.with_columns(pl.col("instrument_id").cast(pl.Int32))
        .join(median_shares, on="instrument_id", how="left")
        .filter(
            (pl.col("market_cap_local") > 0)
            & (pl.col("price") > 0)
            & (
                pl.col("median_turnover_60d").is_null()
                | (
                    (pl.col("median_turnover_60d") > 0)
                    & (pl.col("median_turnover_60d") <= pl.col("market_cap_local"))
                )
            )
        )
        .with_columns((pl.col("market_cap_local") / pl.col("price")).alias("shares"))
        .filter(
            pl.col("median_shares").is_null()
            | (
                (pl.col("shares") / pl.col("median_shares") <= SHARE_JUMP)
                & (pl.col("shares") / pl.col("median_shares") >= 1 / SHARE_JUMP)
            )
        )
    )
    # Market caps in one currency (to_base is 1 within a single market)
    cap = pl.col("market_cap_local") * (pl.col("to_base") if "to_base" in rows.columns else 1.0)
    if max_market_cap is not None:
        rows = rows.filter(cap <= max_market_cap)
    weights = rows.select("instrument_id", (cap / cap.sum()).cast(pl.Float64).alias("weight"))
    return cap_at(weights, MAX_WEIGHT)


def random_pick(universe: pl.DataFrame, k: int, seed: int, as_of_date: date) -> pl.DataFrame:
    """k names drawn uniformly (all of them if fewer), equal weight."""
    ids = sorted(universe["instrument_id"].to_list())
    picked = random.Random(seed * 1_000_003 + as_of_date.toordinal()).sample(ids, min(k, len(ids)))
    return equal_weights(pl.DataFrame({"instrument_id": picked}))


class MarketBenchmark(Strategy):
    """Monthly-rebalanced benchmark over one market's or region's investable
    universe. A region must run on prices in its currency
    (`load_price_panel(currency=region.currency)`).

    weighting: "equal" (equal_weight_v1), "cap" (cap_weight_v1) or
    "random" (random_pick_v1, needs k and seed).
    """

    def __init__(
        self,
        market: Market | Region,
        weighting: str,
        k: int | None = None,
        seed: int | None = None,
        cost_bps: int = 10,
    ) -> None:
        if weighting not in WEIGHTINGS:
            raise ValueError(f"Unknown weighting {weighting!r}")
        if weighting == "random" and (k is None or seed is None):
            raise ValueError("random_pick_v1 needs k and seed")
        self.market = market
        self.weighting = weighting
        self.k = k
        self.seed = seed
        self.cost_bps = cost_bps

    @property
    def benchmark_id(self) -> str:
        return WEIGHTINGS[self.weighting]

    @property
    def name(self) -> str:
        suffix = f" k={self.k} seed={self.seed}" if self.weighting == "random" else ""
        return f"{self.benchmark_id} {self.market.code}{suffix}"

    @property
    def transaction_cost_bps(self) -> int:
        return self.cost_bps

    @property
    def max_position_weight(self) -> float:
        # cap_weight_v1 caps its own weights; the engine must not re-cap
        return 1.0

    def get_rebalancing_dates(self, from_date: date, to_date: date) -> list[date]:
        return month_end_dates(from_date, to_date)

    def generate_signals(
        self,
        as_of_date: date,
        current_holdings: pl.DataFrame | None = None,  # noqa: ARG002
    ) -> TargetPortfolio:
        universe = investable_universe(as_of_date, self.market)
        if universe.is_empty():
            return TargetPortfolio(pl.DataFrame(schema=WEIGHTS_SCHEMA))
        if self.weighting == "equal":
            weights = equal_weights(universe)
        elif self.weighting == "cap":
            ids = universe["instrument_id"].to_list()
            per_usd = usd_rates(as_of_date).get(self.market.currency)
            ceiling = MAX_MARKET_CAP_USD * per_usd if per_usd is not None else None
            weights = cap_weights(universe, trailing_median_shares(as_of_date, ids), ceiling)
        else:
            assert self.k is not None and self.seed is not None
            weights = random_pick(universe, self.k, self.seed, as_of_date)
        return TargetPortfolio(weights, metadata={"universe_size": len(universe)})
