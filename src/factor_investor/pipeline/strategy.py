"""Pipeline strategy (ARCHITECTURE §2, rebalance clock): universe filters,
weighted score blocks, portfolio component. Stages 3-5 on the daily clock
(timing, entries, exits) are not implemented yet.
"""

from datetime import date

import polars as pl

from factor_investor.backtest.strategy import Strategy, TargetPortfolio
from factor_investor.components.base import (
    SCORE_SCHEMA,
    WEIGHT_SCHEMA,
    FilterComponent,
    PortfolioComponent,
    ScoreComponent,
    build_component,
)
from factor_investor.dates import month_end_dates
from factor_investor.pipeline.config import StrategyConfig
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
    def __init__(self, config: StrategyConfig) -> None:
        from factor_investor.benchmarks.run import AREAS

        self.config = config
        self.area = AREAS[config.area]
        self.filters = [build_component(s.component, s.params) for s in config.universe]
        self.blocks = [
            (build_component(b.component, b.params), b.weight) for b in config.scoring.blocks
        ]
        self.portfolio = build_component(config.portfolio.component, config.portfolio.params)
        assert all(isinstance(f, FilterComponent) for f in self.filters)
        assert all(isinstance(c, ScoreComponent) for c, _ in self.blocks)
        assert isinstance(self.portfolio, PortfolioComponent)

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
        instruments = view.universe().select("instrument_id")
        universe_size = len(instruments)
        for component in self.filters:
            assert isinstance(component, FilterComponent)
            instruments = component.run(view, instruments)
        if instruments.is_empty():
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
        assert isinstance(self.portfolio, PortfolioComponent)
        weights = self.portfolio.run(composite, current)
        return TargetPortfolio(
            weights,
            metadata={
                "universe_size": universe_size,
                "after_filters": len(instruments),
                "scored": int(composite["score"].is_not_null().sum()),
            },
        )
