"""Portfolio tracking and rebalancing.

This module provides a generic Portfolio class that:
- Tracks holdings (shares, values, weights)
- Executes rebalancing to target weights
- Calculates transaction costs
- Tracks cash and portfolio value
- Computes daily returns

The Portfolio class is strategy-agnostic and works with any Strategy
that returns TargetPortfolio from generate_signals().
"""

import logging
from dataclasses import dataclass
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """A single trade execution.

    Attributes:
        instrument_id: Instrument being traded
        action: "buy" or "sell"
        shares: Number of shares (positive)
        price: Execution price per share
        cost: Transaction cost (positive, in base currency)
        date: Trade date
    """

    instrument_id: int
    action: str  # "buy" or "sell"
    shares: float  # Number of shares (always positive)
    price: float  # Price per share
    cost: float  # Transaction cost (always positive)
    date: date

    @property
    def value(self) -> float:
        """Gross trade value (before costs)."""
        return self.shares * self.price

    @property
    def net_value(self) -> float:
        """Net trade value (after costs).

        For buys: negative (cash outflow)
        For sells: positive (cash inflow)
        """
        if self.action == "buy":
            return -(self.value + self.cost)
        else:  # sell
            return self.value - self.cost


class Portfolio:
    """Portfolio tracker for backtesting.

    Tracks holdings, cash, and portfolio value. Handles rebalancing
    with transaction costs.

    The Portfolio is generic - it doesn't know about strategies, factors,
    or signals. It just knows how to:
    1. Track current holdings
    2. Rebalance to target weights
    3. Calculate costs
    4. Track value over time
    """

    def __init__(self, initial_capital: float):
        """Initialize portfolio.

        Args:
            initial_capital: Starting cash
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital

        # Current holdings: [instrument_id, shares, last_price]
        self.holdings = pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "shares": pl.Float64,
                "last_price": pl.Float64,
            }
        )

        # Trade history
        self.trades: list[Trade] = []

        # Value history (for performance tracking)
        self.value_history: list[tuple[date, float]] = []

    @property
    def holdings_value(self) -> float:
        """Current market value of holdings."""
        if len(self.holdings) == 0:
            return 0.0

        return (self.holdings["shares"] * self.holdings["last_price"]).sum()

    @property
    def total_value(self) -> float:
        """Total portfolio value (cash + holdings)."""
        return self.cash + self.holdings_value

    def update_prices(self, prices: pl.DataFrame, as_of_date: date) -> float:
        """Update holdings with current prices and calculate return.

        Args:
            prices: DataFrame with [instrument_id, price]
            as_of_date: Current date

        Returns:
            Daily return (as decimal, e.g., 0.01 = 1%)
        """
        if len(self.holdings) == 0:
            # No holdings, no return (just cash)
            self.value_history.append((as_of_date, self.total_value))
            return 0.0

        # Calculate value before price update
        value_before = self.total_value

        # Update prices for held instruments
        self.holdings = self.holdings.join(
            prices.select([
                pl.col("instrument_id"),
                pl.col("price").alias("new_price")
            ]),
            on="instrument_id",
            how="left",
        )

        # Update last_price (use new_price if available, else keep last_price)
        self.holdings = self.holdings.with_columns(
            pl.when(pl.col("new_price").is_not_null())
            .then(pl.col("new_price"))
            .otherwise(pl.col("last_price"))
            .alias("last_price")
        ).drop("new_price")

        # Calculate value after price update
        value_after = self.total_value

        # Calculate return
        daily_return = (value_after / value_before) - 1 if value_before > 0 else 0.0

        # Record value
        self.value_history.append((as_of_date, value_after))

        return daily_return

    def rebalance(
        self,
        target_weights: pl.DataFrame,
        prices: pl.DataFrame,
        rebal_date: date,
        transaction_cost_bps: int = 10,
        max_position_weight: float = 0.10,
    ) -> list[Trade]:
        """Rebalance portfolio to target weights.

        Process:
        1. Calculate target positions (shares needed)
        2. Compare to current positions
        3. Generate trades (buys and sells)
        4. Apply transaction costs
        5. Update holdings and cash

        Args:
            target_weights: DataFrame with [instrument_id, weight]
            prices: DataFrame with [instrument_id, price]
            rebal_date: Rebalancing date
            transaction_cost_bps: Transaction cost in basis points
            max_position_weight: Maximum weight per position

        Returns:
            List of Trade objects executed
        """
        total_value = self.total_value

        # Enforce max position weight
        target_weights = target_weights.with_columns(
            pl.when(pl.col("weight") > max_position_weight)
            .then(pl.lit(max_position_weight))
            .otherwise(pl.col("weight"))
            .alias("weight")
        )

        # Renormalize weights to sum to 1.0
        total_weight = target_weights["weight"].sum()
        if total_weight > 0:
            target_weights = target_weights.with_columns(
                (pl.col("weight") / total_weight).alias("weight")
            )

        # Calculate target positions (only includes instruments with prices)
        target_positions = target_weights.join(
            prices,
            on="instrument_id",
            how="inner",
        )

        target_positions = target_positions.with_columns(
            ((pl.col("weight") * total_value) / pl.col("price")).alias("target_shares")
        )

        # Get current positions and join with prices
        # (need prices for both buying and selling)
        current_positions = self.holdings.select([
            "instrument_id",
            pl.col("shares").alias("current_shares"),
        ]).join(
            prices.select(["instrument_id", pl.col("price").alias("current_price")]),
            on="instrument_id",
            how="left",  # Keep all current positions, even without prices
        )

        # Join target with current (outer join to catch sells and buys)
        positions = target_positions.join(
            current_positions,
            on="instrument_id",
            how="outer",
        ).with_columns([
            pl.col("target_shares").fill_null(0),
            pl.col("current_shares").fill_null(0),
        ])

        # Use target price for buys, current_price for sells
        # If neither available, skip the trade (can't trade without price)
        positions = positions.with_columns(
            pl.when(pl.col("target_shares") > pl.col("current_shares"))
            .then(pl.col("price"))  # Buy: use target price
            .otherwise(pl.col("current_price"))  # Sell: use current price
            .alias("trade_price")
        )

        # Filter out trades without valid prices
        positions = positions.filter(pl.col("trade_price").is_not_null())

        # Calculate trades needed
        positions = positions.with_columns(
            (pl.col("target_shares") - pl.col("current_shares")).alias("shares_delta")
        )

        # Separate buys and sells
        trades_needed = positions.filter(
            pl.col("shares_delta").abs() > 0.01  # Ignore tiny changes
        )

        executed_trades: list[Trade] = []

        # Execute sells first (to free up cash)
        sells = trades_needed.filter(pl.col("shares_delta") < 0).sort("shares_delta")
        for row in sells.iter_rows(named=True):
            trade = self._execute_trade(
                instrument_id=row["instrument_id"],
                shares=abs(row["shares_delta"]),
                price=row["trade_price"],
                action="sell",
                date=rebal_date,
                cost_bps=transaction_cost_bps,
            )
            executed_trades.append(trade)

        # Execute buys (with available cash)
        buys = trades_needed.filter(pl.col("shares_delta") > 0).sort("shares_delta", descending=True)
        for row in buys.iter_rows(named=True):
            trade = self._execute_trade(
                instrument_id=row["instrument_id"],
                shares=row["shares_delta"],
                price=row["trade_price"],
                action="buy",
                date=rebal_date,
                cost_bps=transaction_cost_bps,
            )
            executed_trades.append(trade)

            # Check if we're out of cash
            if self.cash < 0:
                logger.warning(
                    f"Insufficient cash after rebalancing on {rebal_date}. "
                    f"Cash: {self.cash:,.0f} (negative)"
                )
                break

        return executed_trades

    def _execute_trade(
        self,
        instrument_id: int,
        shares: float,
        price: float,
        action: str,
        date: date,
        cost_bps: int,
    ) -> Trade:
        """Execute a single trade and update holdings/cash.

        Args:
            instrument_id: Instrument to trade
            shares: Number of shares (positive)
            price: Execution price
            action: "buy" or "sell"
            date: Trade date
            cost_bps: Transaction cost in basis points

        Returns:
            Trade object
        """
        # Calculate cost
        gross_value = shares * price
        cost = gross_value * (cost_bps / 10000)

        # Create trade
        trade = Trade(
            instrument_id=instrument_id,
            action=action,
            shares=shares,
            price=price,
            cost=cost,
            date=date,
        )

        # Update cash
        self.cash += trade.net_value

        # Update holdings
        if action == "buy":
            # Add or increase position
            existing = self.holdings.filter(pl.col("instrument_id") == instrument_id)

            if len(existing) > 0:
                # Increase existing position
                current_shares = existing["shares"][0]
                self.holdings = self.holdings.with_columns(
                    pl.when(pl.col("instrument_id") == instrument_id)
                    .then(pl.lit(current_shares + shares))
                    .otherwise(pl.col("shares"))
                    .alias("shares"),
                    pl.when(pl.col("instrument_id") == instrument_id)
                    .then(pl.lit(price))
                    .otherwise(pl.col("last_price"))
                    .alias("last_price"),
                )
            else:
                # New position
                new_holding = pl.DataFrame({
                    "instrument_id": pl.Series([instrument_id], dtype=pl.Int32),
                    "shares": [shares],
                    "last_price": [price],
                })
                self.holdings = pl.concat([self.holdings, new_holding])

        else:  # sell
            # Reduce or close position
            existing = self.holdings.filter(pl.col("instrument_id") == instrument_id)

            if len(existing) > 0:
                current_shares = existing["shares"][0]
                remaining_shares = current_shares - shares

                if remaining_shares < 0.01:
                    # Close position completely
                    self.holdings = self.holdings.filter(
                        pl.col("instrument_id") != instrument_id
                    )
                else:
                    # Reduce position
                    self.holdings = self.holdings.with_columns(
                        pl.when(pl.col("instrument_id") == instrument_id)
                        .then(pl.lit(remaining_shares))
                        .otherwise(pl.col("shares"))
                        .alias("shares"),
                        pl.when(pl.col("instrument_id") == instrument_id)
                        .then(pl.lit(price))
                        .otherwise(pl.col("last_price"))
                        .alias("last_price"),
                    )

        # Record trade
        self.trades.append(trade)

        return trade

    def get_holdings_df(self) -> pl.DataFrame:
        """Get current holdings with values and weights.

        Returns:
            DataFrame with [instrument_id, shares, price, value, weight]
        """
        if len(self.holdings) == 0:
            return pl.DataFrame(
                schema={
                    "instrument_id": pl.Int32,
                    "shares": pl.Float64,
                    "price": pl.Float64,
                    "value": pl.Float64,
                    "weight": pl.Float64,
                }
            )

        total_value = self.total_value

        return self.holdings.with_columns([
            (pl.col("shares") * pl.col("last_price")).alias("value"),
        ]).with_columns([
            (pl.col("value") / total_value).alias("weight"),
        ]).rename({"last_price": "price"})
