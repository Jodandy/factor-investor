"""Unit tests for metric calculation functions."""

from decimal import Decimal

from factor_investor.pit.metrics import (
    DEFAULT_TAX_RATE,
    DERIVED_METRICS,
    MetricInputs,
    calculate_asset_turnover,
    calculate_current_ratio,
    calculate_fcf_margin,
    calculate_gross_margin,
    calculate_interest_coverage,
    calculate_net_debt_to_ebit,
    calculate_net_debt_to_equity,
    calculate_net_margin,
    calculate_operating_margin,
    calculate_roa,
    calculate_roe,
    calculate_roic,
    calculate_roic_pretax,
    calculate_solvency,
)


class TestProfitabilityMetrics:
    """Tests for profitability metric calculations."""

    def test_roe_happy_path(self) -> None:
        """Test ROE calculation with valid inputs."""
        inputs: MetricInputs = {
            "profit_to_equity_holders": Decimal("100"),
            "total_equity": Decimal("1000"),
        }

        result = calculate_roe(inputs)
        assert result == Decimal("0.1"), f"Expected 0.1, got {result}"

    def test_roe_null_handling(self) -> None:
        """Test ROE returns None when inputs are missing."""
        # Missing profit
        inputs: MetricInputs = {"total_equity": Decimal("1000")}
        assert calculate_roe(inputs) is None

        # Missing equity
        inputs = {"profit_to_equity_holders": Decimal("100")}
        assert calculate_roe(inputs) is None

        # Both missing
        inputs = {}
        assert calculate_roe(inputs) is None

    def test_roe_zero_equity(self) -> None:
        """Test ROE returns None when equity is zero or negative."""
        inputs: MetricInputs = {
            "profit_to_equity_holders": Decimal("100"),
            "total_equity": Decimal("0"),
        }
        assert calculate_roe(inputs) is None

        inputs["total_equity"] = Decimal("-100")
        assert calculate_roe(inputs) is None

    def test_roa_happy_path(self) -> None:
        """Test ROA calculation with valid inputs."""
        inputs: MetricInputs = {
            "profit_to_equity_holders": Decimal("100"),
            "total_assets": Decimal("2000"),
        }

        result = calculate_roa(inputs)
        assert result == Decimal("0.05"), f"Expected 0.05, got {result}"

    def test_roic_happy_path(self) -> None:
        """Test ROIC calculation with valid inputs."""
        inputs: MetricInputs = {
            "operating_income": Decimal("200"),
            "profit_to_equity_holders": Decimal("120"),
            "profit_before_tax": Decimal("150"),
            "total_equity": Decimal("1000"),
            "net_debt": Decimal("500"),
        }

        result = calculate_roic(inputs)

        # Calculate expected manually:
        # effective_tax_rate = 1 - (120/150) = 0.2
        # NOPAT = 200 * (1 - 0.2) = 160
        # invested_capital = 1000 + 500 = 1500
        # ROIC = 160 / 1500 = 0.106666...

        assert result is not None
        assert abs(result - Decimal("0.106666")) < Decimal("0.00001")

    def test_roic_uses_default_tax_rate_when_effective_rate_unusable(self) -> None:
        """Missing ROIC in such years made multi-year averages skip bad years."""
        # Effective tax rate negative (profit > profit_before_tax)
        inputs: MetricInputs = {
            "operating_income": Decimal("200"),
            "profit_to_equity_holders": Decimal("200"),
            "profit_before_tax": Decimal("150"),
            "total_equity": Decimal("1000"),
            "net_debt": Decimal("500"),
        }
        expected = Decimal("200") * (1 - DEFAULT_TAX_RATE) / Decimal("1500")
        assert calculate_roic(inputs) == expected

        # Pre-tax loss from financial items, operating profit still positive
        inputs["profit_before_tax"] = Decimal("-10")
        assert calculate_roic(inputs) == expected

    def test_roic_operating_loss_is_negative_without_tax_shield(self) -> None:
        inputs: MetricInputs = {
            "operating_income": Decimal("-300"),
            "profit_to_equity_holders": Decimal("-320"),
            "profit_before_tax": Decimal("-320"),
            "total_equity": Decimal("1000"),
            "net_debt": Decimal("500"),
        }
        assert calculate_roic(inputs) == Decimal("-300") / Decimal("1500")

    def test_roic_undefined_without_invested_capital(self) -> None:
        inputs: MetricInputs = {
            "operating_income": Decimal("200"),
            "profit_to_equity_holders": Decimal("120"),
            "profit_before_tax": Decimal("150"),
            "total_equity": Decimal("-600"),
            "net_debt": Decimal("500"),
        }
        assert calculate_roic(inputs) is None
        assert calculate_roic_pretax(inputs) is None

    def test_roic_pretax(self) -> None:
        inputs: MetricInputs = {
            "operating_income": Decimal("-300"),
            "total_equity": Decimal("1000"),
            "net_debt": Decimal("500"),
        }
        assert calculate_roic_pretax(inputs) == Decimal("-0.2")

        inputs["operating_income"] = Decimal("300")
        assert calculate_roic_pretax(inputs) == Decimal("0.2")

    def test_roic_pretax_registered(self) -> None:
        assert DERIVED_METRICS["roic_pretax"] is calculate_roic_pretax

    def test_gross_margin_happy_path(self) -> None:
        """Test gross margin calculation."""
        inputs: MetricInputs = {
            "gross_income": Decimal("400"),
            "revenues": Decimal("1000"),
        }

        result = calculate_gross_margin(inputs)
        assert result == Decimal("0.4")

    def test_operating_margin_happy_path(self) -> None:
        """Test operating margin calculation."""
        inputs: MetricInputs = {
            "operating_income": Decimal("150"),
            "revenues": Decimal("1000"),
        }

        result = calculate_operating_margin(inputs)
        assert result == Decimal("0.15")

    def test_net_margin_happy_path(self) -> None:
        """Test net margin calculation."""
        inputs: MetricInputs = {
            "profit_to_equity_holders": Decimal("80"),
            "revenues": Decimal("1000"),
        }

        result = calculate_net_margin(inputs)
        assert result == Decimal("0.08")

    def test_fcf_margin_happy_path(self) -> None:
        """Test FCF margin calculation."""
        inputs: MetricInputs = {
            "free_cash_flow": Decimal("120"),
            "revenues": Decimal("1000"),
        }

        result = calculate_fcf_margin(inputs)
        assert result == Decimal("0.12")


