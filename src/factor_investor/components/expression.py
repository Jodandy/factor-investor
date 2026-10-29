"""expression_v1 language: comparisons, boolean logic and arithmetic over named
columns (metrics and universe fields), parsed into a whitelisted AST and
compiled to a polars expression. Nothing is ever passed to `eval`.

Missing values propagate: a comparison on a missing value is unknown, and an
unknown condition never selects an instrument (`fill_null(False)` by the
caller); `or` with a true side is still true.
"""

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import polars as pl

_COMPARE: dict[type[ast.cmpop], Callable[[Any, Any], pl.Expr]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_ARITHMETIC: dict[type[ast.operator], Callable[[Any, Any], pl.Expr]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_FUNCTIONS: dict[str, Callable[[pl.Expr], pl.Expr]] = {"abs": lambda e: e.abs()}


@dataclass(frozen=True)
class Expression:
    source: str
    tree: ast.Expression
    names: frozenset[str]

    def to_polars(self) -> pl.Expr:
        compiled: pl.Expr = _compile(self.tree.body)
        return compiled


def parse_expression(
    source: str, known_names: set[str] | frozenset[str] | None = None
) -> Expression:
    """Parse and validate; raises ValueError for anything outside the language."""
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression {source!r}: {e.msg}") from e
    names: set[str] = set()
    _validate(tree.body, names)
    if known_names is not None:
        unknown = names - set(known_names)
        if unknown:
            raise ValueError(f"Unknown names in {source!r}: {sorted(unknown)}")
    return Expression(source, tree, frozenset(names))


def _validate(node: ast.AST, names: set[str]) -> None:
    match node:
        case ast.BoolOp(op=ast.And() | ast.Or(), values=values):
            for value in values:
                _validate(value, names)
        case ast.UnaryOp(op=ast.Not() | ast.USub(), operand=operand):
            _validate(operand, names)
        case ast.Compare(left=left, ops=ops, comparators=comparators):
            if not all(type(op) in _COMPARE for op in ops):
                raise ValueError(f"Comparison not allowed: {ast.unparse(node)}")
            for child in (left, *comparators):
                _validate(child, names)
        case ast.BinOp(left=left, op=op, right=right):
            if type(op) not in _ARITHMETIC:
                raise ValueError(f"Operator not allowed: {ast.unparse(node)}")
            _validate(left, names)
            _validate(right, names)
        case ast.Call(func=ast.Name(id=function), args=[argument], keywords=[]) if (
            function in _FUNCTIONS
        ):
            _validate(argument, names)
        case ast.Name(id=name):
            names.add(name)
        case ast.Constant(value=value) if isinstance(value, int | float) and not isinstance(
            value, bool
        ):
            pass
        case _:
            raise ValueError(f"Not allowed in an expression: {ast.unparse(node)!r}")


def _compile(node: ast.AST) -> Any:
    match node:
        case ast.BoolOp(op=op, values=values):
            compiled = [_compile(v) for v in values]
            result = compiled[0]
            for value in compiled[1:]:
                result = result & value if isinstance(op, ast.And) else result | value
            return result
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return ~_compile(operand)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_compile(operand)
        case ast.Compare(left=left, ops=ops, comparators=comparators):
            terms = [_compile(left), *(_compile(c) for c in comparators)]
            parts = [_COMPARE[type(op)](terms[i], terms[i + 1]) for i, op in enumerate(ops)]
            result = parts[0]
            for part in parts[1:]:
                result = result & part
            return result
        case ast.BinOp(left=left, op=op, right=right):
            return _ARITHMETIC[type(op)](_compile(left), _compile(right))
        case ast.Call(func=ast.Name(id=function), args=[argument]):
            return _FUNCTIONS[function](_compile(argument))
        case ast.Name(id=name):
            return pl.col(name)
        case ast.Constant(value=value):
            return pl.lit(value)
    raise AssertionError(f"unvalidated node {ast.dump(node)}")
