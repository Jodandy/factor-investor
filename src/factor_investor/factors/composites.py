"""Composite score calculation.

Composite scores combine multiple factors into a single score.
Examples: Piotroski F-Score, Altman Z-Score, etc.

Each composite is defined in a YAML config file specifying:
- Components (which factors to use)
- Conditions (how to evaluate each component)
- Weights (how to combine components)
"""

import logging
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import yaml

from factor_investor.factors.queries import get_factor

logger = logging.getLogger(__name__)

# Config directory
COMPOSITES_DIR = Path("config/composites")


def calculate_composite_score(
    composite_id: str,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Calculate composite score for instruments.

    Args:
        composite_id: Composite score ID (e.g., "piotroski_f_score")
        as_of_date: Date to calculate for
        instrument_ids: Optional filter

    Returns:
        DataFrame with columns [instrument_id, date, score, score_label]

    Example:
        >>> df = calculate_composite_score("piotroski_f_score", date(2024, 1, 31))
        >>> print(df)
        ┌─────────────────┬────────────┬───────┬─────────────┐
        │ instrument_id   │ date       │ score │ score_label │
        ├─────────────────┼────────────┼───────┼─────────────┤
        │ 2               │ 2024-01-31 │ 7     │ Strong      │
        │ 3               │ 2024-01-31 │ 9     │ Very Strong │
        └─────────────────┴────────────┴───────┴─────────────┘
    """
    # Load config
    config_path = COMPOSITES_DIR / f"{composite_id}.yaml"
    if not config_path.exists():
        raise ValueError(f"Composite config not found: {config_path}")

    with config_path.open("r") as f:
        config = yaml.safe_load(f)

    logger.debug(f"Calculating {config['name']} for {as_of_date}")

    # Calculate each component
    component_scores = []

    for component in config["components"]:
        logger.debug(f"  Evaluating component: {component['id']}")

        try:
            score_df = _evaluate_component(component, as_of_date, instrument_ids)
            component_scores.append(score_df)
        except Exception as e:
            logger.warning(f"  Failed to evaluate {component['id']}: {e}")
            continue

    if len(component_scores) == 0:
        logger.warning(f"No components could be calculated for {composite_id}")
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "score": pl.Int32,
                "score_label": pl.Utf8,
            }
        )

    # Combine component scores
    total_score_df = _combine_component_scores(
        component_scores,
        min_required=config.get("min_components_required", len(config["components"])),
    )

    # Add date
    total_score_df = total_score_df.with_columns(pl.lit(as_of_date).alias("date"))

    # Add score labels
    score_ranges = config.get("score_ranges", [])
    total_score_df = _add_score_labels(total_score_df, score_ranges)

    logger.debug(
        f"  Calculated {len(total_score_df)} scores "
        f"(mean: {total_score_df['score'].mean():.2f})"
    )

    return total_score_df.select(["instrument_id", "date", "score", "score_label"])


def _evaluate_component(
    component: dict,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Evaluate a single component and return binary score (0 or 1).

    Args:
        component: Component config dict
        as_of_date: Date to evaluate
        instrument_ids: Optional filter

    Returns:
        DataFrame with columns [instrument_id, score]
    """
    condition = component["condition"]

    # Handle different condition types
    if condition.startswith("change_1y"):
        # Year-over-year change condition (e.g., "change_1y > 0")
        return _evaluate_change_condition(
            component["metric"], condition, as_of_date, instrument_ids
        )

    elif "a > b" in condition or "a < b" in condition:
        # Comparison between two metrics (e.g., "a > b")
        return _evaluate_comparison_condition(
            component["metric_a"],
            component["metric_b"],
            condition,
            as_of_date,
            instrument_ids,
        )

    else:
        # Simple condition on single metric (e.g., "> 0", "< 0")
        return _evaluate_simple_condition(
            component["metric"], condition, as_of_date, instrument_ids
        )


def _evaluate_simple_condition(
    metric: str,
    condition: str,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Evaluate simple condition on a metric (e.g., "roe > 0").

    Args:
        metric: Metric/factor ID
        condition: Condition string (e.g., "> 0", "< 0", ">= 10")
        as_of_date: Date to evaluate
        instrument_ids: Optional filter

    Returns:
        DataFrame with columns [instrument_id, score]
    """
    # Get factor
    df = get_factor(metric, as_of_date, instrument_ids)

    if len(df) == 0:
        return pl.DataFrame(schema={"instrument_id": pl.Int32, "score": pl.Int8})

    # Parse condition
    # Examples: "> 0", "< 0", ">= 10"
    import re

    match = re.match(r"([><=]+)\s*([-\d.]+)", condition)
    if not match:
        raise ValueError(f"Invalid condition format: {condition}")

    operator = match.group(1)
    threshold = float(match.group(2))

    # Apply condition
    if operator == ">":
        score_expr = (pl.col("value") > threshold).cast(pl.Int8)
    elif operator == "<":
        score_expr = (pl.col("value") < threshold).cast(pl.Int8)
    elif operator == ">=":
        score_expr = (pl.col("value") >= threshold).cast(pl.Int8)
    elif operator == "<=":
        score_expr = (pl.col("value") <= threshold).cast(pl.Int8)
    elif operator == "==":
        score_expr = (pl.col("value") == threshold).cast(pl.Int8)
    else:
        raise ValueError(f"Unknown operator: {operator}")

    result = df.with_columns(score_expr.alias("score")).select(["instrument_id", "score"])

    return result


def _evaluate_change_condition(
    metric: str,
    condition: str,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Evaluate year-over-year change condition (e.g., "change_1y > 0").

    Args:
        metric: Metric/factor ID
        condition: Condition string (e.g., "change_1y > 0")
        as_of_date: Date to evaluate
        instrument_ids: Optional filter

    Returns:
        DataFrame with columns [instrument_id, score]
    """
    # Get current value
    df_current = get_factor(metric, as_of_date, instrument_ids)

    # Get value from 1 year ago
    date_1y_ago = as_of_date - timedelta(days=365)
    df_previous = get_factor(metric, date_1y_ago, instrument_ids)

    if len(df_current) == 0 or len(df_previous) == 0:
        return pl.DataFrame(schema={"instrument_id": pl.Int32, "score": pl.Int8})

    # Join current and previous
    joined = df_current.join(
        df_previous.select(["instrument_id", pl.col("value").alias("value_prev")]),
        on="instrument_id",
        how="inner",
    )

    # Calculate change
    joined = joined.with_columns(
        (pl.col("value") - pl.col("value_prev")).alias("change")
    )

    # Parse condition (e.g., "change_1y > 0" -> "> 0")
    import re

    match = re.search(r"([><=]+)\s*([-\d.]+)", condition)
    if not match:
        raise ValueError(f"Invalid condition format: {condition}")

    operator = match.group(1)
    threshold = float(match.group(2))

    # Apply condition
    if operator == ">":
        score_expr = (pl.col("change") > threshold).cast(pl.Int8)
    elif operator == "<":
        score_expr = (pl.col("change") < threshold).cast(pl.Int8)
    elif operator == ">=":
        score_expr = (pl.col("change") >= threshold).cast(pl.Int8)
    elif operator == "<=":
        score_expr = (pl.col("change") <= threshold).cast(pl.Int8)
    else:
        raise ValueError(f"Unknown operator: {operator}")

    result = joined.with_columns(score_expr.alias("score")).select(
        ["instrument_id", "score"]
    )

    return result


def _evaluate_comparison_condition(
    metric_a: str,
    metric_b: str,
    condition: str,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Evaluate comparison between two metrics (e.g., "a > b").

    Args:
        metric_a: First metric/factor ID
        metric_b: Second metric/factor ID
        condition: Condition string (e.g., "a > b", "a < b")
        as_of_date: Date to evaluate
        instrument_ids: Optional filter

    Returns:
        DataFrame with columns [instrument_id, score]
    """
    # Get both metrics
    df_a = get_factor(metric_a, as_of_date, instrument_ids)
    df_b = get_factor(metric_b, as_of_date, instrument_ids)

    if len(df_a) == 0 or len(df_b) == 0:
        return pl.DataFrame(schema={"instrument_id": pl.Int32, "score": pl.Int8})

    # Join
    joined = df_a.join(
        df_b.select(["instrument_id", pl.col("value").alias("value_b")]),
        on="instrument_id",
        how="inner",
    )

    # Rename for clarity
    joined = joined.rename({"value": "value_a"})

    # Apply condition
    if "a > b" in condition:
        score_expr = (pl.col("value_a") > pl.col("value_b")).cast(pl.Int8)
    elif "a < b" in condition:
        score_expr = (pl.col("value_a") < pl.col("value_b")).cast(pl.Int8)
    elif "a >= b" in condition:
        score_expr = (pl.col("value_a") >= pl.col("value_b")).cast(pl.Int8)
    elif "a <= b" in condition:
        score_expr = (pl.col("value_a") <= pl.col("value_b")).cast(pl.Int8)
    else:
        raise ValueError(f"Unknown comparison condition: {condition}")

    result = joined.with_columns(score_expr.alias("score")).select(
        ["instrument_id", "score"]
    )

    return result


def _combine_component_scores(
    component_scores: list[pl.DataFrame],
    min_required: int,
) -> pl.DataFrame:
    """Combine component scores into total score.

    Args:
        component_scores: List of DataFrames with [instrument_id, score]
        min_required: Minimum number of components required

    Returns:
        DataFrame with [instrument_id, score]
    """
    if len(component_scores) == 0:
        return pl.DataFrame(schema={"instrument_id": pl.Int32, "score": pl.Int32})

    # Start with first component
    result = component_scores[0].rename({"score": "score_0"})

    # Join all other components
    for i, component_df in enumerate(component_scores[1:], 1):
        result = result.join(
            component_df.rename({"score": f"score_{i}"}),
            on="instrument_id",
            how="outer",  # Keep all instruments
            coalesce=True,  # Merge duplicate columns
        )

    # Sum all score columns
    score_cols = [f"score_{i}" for i in range(len(component_scores))]

    # Count non-null scores (components available)
    result = result.with_columns(
        pl.sum_horizontal(score_cols).alias("total_score"),
        pl.sum_horizontal([pl.col(c).is_not_null() for c in score_cols]).alias(
            "num_components"
        ),
    )

    # Filter to instruments with minimum required components
    result = result.filter(pl.col("num_components") >= min_required)

    return result.select(["instrument_id", pl.col("total_score").alias("score")])


def _add_score_labels(
    df: pl.DataFrame,
    score_ranges: list[dict],
) -> pl.DataFrame:
    """Add score labels based on ranges.

    Args:
        df: DataFrame with score column
        score_ranges: List of {range: [min, max], label: str}

    Returns:
        DataFrame with score_label column added
    """
    if len(score_ranges) == 0:
        return df.with_columns(pl.lit("").alias("score_label"))

    # Build label expression
    label_expr = pl.lit("Unknown")

    for range_config in reversed(score_ranges):
        min_score, max_score = range_config["range"]
        label = range_config["label"]

        label_expr = pl.when(
            (pl.col("score") >= min_score) & (pl.col("score") <= max_score)
        ).then(pl.lit(label)).otherwise(label_expr)

    return df.with_columns(label_expr.alias("score_label"))


def get_composite_config(composite_id: str) -> dict:
    """Load composite configuration.

    Args:
        composite_id: Composite score ID

    Returns:
        Config dict

    Example:
        >>> config = get_composite_config("piotroski_f_score")
        >>> print(config["name"])
        Piotroski F-Score
    """
    config_path = COMPOSITES_DIR / f"{composite_id}.yaml"
    if not config_path.exists():
        raise ValueError(f"Composite config not found: {config_path}")

    with config_path.open("r") as f:
        return yaml.safe_load(f)


def list_available_composites() -> list[str]:
    """List all available composite scores.

    Returns:
        List of composite IDs

    Example:
        >>> composites = list_available_composites()
        >>> print(composites)
        ['piotroski_f_score', 'altman_z_nordic']
    """
    if not COMPOSITES_DIR.exists():
        return []

    return [f.stem for f in COMPOSITES_DIR.glob("*.yaml")]
