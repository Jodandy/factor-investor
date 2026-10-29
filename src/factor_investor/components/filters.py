"""Filter components (stages 1.1 and 1.2)."""

import polars as pl
from pydantic import field_validator

from factor_investor.components.base import (
    ComponentParams,
    FilterComponent,
    View,
    register_component,
)
from factor_investor.components.expression import parse_expression


class ExpressionParams(ComponentParams):
    expression: str

    @field_validator("expression")
    @classmethod
    def _parses(cls, value: str) -> str:
        parse_expression(value)
        return value


@register_component
class ExpressionFilter(FilterComponent):
    """Keeps instruments for which the expression is true (unknown counts as false).

    Names are metrics on the view's date or universe fields (market_cap,
    turnover in the area's currency, price, years_of_history).
    """

    id = "expression_v1"
    Params = ExpressionParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        assert isinstance(self.params, ExpressionParams)
        expression = parse_expression(self.params.expression)
        frame = view.frame(instruments, expression.names)
        return frame.filter(expression.to_polars().fill_null(False)).select("instrument_id")