class TestLeverageMetrics:
    """Tests for leverage metric calculations."""

    def test_net_debt_to_equity_happy_path(self) -> None:
        """Test net debt to equity calculation."""
        inputs: MetricInputs = {
            "net_debt": Decimal("500"),
            "total_equity": Decimal("1000"),
        }

        result = calculate_net_debt_to_equity(inputs)
        assert result == Decimal("0.5")

    def test_net_debt_to_ebit_happy_path(self) -> None:
        """Test net debt to EBIT calculation."""
        inputs: MetricInputs = {
            "net_debt": Decimal("500"),
            "operating_income": Decimal("200"),
        }

        result = calculate_net_debt_to_ebit(inputs)
        assert result == Decimal("2.5")

    def test_solvency_happy_path(self) -> None:
        """Test solvency (equity ratio) calculation."""
        inputs: MetricInputs = {
            "total_equity": Decimal("600"),
            "total_assets": Decimal("1000"),
        }

        result = calculate_solvency(inputs)
        assert result == Decimal("0.6")

    def test_current_ratio_happy_path(self) -> None:
        """Test current ratio calculation."""
        inputs: MetricInputs = {
            "current_assets": Decimal("500"),
            "current_liabilities": Decimal("300"),
        }

        result = calculate_current_ratio(inputs)
        assert abs(result - Decimal("1.666666")) < Decimal("0.00001")


class TestEfficiencyMetrics:
    """Tests for efficiency metric calculations."""

    def test_asset_turnover_happy_path(self) -> None:
        """Test asset turnover calculation."""
        inputs: MetricInputs = {
            "revenues": Decimal("2000"),
            "total_assets": Decimal("1000"),
        }

        result = calculate_asset_turnover(inputs)
        assert result == Decimal("2.0")

    def test_interest_coverage_happy_path(self) -> None:
        """Test interest coverage calculation."""
        inputs: MetricInputs = {
            "operating_income": Decimal("200"),
            "profit_before_tax": Decimal("180"),
        }

        result = calculate_interest_coverage(inputs)

        # interest_expense = 200 - 180 = 20
        # coverage = 200 / 20 = 10
        assert result == Decimal("10.0")

    def test_interest_coverage_no_interest(self) -> None:
        """Test interest coverage returns None when no interest expense."""
        # operating_income = profit_before_tax (no interest)
        inputs: MetricInputs = {
            "operating_income": Decimal("200"),
            "profit_before_tax": Decimal("200"),
        }

        assert calculate_interest_coverage(inputs) is None

    def test_interest_coverage_financial_income(self) -> None:
        """Test interest coverage returns None when financial income > expense."""
        # profit_before_tax > operating_income (net financial income)
        inputs: MetricInputs = {
            "operating_income": Decimal("200"),
            "profit_before_tax": Decimal("250"),
        }

        assert calculate_interest_coverage(inputs) is None


class TestNegativeValues:
    """Tests for handling negative values in inputs."""

    def test_negative_revenue_returns_none(self) -> None:
        """Test that negative revenues return None for margin calculations."""
        inputs: MetricInputs = {
            "gross_income": Decimal("100"),
            "revenues": Decimal("-500"),
        }

        assert calculate_gross_margin(inputs) is None
        assert (
            calculate_operating_margin(
                {"operating_income": Decimal("50"), "revenues": Decimal("-500")}
            )
            is None
        )

    def test_negative_equity_returns_none(self) -> None:
        """Test that negative equity returns None for ROE."""
        inputs: MetricInputs = {
            "profit_to_equity_holders": Decimal("100"),
            "total_equity": Decimal("-50"),
        }

        assert calculate_roe(inputs) is None

    def test_negative_net_debt_is_allowed(self) -> None:
        """Test that negative net debt (cash position) is allowed."""
        inputs: MetricInputs = {
            "net_debt": Decimal("-200"),  # Company has net cash
            "total_equity": Decimal("1000"),
        }

        result = calculate_net_debt_to_equity(inputs)
        assert result == Decimal("-0.2")  # Negative is OK
