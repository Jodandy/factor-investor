"""Generic strategy interface for backtesting.

This module defines the abstract Strategy interface that all concrete strategies
must implement. The interface is intentionally minimal to support diverse
strategy types (factor-based, technical, ML-based, etc.).

The BacktestEngine only cares about:
1. What instruments to hold (and at what weights)
2. When to rebalance

Everything else (factor selection, ranking, filtering) is strategy-specific.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)


@dataclass
class TargetPortfolio:
    """Target portfolio weights for rebalancing.

    This is the output of a strategy's generate_signals() method.
    The BacktestEngine uses this to rebalance the portfolio.

    Attributes:
        holdings: DataFrame with columns [instrument_id, weight]
                  Weights should sum to ~1.0 (or fraction of capital to deploy)
        metadata: Optional metadata about the signal generation
                  (e.g., factor scores, rankings, filters applied)
        keep: Held instruments to leave untouched (neither sold nor resized).
              Holdings that are neither in `holdings` nor in `keep` are sold.
        normalize: If True (default), weights are capped and rescaled to sum
              1. If False they are fractions of portfolio value as given (for
              targets that add or remove positions next to kept ones).
    """

    holdings: pl.DataFrame  # [instrument_id, weight]
    metadata: dict[str, Any] | None = None
    keep: frozenset[int] = frozenset()
    normalize: bool = True

    def __post_init__(self):
        """Validate holdings DataFrame."""
        required_cols = {"instrument_id", "weight"}
        actual_cols = set(self.holdings.columns)

        if not required_cols.issubset(actual_cols):
            raise ValueError(
                f"Holdings must have columns {required_cols}, got {actual_cols}"
            )

        # Check weights sum to reasonable value (allow empty portfolio)
        if len(self.holdings) > 0:
            total_weight = self.holdings["weight"].sum()
            if total_weight <= 0 or total_weight > 1.5:
                raise ValueError(
                    f"Total weight {total_weight:.2f} outside reasonable range (0, 1.5]"
                )


class Strategy(ABC):
    """Abstract base class for all trading strategies.

    A Strategy defines:
    1. WHAT to hold (which instruments, at what weights)
    2. WHEN to rebalance (via rebalancing_dates)

    It does NOT define:
    - HOW to execute trades (BacktestEngine handles this)
    - HOW to calculate performance (BacktestEngine handles this)
    - HOW to handle costs (BacktestEngine handles this)

    This separation allows the BacktestEngine to be completely generic.
    """

    @abstractmethod
    def generate_signals(
        self, as_of_date: date, current_holdings: pl.DataFrame | None = None
    ) -> TargetPortfolio:
        """Generate target portfolio for a rebalancing date.

        This is the core strategy logic. Given a date (and optionally current
        holdings), return the desired portfolio weights.

        Args:
            as_of_date: Rebalancing date
            current_holdings: Optional current holdings [instrument_id, weight, value]
                             Useful for strategies that care about current positions

        Returns:
            TargetPortfolio with desired holdings

        Example:
            >>> # Long-only factor strategy
            >>> def generate_signals(self, as_of_date, current_holdings=None):
            ...     # Get factor scores
            ...     factor_df = get_factor("roic_mean_5y_pct", as_of_date)
            ...
            ...     # Rank and select top 30
            ...     top_30 = factor_df.sort("value", descending=True).head(30)
            ...
            ...     # Equal weight
            ...     holdings = top_30.with_columns(
            ...         pl.lit(1.0 / 30).alias("weight")
            ...     ).select(["instrument_id", "weight"])
            ...
            ...     return TargetPortfolio(holdings=holdings)
        """
        pass

    @abstractmethod
    def get_rebalancing_dates(self, from_date: date, to_date: date) -> list[date]:
        """Get all rebalancing dates in the backtest period.

        Args:
            from_date: Backtest start date
            to_date: Backtest end date

        Returns:
            List of dates when portfolio should be rebalanced

        Example:
            >>> # Annual rebalancing on Jan 31
            >>> def get_rebalancing_dates(self, from_date, to_date):
            ...     dates = []
            ...     year = from_date.year
            ...     while True:
            ...         rebal_date = date(year, 1, 31)
            ...         if rebal_date > to_date:
            ...             break
            ...         if rebal_date >= from_date:
            ...             dates.append(rebal_date)
            ...         year += 1
            ...     return dates
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for reporting.

        Returns:
            Human-readable strategy name

        Example:
            >>> return "ROIC Quality (Top 30, Annual)"
        """
        pass

    @property
    def description(self) -> str:
        """Optional detailed strategy description.

        Returns:
            Strategy description (default: empty string)
        """
        return ""

    @property
    def transaction_cost_bps(self) -> int:
        """Transaction cost in basis points per trade.

        Returns:
            Cost in bps (default: 10 bps = 0.10%)

        Note: Can be overridden by BacktestEngine config
        """
        return 10

    @property
    def max_position_weight(self) -> float:
        """Maximum weight per position (risk management).

        Returns:
            Max weight (default: 0.10 = 10%)

        Note: Can be overridden by BacktestEngine config
        """
        return 0.10

    @property
    def uses_daily_clock(self) -> bool:
        """Whether the engine should call on_day (default: if it is overridden)."""
        return type(self).on_day is not Strategy.on_day

    def on_day(
        self,
        as_of_date: date,  # noqa: ARG002
        holdings: pl.DataFrame,  # noqa: ARG002
    ) -> "TargetPortfolio | None":
        """Optional daily hook (the daily clock, ARCHITECTURE §2 stages 3-5).

        Called at the end of every trading day except days with a rebalancing
        signal, after that day's trades, with the holdings
        [instrument_id, shares, price, value, weight]. It may use data up to
        as_of_date only. A returned target is executed like a rebalancing
        signal: from the next trading day, per instrument. Holdings not in the
        target and not in its `keep` set are sold. Strategies that do not
        override it are never called.
        """
        return None

    def on_rebalance(
        self,
        rebal_date: date,
        old_holdings: pl.DataFrame,
        new_holdings: pl.DataFrame,
        trades: pl.DataFrame,
    ) -> None:
        """Optional callback after rebalancing.

        Useful for strategies that want to track state, log information,
        or perform additional analysis at rebalancing.

        Args:
            rebal_date: Rebalancing date
            old_holdings: Holdings before rebalancing
            new_holdings: Holdings after rebalancing
            trades: Trades executed [instrument_id, action, shares, price, cost]

        Example:
            >>> def on_rebalance(self, rebal_date, old_holdings, new_holdings, trades):
            ...     print(f"Rebalanced on {rebal_date}: {len(trades)} trades")
        """
        pass


class LongOnlyFactorStrategy(Strategy):
    """Long-only strategy based on factor ranking.

    This is a simple but flexible implementation that demonstrates how to
    use the Strategy interface. It supports:
    - Single or multiple factors (with weights)
    - Equal weight or factor-weighted positions
    - Flexible rebalancing frequency
    - Universe filters (market cap, liquidity, etc.)

    Example:
        >>> # Simple ROIC strategy
        >>> strategy = LongOnlyFactorStrategy(
        ...     name="ROIC Quality",
        ...     factors={"roic_mean_5y_pct": 1.0},
        ...     num_positions=30,
        ...     rebalancing_frequency="annual",
        ... )

        >>> # Multi-factor strategy
        >>> strategy = LongOnlyFactorStrategy(
        ...     name="Quality + Value",
        ...     factors={
        ...         "roic_mean_5y_pct": 0.5,
        ...         "fcf_yield_level_pct": 0.5,
        ...     },
        ...     num_positions=50,
        ...     rebalancing_frequency="quarterly",
        ... )
    """

    def __init__(
        self,
        name: str,
        factors: dict[str, float],
        num_positions: int = 30,
        rebalancing_frequency: str = "annual",
        position_sizing: str = "equal_weight",
        min_market_cap: float | None = None,
        description: str = "",
    ):
        """Initialize long-only factor strategy.

        Args:
            name: Strategy name
            factors: Dict mapping factor_id -> weight (weights should sum to 1.0)
            num_positions: Number of positions to hold
            rebalancing_frequency: "monthly", "quarterly", "annual"
            position_sizing: "equal_weight" or "factor_weighted"
            min_market_cap: Optional minimum market cap filter (in millions)
            description: Optional strategy description
        """
        self._name = name
        self._description = description
        self.factors = factors
        self.num_positions = num_positions
        self.rebalancing_frequency = rebalancing_frequency
        self.position_sizing = position_sizing
        self.min_market_cap = min_market_cap

        # Validate factor weights
        total_weight = sum(factors.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"Factor weights must sum to 1.0, got {total_weight:.4f}"
            )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def generate_signals(
        self, as_of_date: date, current_holdings: pl.DataFrame | None = None
    ) -> TargetPortfolio:
        """Generate target portfolio by ranking on combined factor scores.

        Process:
        1. Load all factors
        2. Combine factor scores (weighted average)
        3. Apply universe filters
        4. Rank by combined score
        5. Select top N
        6. Calculate weights (equal or factor-weighted)

        Args:
            as_of_date: Rebalancing date
            current_holdings: Ignored (not used in this strategy)

        Returns:
            TargetPortfolio with top N holdings
        """
        from factor_investor.factors.queries import get_factor

        # Load all factors
        factor_dfs = {}
        for factor_id in self.factors:
            df = get_factor(factor_id, as_of_date)
            if len(df) > 0:
                factor_dfs[factor_id] = df

        if len(factor_dfs) == 0:
            # No factor data available
            return TargetPortfolio(
                holdings=pl.DataFrame(schema={"instrument_id": pl.Int32, "weight": pl.Float64})
            )

        # Combine factors (weighted average of percentiles)
        # Start with first factor
        first_factor = list(factor_dfs.keys())[0]
        combined = factor_dfs[first_factor].select([
            "instrument_id",
            (pl.col("value") * self.factors[first_factor]).alias("combined_score")
        ])

        # Add remaining factors
        for factor_id in list(factor_dfs.keys())[1:]:
            factor_weight = self.factors[factor_id]
            combined = combined.join(
                factor_dfs[factor_id].select([
                    "instrument_id",
                    (pl.col("value") * factor_weight).alias(f"score_{factor_id}")
                ]),
                on="instrument_id",
                how="inner",
            )
            # Sum scores
            combined = combined.with_columns(
                (pl.col("combined_score") + pl.col(f"score_{factor_id}")).alias("combined_score")
            ).drop(f"score_{factor_id}")

        # Apply filters (if any)
        if self.min_market_cap is not None:
            # TODO: Implement market cap filter
            # Would need to get market_cap_local from fundamental_metrics
            pass

        # Filter out corrupted instruments (data quality issues)
        from factor_investor.universe.corrupted_instruments import filter_corrupted

        valid_instrument_ids = filter_corrupted(combined["instrument_id"].to_list())
        combined = combined.filter(pl.col("instrument_id").is_in(valid_instrument_ids))

        if len(combined) == 0:
            # All instruments filtered out
            logger.warning(f"All instruments filtered out (corrupted data)")
            return TargetPortfolio(
                holdings=pl.DataFrame(schema={"instrument_id": pl.Int32, "weight": pl.Float64})
            )

        # Rank by combined score
        ranked = combined.sort("combined_score", descending=True)

        # Select top N
        top_n = ranked.head(self.num_positions)

        # Calculate weights
        if self.position_sizing == "equal_weight":
            holdings = top_n.with_columns(
                pl.lit(1.0 / self.num_positions).alias("weight")
            )
        elif self.position_sizing == "factor_weighted":
            # Weight by normalized score
            total_score = top_n["combined_score"].sum()
            holdings = top_n.with_columns(
                (pl.col("combined_score") / total_score).alias("weight")
            )
        else:
            raise ValueError(f"Unknown position_sizing: {self.position_sizing}")

        return TargetPortfolio(
            holdings=holdings.select(["instrument_id", "weight"]),
            metadata={
                "num_candidates": len(combined),
                "num_selected": len(holdings),
                "factors_used": list(self.factors.keys()),
            }
        )

    def get_rebalancing_dates(self, from_date: date, to_date: date) -> list[date]:
        """Get rebalancing dates based on frequency.

        Args:
            from_date: Start date
            to_date: End date

        Returns:
            List of rebalancing dates
        """
        from factor_investor.dates import month_end_dates

        month_ends = month_end_dates(from_date, to_date)

        if self.rebalancing_frequency == "monthly":
            return month_ends

        elif self.rebalancing_frequency == "quarterly":
            # Keep only quarter-ends (Mar, Jun, Sep, Dec)
            return [d for d in month_ends if d.month in [3, 6, 9, 12]]

        elif self.rebalancing_frequency == "annual":
            # Keep only year-ends (December)
            return [d for d in month_ends if d.month == 12]

        else:
            raise ValueError(
                f"Unknown rebalancing_frequency: {self.rebalancing_frequency}"
            )
