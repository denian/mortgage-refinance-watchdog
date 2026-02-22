import pytest
from src.calculator import (
    monthly_payment,
    total_interest,
    compute_scenario_a,
    compute_scenario_b,
    compute_break_even,
    format_currency,
    format_percent,
)


def test_monthly_payment_known_value():
    # $400k at 6.5% for 30 years → ~$2,528.27
    pmt = monthly_payment(400_000, 0.065, 360)
    assert abs(pmt - 2528.27) < 0.10


def test_monthly_payment_zero_rate():
    pmt = monthly_payment(120_000, 0.0, 120)
    assert abs(pmt - 1000.0) < 0.01


def test_total_interest():
    interest = total_interest(400_000, 0.065, 360)
    # total payments = 2528.27 * 360 = 910,177; interest = 910,177 - 400,000 = 510,177
    assert abs(interest - 510_177) < 10


def test_compute_scenario_a():
    result = compute_scenario_a(800_000, 0.065, 360)
    assert result["balance"] == 800_000
    assert result["annual_rate"] == 0.065
    assert result["term_months"] == 360
    assert result["monthly_payment"] > 0
    assert result["total_interest"] > 0


def test_compute_scenario_b_includes_closing_costs():
    result = compute_scenario_b(800_000, 0.055, 360, 6_000)
    assert result["closing_costs"] == 6_000
    assert result["total_cost"] == result["total_interest"] + 6_000


def test_break_even_alert_triggered():
    a = compute_scenario_a(800_000, 0.065, 360)
    # A much lower rate should trigger alert (break-even well under 24 months)
    b = compute_scenario_b(800_000, 0.04, 360, 6_000)
    result = compute_break_even(a, b, 6_000, threshold_months=24)
    assert result["should_alert"] is True
    assert result["monthly_savings"] > 0
    assert result["break_even_months"] < 24


def test_break_even_no_alert_when_rate_barely_lower():
    a = compute_scenario_a(800_000, 0.065, 360)
    # A trivially lower rate won't break even within 24 months on $6k closing costs
    b = compute_scenario_b(800_000, 0.0645, 360, 6_000)
    result = compute_break_even(a, b, 6_000, threshold_months=24)
    # savings are tiny, break-even will be very long
    assert result["should_alert"] is False or result["break_even_months"] > 24


def test_break_even_unfavorable_rate():
    a = compute_scenario_a(500_000, 0.05, 360)
    b = compute_scenario_b(500_000, 0.07, 360, 0)
    result = compute_break_even(a, b, 0, threshold_months=24)
    assert result["should_alert"] is False
    assert result["break_even_months"] == float("inf")
    assert "not beneficial" in result["reason"]


def test_break_even_zero_closing_costs():
    a = compute_scenario_a(500_000, 0.065, 360)
    b = compute_scenario_b(500_000, 0.055, 360, 0)
    result = compute_break_even(a, b, 0, threshold_months=24)
    assert result["should_alert"] is True
    assert result["break_even_months"] == 0


def test_format_currency():
    assert format_currency(1_234.56) == "$1,234.56"
    assert format_currency(-500.0) == "-$500.00"


def test_format_percent():
    assert format_percent(0.065) == "6.5%"
    assert format_percent(0.055) == "5.5%"
    assert format_percent(0.10) == "10%"
