from datetime import date

import pytest
from src.calculator import (
    monthly_payment,
    total_interest,
    compute_scenario_a,
    compute_scenario_b,
    compute_scenario_remaining,
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


def test_compute_scenario_remaining_no_history_matches_original():
    # As of the day before the first payment, nothing has changed yet
    result = compute_scenario_remaining(
        800_000, 0.065, 360, date(2026, 4, 1), [], as_of=date(2026, 3, 31)
    )
    assert result["balance"] == 800_000
    assert result["term_months"] == 360
    assert abs(result["interest_saved"]) < 0.01
    assert result["extra_principal_paid"] == 0


def test_compute_scenario_remaining_known_schedule():
    # Regression values for a fixed scenario. The simulation model (scheduled
    # payments on their due dates, extra payments applied on their own dates)
    # was originally validated to the dollar against a real servicer statement.
    payments = [
        {"date": date(2025, 3, 10), "amount": 8_000},
        {"date": date(2025, 6, 5), "amount": 5_000},
    ]
    result = compute_scenario_remaining(
        500_000, 0.06, 360, date(2025, 2, 1), payments, as_of=date(2025, 7, 15)
    )
    assert result["monthly_payment"] == pytest.approx(2_997.75, abs=0.01)
    assert result["balance"] == pytest.approx(483_789.70, abs=0.01)
    assert result["term_months"] == 329
    assert result["extra_principal_paid"] == 13_000
    assert result["interest_saved"] == pytest.approx(59_686.77, abs=0.01)
    # Lifetime interest = original total interest minus interest saved
    original = total_interest(500_000, 0.06, 360)
    assert result["total_interest"] == pytest.approx(
        original - result["interest_saved"], abs=0.01
    )


def test_compute_scenario_remaining_extra_payment_today_saves_more():
    # Basis of the what-if widget: adding a hypothetical payment today
    # strictly increases interest saved, and larger payments save more.
    today = date(2025, 7, 15)
    payments = [{"date": date(2025, 3, 10), "amount": 8_000}]

    def saved(extra: float) -> float:
        extras = payments + ([{"date": today, "amount": extra}] if extra else [])
        return compute_scenario_remaining(
            500_000, 0.06, 360, date(2025, 2, 1), extras, as_of=today
        )["interest_saved"]

    base = saved(0)
    assert saved(1_000) > base
    assert saved(10_000) > saved(1_000)
    assert saved(25_000) > saved(10_000)
    # Each prepaid dollar saves several dollars of interest on a young 30-yr loan
    assert (saved(10_000) - base) / 10_000 > 2


def test_compute_scenario_remaining_ignores_future_payments():
    payments = [{"date": date(2026, 8, 1), "amount": 50_000}]
    result = compute_scenario_remaining(
        800_000, 0.065, 360, date(2026, 4, 1), payments, as_of=date(2026, 7, 13)
    )
    assert result["extra_principal_paid"] == 0


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
