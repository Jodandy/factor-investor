"""Pipeline strategy (ARCHITECTURE §2): universe filters, weighted score
blocks and a portfolio component on the rebalance clock; optionally timing
signals and exits on the daily clock.

Daily mode (any timing or exit component, or sell_on_rank false):
- on a rebalancing date the portfolio component's selection gives the slots
  (its size) and the candidates in rank order. Holdings outside the selection
  are sold if sell_on_rank. Candidates whose timing signals are all on are
  bought (1/slots each, rank order, up to the free slots); the others wait on
  a watchlist. Kept holdings are resized to 1/slots, as without daily mode.
- every other trading day, after the day's trades: positions track their
  entry price and highest price; exits close positions, and so do exit
  signals that are off (e.g. price below the Ichimoku cloud); watchlist names whose
  signals turn on fill free slots. Untouched positions are kept as they are
  (no daily resizing). A name closed by an exit is not bought again before the
  next rebalancing.
Decisions on day T use prices up to T; the engine executes them from T+1.
"""

from datetime import date
from typing import Any

import polars as pl

from factor_investor.backtest.portfolio import Portfolio
from factor_investor.backtest.strategy import Strategy, TargetPortfolio
from factor_investor.components.base import (
    SCORE_SCHEMA,
    WEIGHT_SCHEMA,
    ExitComponent,
    FilterComponent,
    PortfolioComponent,
    ScoreComponent,
    SignalComponent,
    build_component,
)
from factor_investor.dates import month_end_dates
from factor_investor.pipeline.config import StrategyConfig
from factor_investor.pipeline.daily import DailyPrices, DailyView, daily_prices
from factor_investor.pipeline.view import PointInTimeView

REBALANCE_MONTHS = {
    "monthly": set(range(1, 13)),
    "quarterly": {3, 6, 9, 12},
    "semiannual": {6, 12},
    "annual": {12},
}


def rebalancing_dates(rebalance: str, from_date: date, to_date: date) -> list[date]:
    months = REBALANCE_MONTHS[rebalance]
    return [d for d in month_end_dates(from_date, to_date) if d.month in months]


def combine_scores(blocks: list[tuple[pl.DataFrame, float]], min_coverage: float) -> pl.DataFrame:
    """Weighted mean of the block scores a name has; null if the blocks with a
    score carry less than min_coverage of the total weight."""
    total = sum(weight for _, weight in blocks)
    frame = blocks[0][0].select("instrument_id")
    for i, (scores, _) in enumerate(blocks):
        frame = frame.join(scores.rename({"score": f"s{i}"}), on="instrument_id", how="left")
    weighted = pl.sum_horizontal(
        pl.col(f"s{i}").fill_null(0) * w for i, (_, w) in enumerate(blocks)
    )
    covered = pl.sum_horizontal(
        pl.col(f"s{i}").is_not_null().cast(pl.Float64) * w for i, (_, w) in enumerate(blocks)
    )
    return frame.select(
        "instrument_id",
        pl.when(covered >= min_coverage * total - 1e-12)
        .then(weighted / covered)
        .otherwise(None)
        .alias("score"),
    ).cast(SCORE_SCHEMA)  # type: ignore[arg-type]


