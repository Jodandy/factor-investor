"""Metric calculation functions for point-in-time fundamentals.

All functions follow these principles:
1. Return None if any required input is missing or invalid
2. Handle edge cases (division by zero, negative denominators)
3. Use Decimal for precision
4. Document formula clearly in docstring

Formulas are documented in docs/DECISIONS.md.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import TypedDict


class MetricInputs(TypedDict, total=False):
    """Type definition for metric calculation inputs from reports.

    All fields are optional to support NULL handling.
    """

    # Income statement
    revenues: Decimal | None
    net_sales: Decimal | None
    gross_income: Decimal | None
    operating_income: Decimal | None
    profit_before_tax: Decimal | None
    profit_to_equity_holders: Decimal | None
    earnings_per_share: Decimal | None

    # Balance sheet
    intangible_assets: Decimal | None
    tangible_assets: Decimal | None
    financial_assets: Decimal | None
    non_current_assets: Decimal | None
    cash_and_equivalents: Decimal | None
    current_assets: Decimal | None
    total_assets: Decimal | None
    total_equity: Decimal | None
    non_current_liabilities: Decimal | None
    current_liabilities: Decimal | None
    total_liabilities_and_equity: Decimal | None
    net_debt: Decimal | None

    # Cash flow
    cash_flow_from_operating_activities: Decimal | None
    cash_flow_from_investing_activities: Decimal | None
    cash_flow_from_financing_activities: Decimal | None
    cash_flow_for_the_year: Decimal | None
    free_cash_flow: Decimal | None

    # Share data
    number_of_shares: Decimal | None
    dividend: Decimal | None


# Used for after-tax ROIC when the effective tax rate cannot be computed
# (loss before tax, or effective rate outside [0, 1])
DEFAULT_TAX_RATE = Decimal("0.22")

# --- Profitability Metrics ---


def calculate_roe(inputs: MetricInputs) -> Decimal | None:
    """Calculate Return on Equity (ROE).

    Formula: profit_to_equity_holders / total_equity

    Returns:
        ROE as decimal (e.g., 0.15 for 15%)
        None if inputs invalid or equity <= 0
    """
    profit = inputs.get("profit_to_equity_holders")
    equity = inputs.get("total_equity")

    if profit is None or equity is None or equity <= 0:
        return None

    return profit / equity


def calculate_roa(inputs: MetricInputs) -> Decimal | None:
    """Calculate Return on Assets (ROA).

    Formula: profit_to_equity_holders / total_assets

    Returns:
        ROA as decimal (e.g., 0.08 for 8%)
        None if inputs invalid or assets <= 0
    """
    profit = inputs.get("profit_to_equity_holders")
    assets = inputs.get("total_assets")

    if profit is None or assets is None or assets <= 0:
        return None

    return profit / assets


def _invested_capital(inputs: MetricInputs) -> Decimal | None:
    """total_equity + net_debt, or None if missing or not positive."""
    equity = inputs.get("total_equity")
    net_debt = inputs.get("net_debt")
    if equity is None or net_debt is None:
        return None
    invested_capital = equity + net_debt
    return invested_capital if invested_capital > 0 else None


def calculate_roic(inputs: MetricInputs) -> Decimal | None:
    """Calculate after-tax Return on Invested Capital (ROIC).

    Formula: NOPAT / invested_capital

    Where:
        effective_tax_rate = 1 - (profit_to_equity_holders / profit_before_tax)
            if profit_before_tax > 0 and the rate is within [0, 1],
            otherwise DEFAULT_TAX_RATE
        NOPAT = operating_income * (1 - tax_rate) if operating_income > 0,
            otherwise operating_income (no tax shield on operating losses)
        invested_capital = total_equity + net_debt

    Loss years give a negative ROIC rather than None, so multi-year averages
    do not silently skip bad years.

    Returns:
        ROIC as decimal (e.g., 0.12 for 12%)
        None if operating income or invested capital is missing, or
        invested capital <= 0 (ROIC undefined)
    """
    operating_income = inputs.get("operating_income")
    invested_capital = _invested_capital(inputs)
    if operating_income is None or invested_capital is None:
        return None

    if operating_income <= 0:
        return operating_income / invested_capital

    tax_rate = DEFAULT_TAX_RATE
    profit = inputs.get("profit_to_equity_holders")
    profit_before_tax = inputs.get("profit_before_tax")
    if profit is not None and profit_before_tax is not None and profit_before_tax > 0:
        effective_tax_rate = 1 - (profit / profit_before_tax)
        if 0 <= effective_tax_rate <= 1:
            tax_rate = effective_tax_rate

    return operating_income * (1 - tax_rate) / invested_capital


def calculate_roic_pretax(inputs: MetricInputs) -> Decimal | None:
    """Calculate pre-tax Return on Invested Capital.

    Formula: operating_income / (total_equity + net_debt)

    Free of tax-rate noise and comparable across tax regimes. Operating losses
    give a negative value.

    Returns:
        Pre-tax ROIC as decimal
        None if inputs missing or invested capital <= 0
    """
    operating_income = inputs.get("operating_income")
    invested_capital = _invested_capital(inputs)
    if operating_income is None or invested_capital is None:
        return None
    return operating_income / invested_capital


def calculate_gross_margin(inputs: MetricInputs) -> Decimal | None:
    """Calculate gross margin.

    Formula: gross_income / revenues

    Returns:
        Margin as decimal (e.g., 0.40 for 40%)
        None if inputs invalid or revenues <= 0
    """
    gross_income = inputs.get("gross_income")
    revenues = inputs.get("revenues")

    if gross_income is None or revenues is None or revenues <= 0:
        return None

    return gross_income / revenues


def calculate_operating_margin(inputs: MetricInputs) -> Decimal | None:
    """Calculate operating margin (EBIT margin).

    Formula: operating_income / revenues

    Returns:
        Margin as decimal (e.g., 0.15 for 15%)
        None if inputs invalid or revenues <= 0
    """
    operating_income = inputs.get("operating_income")
    revenues = inputs.get("revenues")

    if operating_income is None or revenues is None or revenues <= 0:
        return None

    return operating_income / revenues


def calculate_net_margin(inputs: MetricInputs) -> Decimal | None:
    """Calculate net profit margin.

    Formula: profit_to_equity_holders / revenues

    Returns:
        Margin as decimal (e.g., 0.10 for 10%)
        None if inputs invalid or revenues <= 0
    """
    profit = inputs.get("profit_to_equity_holders")
    revenues = inputs.get("revenues")

    if profit is None or revenues is None or revenues <= 0:
        return None

    return profit / revenues


def calculate_fcf_margin(inputs: MetricInputs) -> Decimal | None:
    """Calculate free cash flow margin.

    Formula: free_cash_flow / revenues

    Returns:
        Margin as decimal (e.g., 0.12 for 12%)
        None if inputs invalid or revenues <= 0
    """
    fcf = inputs.get("free_cash_flow")
    revenues = inputs.get("revenues")

    if fcf is None or revenues is None or revenues <= 0:
        return None

    return fcf / revenues


# --- Leverage Metrics ---


def calculate_net_debt_to_equity(inputs: MetricInputs) -> Decimal | None:
    """Calculate net debt to equity ratio.

    Formula: net_debt / total_equity

    Returns:
        Ratio as decimal (e.g., 0.50 for 50% debt/equity)
        None if inputs invalid or equity <= 0
    """
    net_debt = inputs.get("net_debt")
    equity = inputs.get("total_equity")

    if net_debt is None or equity is None or equity <= 0:
        return None

    return net_debt / equity


def calculate_net_debt_to_ebit(inputs: MetricInputs) -> Decimal | None:
    """Calculate net debt to EBIT ratio.

    Formula: net_debt / operating_income

    Note: Using operating_income as proxy for EBIT since EBITDA not available.

    Returns:
        Ratio as decimal (e.g., 2.5 for 2.5x EBIT)
        None if inputs invalid or operating_income <= 0
    """
    net_debt = inputs.get("net_debt")
    operating_income = inputs.get("operating_income")

    if net_debt is None or operating_income is None or operating_income <= 0:
        return None

    return net_debt / operating_income


def calculate_solvency(inputs: MetricInputs) -> Decimal | None:
    """Calculate solvency ratio (equity ratio).

    Formula: total_equity / total_assets

    Returns:
        Ratio as decimal (e.g., 0.45 for 45% equity)
        None if inputs invalid or assets <= 0
    """
    equity = inputs.get("total_equity")
    assets = inputs.get("total_assets")

    if equity is None or assets is None or assets <= 0:
        return None

    return equity / assets


def calculate_current_ratio(inputs: MetricInputs) -> Decimal | None:
    """Calculate current ratio.

    Formula: current_assets / current_liabilities

    Returns:
        Ratio as decimal (e.g., 1.5 for 1.5x coverage)
        None if inputs invalid or current_liabilities <= 0
    """
    current_assets = inputs.get("current_assets")
    current_liabilities = inputs.get("current_liabilities")

    if current_assets is None or current_liabilities is None or current_liabilities <= 0:
        return None

    return current_assets / current_liabilities


# --- Efficiency Metrics ---


def calculate_asset_turnover(inputs: MetricInputs) -> Decimal | None:
    """Calculate asset turnover.

    Formula: revenues / total_assets

    Returns:
        Ratio as decimal (e.g., 1.2 for 1.2x turnover)
        None if inputs invalid or assets <= 0
    """
    revenues = inputs.get("revenues")
    assets = inputs.get("total_assets")

    if revenues is None or assets is None or assets <= 0:
        return None

    return revenues / assets


def calculate_interest_coverage(inputs: MetricInputs) -> Decimal | None:
    """Calculate interest coverage ratio.

    Formula: operating_income / interest_expense

    Where interest_expense is estimated as:
        interest_expense = operating_income - profit_before_tax

    Returns:
        Ratio as decimal (e.g., 5.0 for 5x coverage)
        None if inputs invalid or interest_expense <= 0
    """
    operating_income = inputs.get("operating_income")
    profit_before_tax = inputs.get("profit_before_tax")

    if operating_income is None or profit_before_tax is None:
        return None

    # Estimate interest expense
    interest_expense = operating_income - profit_before_tax

    if interest_expense <= 0:
        return None  # No interest or negative (means financial income > expense)

    return operating_income / interest_expense


# --- Shareholder Metrics ---


def calculate_book_value_per_share(inputs: MetricInputs) -> Decimal | None:
    """Calculate book value per share.

    Formula: total_equity / number_of_shares

    Returns:
        Book value per share
        None if inputs invalid or shares <= 0
    """
    equity = inputs.get("total_equity")
    shares = inputs.get("number_of_shares")

    if equity is None or shares is None or shares <= 0:
        return None

    return equity / shares


# --- Metric Registry ---


DERIVED_METRICS: dict[str, Callable[[MetricInputs], Decimal | None]] = {
    # Profitability
    "roe": calculate_roe,
    "roa": calculate_roa,
    "roic": calculate_roic,
    "roic_pretax": calculate_roic_pretax,
    "gross_margin": calculate_gross_margin,
    "operating_margin": calculate_operating_margin,
    "net_margin": calculate_net_margin,
    "fcf_margin": calculate_fcf_margin,
    # Leverage
    "net_debt_to_equity": calculate_net_debt_to_equity,
    "net_debt_to_ebit": calculate_net_debt_to_ebit,
    "solvency": calculate_solvency,
    "current_ratio": calculate_current_ratio,
    # Efficiency
    "asset_turnover": calculate_asset_turnover,
    "interest_coverage": calculate_interest_coverage,
    # Shareholder
    "book_value_per_share": calculate_book_value_per_share,
}
"""Registry of all derived metrics with their calculation functions."""


# Base metrics that are extracted directly from reports (no calculation needed)
BASE_METRICS = [
    # Income statement
    "revenues",
    "net_sales",
    "gross_income",
    "operating_income",
    "profit_before_tax",
    "profit_to_equity_holders",
    "earnings_per_share",
    # Balance sheet
    "intangible_assets",
    "tangible_assets",
    "financial_assets",
    "non_current_assets",
    "cash_and_equivalents",
    "current_assets",
    "total_assets",
    "total_equity",
    "non_current_liabilities",
    "current_liabilities",
    "total_liabilities_and_equity",
    "net_debt",
    # Cash flow
    "cash_flow_from_operating_activities",
    "cash_flow_from_investing_activities",
    "cash_flow_from_financing_activities",
    "cash_flow_for_the_year",
    "free_cash_flow",
    # Share data
    "number_of_shares",
    "dividend",
]
"""List of base metrics extracted directly from report data."""