class PipelineStrategy(Strategy):
    def __init__(self, config: StrategyConfig, daily: DailyPrices | None = None) -> None:
        from factor_investor.benchmarks.run import AREAS

        self.config = config
        self.area = AREAS[config.area]
        self.filters = [build_component(s.component, s.params) for s in config.universe]
        self.hold = [build_component(s.component, s.params) for s in config.hold]
        self.blocks = [
            (build_component(b.component, b.params), b.weight) for b in config.scoring.blocks
        ]
        self.portfolio = build_component(config.portfolio.component, config.portfolio.params)
        assert all(isinstance(f, FilterComponent) for f in self.filters)
        assert all(isinstance(c, ScoreComponent) for c, _ in self.blocks)
        assert isinstance(self.portfolio, PortfolioComponent)
        self.timing = [build_component(s.component, s.params) for s in config.timing]
        self.exits = [build_component(s.component, s.params) for s in config.exits]
        self.exit_signals = [build_component(s.component, s.params) for s in config.exit_signals]
        self.daily_mode = bool(
            self.timing or self.exits or self.exit_signals or not config.sell_on_rank
        )
        self._daily = daily
        # daily-mode state
        self.slots = 0
        self.slot_weight: float | None = None  # capped portfolios: weight per name
        self.watchlist: list[int] = []
        self.exited: set[int] = set()
        self.positions: dict[int, tuple[float, float]] = {}  # id -> (entry price, high)
        # buys ordered but not yet filled: a new target replaces unfilled
        # orders in the engine, so they are repeated until they are held
        self.ordered: set[int] = set()

    @property
    def uses_daily_clock(self) -> bool:
        return self.daily_mode

    @property
    def daily(self) -> DailyPrices:
        if self._daily is None:
            self._daily = daily_prices(self.config.area)
        return self._daily

    @property
    def name(self) -> str:
        return self.config.id

    @property
    def transaction_cost_bps(self) -> int:
        return self.config.cost_bps

    @property
    def max_position_weight(self) -> float:
        return 1.0

    def get_rebalancing_dates(self, from_date: date, to_date: date) -> list[date]:
        return rebalancing_dates(self.config.rebalance, from_date, to_date)

    def generate_signals(
        self, as_of_date: date, current_holdings: pl.DataFrame | None = None
    ) -> TargetPortfolio:
        view = PointInTimeView(as_of_date, self.area)
        investable = view.universe().select("instrument_id")
        instruments = investable
        universe_size = len(instruments)
        for component in self.filters:
            assert isinstance(component, FilterComponent)
            instruments = component.run(view, instruments)
        if instruments.is_empty() and not self.hold:
            return TargetPortfolio(pl.DataFrame(schema=WEIGHT_SCHEMA))
        scores = []
        for component, weight in self.blocks:
            assert isinstance(component, ScoreComponent)
            scores.append((component.run(view, instruments), weight))
        composite = combine_scores(scores, self.config.scoring.min_coverage)
        current = (
            current_holdings["instrument_id"].to_list()
            if current_holdings is not None and not current_holdings.is_empty()
            else []
        )
        if self.hold and current:
            # held names that pass the hold rules outrank every buy candidate
            holding = investable.filter(pl.col("instrument_id").is_in(current))
            for component in self.hold:
                assert isinstance(component, FilterComponent)
                holding = component.run(view, holding)
            composite = pl.concat(
                [
                    composite.filter(
                        ~pl.col("instrument_id").is_in(holding["instrument_id"].implode())
                    ),
                    holding.select(
                        pl.col("instrument_id").cast(pl.Int32), pl.lit(2.0).alias("score")
                    ),
                ]
            )
        assert isinstance(self.portfolio, PortfolioComponent)
        weights = self.portfolio.run(composite, current)
        metadata = {
            "universe_size": universe_size,
            "after_filters": len(instruments),
            "scored": int(composite["score"].is_not_null().sum()),
        }
        # a capped portfolio (weights summing to less than 1) keeps its cash
        fully_invested = float(weights["weight"].sum()) >= 1 - 1e-9 if len(weights) else True
        if not self.daily_mode:
            return TargetPortfolio(weights, metadata=metadata, normalize=fully_invested)

        rank = dict(composite.drop_nulls("score").select("instrument_id", "score").rows())
        selection = sorted(weights["instrument_id"].to_list(), key=lambda i: (-rank[i], i))
        held = set(current)
        kept = [i for i in current if i in selection] if self.config.sell_on_rank else list(current)
        self.slots = len(selection)
        self.slot_weight = None if fully_invested else float(weights["weight"].to_list()[0])
        self.exited = set()
        candidates = [i for i in selection if i not in held]
        buys = self._entries(as_of_date, candidates, self.slots - len(kept))
        self.watchlist = [i for i in candidates if i not in buys]
        self.ordered = set(buys)
        metadata["watchlist"] = len(self.watchlist)
        return self._target(kept + buys, keep=frozenset(), metadata=metadata)

    def _entries(self, as_of: date, candidates: list[int], free: int) -> list[int]:
        """Up to `free` candidates, in order, whose timing signals are all on."""
        if free <= 0 or not candidates:
            return []
        on = set(candidates)
        view = DailyView(self.daily, as_of)
        for component in self.timing:
            assert isinstance(component, SignalComponent)
            on &= component.run(view, candidates)
        return [i for i in candidates if i in on][:free]

    def _target(
        self, names: list[int], keep: frozenset[int], metadata: dict[str, Any] | None = None
    ) -> TargetPortfolio:
        # 1/slots of portfolio value, normalized by the engine's own function as
        # for a full equal-weight target, so a fully invested daily-mode
        # portfolio is bit-identical to the plain strategy
        weight = (
            self.slot_weight
            if self.slot_weight is not None
            else Portfolio.normalize_weights(
                pl.DataFrame({"weight": [1 / self.slots] * self.slots}), 1.0
            )["weight"][0]
            if self.slots
            else 0.0
        )
        return TargetPortfolio(
            pl.DataFrame(
                {"instrument_id": names, "weight": [weight] * len(names)}, schema=WEIGHT_SCHEMA
            ),
            metadata=metadata,
            keep=keep,
            normalize=False,
        )

    def on_day(self, as_of_date: date, holdings: pl.DataFrame) -> TargetPortfolio | None:
        if not self.daily_mode:
            return None
        prices = dict(holdings.select("instrument_id", "price").rows())
        # entry price and highest price since entry, for every position held today
        positions = {}
        for i, price in prices.items():
            entry, high = self.positions.get(i, (price, price))
            positions[i] = (entry, max(high, price))
        self.positions = positions
        closing: set[int] = set()
        if self.exits and self.positions:
            frame = pl.DataFrame(
                [(i, e, h, prices[i]) for i, (e, h) in self.positions.items()],
                schema={
                    "instrument_id": pl.Int32,
                    "entry_price": pl.Float64,
                    "high": pl.Float64,
                    "price": pl.Float64,
                },
                orient="row",
            )
            for component in self.exits:
                assert isinstance(component, ExitComponent)
                closing |= component.run(frame)
        if self.exit_signals and prices:
            held_ids = sorted(prices)
            view = DailyView(self.daily, as_of_date)
            for signal in self.exit_signals:
                assert isinstance(signal, SignalComponent)
                closing |= set(held_ids) - signal.run(view, held_ids)
        held = set(prices)
        self.ordered -= held
        candidates = [i for i in self.watchlist if i not in held and i not in self.exited]
        free = self.slots - (len(held) - len(closing)) - len(self.ordered)
        buys = self._entries(as_of_date, candidates, free)
        if not closing and not buys:
            return None
        self.exited |= closing
        self.watchlist = [i for i in self.watchlist if i not in buys]
        self.ordered |= set(buys)
        return self._target(sorted(self.ordered), keep=frozenset(held - closing))
