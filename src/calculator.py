from datetime import date

import numpy_financial as npf


def monthly_payment(principal: float, annual_rate: float, n_months: int) -> float:
    if annual_rate == 0:
        return principal / n_months
    return float(-npf.pmt(rate=annual_rate / 12, nper=n_months, pv=principal))


def total_interest(principal: float, annual_rate: float, n_months: int) -> float:
    return monthly_payment(principal, annual_rate, n_months) * n_months - principal


def compute_scenario_a(balance: float, annual_rate: float, remaining_months: int) -> dict:
    pmt = monthly_payment(balance, annual_rate, remaining_months)
    return {
        "label": "Current Loan (no refinance)",
        "balance": balance,
        "annual_rate": annual_rate,
        "term_months": remaining_months,
        "monthly_payment": pmt,
        "total_interest": total_interest(balance, annual_rate, remaining_months),
    }


def compute_scenario_remaining(
    balance: float,
    annual_rate: float,
    term_months: int,
    first_payment_date: date,
    principal_payments: list[dict],
    as_of: date | None = None,
) -> dict:
    """Current loan as of `as_of`, accounting for scheduled payments made since
    `first_payment_date` and any extra principal-only payments.

    Extra payments keep the monthly payment the same but shorten the term, so
    the remaining term and lifetime interest are found by simulating the
    amortization schedule rather than by closed formula.
    """
    as_of = as_of or date.today()
    pmt = monthly_payment(balance, annual_rate, term_months)
    full_interest = total_interest(balance, annual_rate, term_months)
    monthly_rate = annual_rate / 12

    events = []
    for k in range(term_months):
        due = _add_months(first_payment_date, k)
        if due > as_of:
            break
        events.append((due, 0, pmt))  # scheduled payment (0 sorts before extras same-day)
    extra_paid = 0.0
    for p in principal_payments:
        if p["date"] <= as_of:
            events.append((p["date"], 1, float(p["amount"])))
            extra_paid += float(p["amount"])
    events.sort(key=lambda e: (e[0], e[1]))

    remaining = balance
    interest_paid = 0.0
    for _, kind, amount in events:
        if remaining <= 0:
            break
        if kind == 0:
            interest = remaining * monthly_rate
            interest_paid += interest
            remaining -= min(pmt - interest, remaining)
        else:
            remaining -= min(amount, remaining)

    # Simulate the rest of the schedule to payoff. Count full months only;
    # a small final partial payment doesn't count as a remaining month.
    future_balance = remaining
    future_interest = 0.0
    remaining_months = 0
    while future_balance > 0.005:
        interest = future_balance * monthly_rate
        future_interest += interest
        principal = min(pmt - interest, future_balance)
        future_balance -= principal
        if principal >= pmt - interest - 0.005:
            remaining_months += 1

    lifetime_interest = interest_paid + future_interest
    return {
        "label": "Current Loan (remaining)",
        "balance": remaining,
        "annual_rate": annual_rate,
        "term_months": remaining_months,
        "monthly_payment": pmt,
        "total_interest": lifetime_interest,
        "interest_saved": full_interest - lifetime_interest,
        "extra_principal_paid": extra_paid,
        "total_cost": balance + lifetime_interest,
    }


def _add_months(d: date, n: int) -> date:
    year, month = divmod(d.month - 1 + n, 12)
    return date(d.year + year, month + 1, min(d.day, 28))


def compute_scenario_b(
    balance: float,
    new_annual_rate: float,
    new_term_months: int,
    closing_costs: float,
) -> dict:
    pmt = monthly_payment(balance, new_annual_rate, new_term_months)
    interest = total_interest(balance, new_annual_rate, new_term_months)
    return {
        "label": "Refinanced Loan",
        "balance": balance,
        "annual_rate": new_annual_rate,
        "term_months": new_term_months,
        "monthly_payment": pmt,
        "total_interest": interest,
        "closing_costs": closing_costs,
        "total_cost": interest + closing_costs,
    }


def compute_break_even(
    scenario_a: dict,
    scenario_b: dict,
    closing_costs: float,
    threshold_months: int = 24,
) -> dict:
    monthly_savings = scenario_a["monthly_payment"] - scenario_b["monthly_payment"]
    lifetime_savings = scenario_a["total_interest"] - scenario_b["total_cost"]

    if monthly_savings <= 0:
        return {
            "monthly_savings": monthly_savings,
            "break_even_months": float("inf"),
            "lifetime_savings": lifetime_savings,
            "should_alert": False,
            "reason": (
                f"The new rate ({format_percent(scenario_b['annual_rate'])}) is not "
                f"low enough to reduce your monthly payment. Your payment would "
                f"{'increase' if monthly_savings < 0 else 'stay the same'} by "
                f"{format_currency(abs(monthly_savings))}/mo. Refinancing is not beneficial."
            ),
        }

    if closing_costs == 0:
        return {
            "monthly_savings": monthly_savings,
            "break_even_months": 0,
            "lifetime_savings": lifetime_savings,
            "should_alert": True,
            "reason": (
                f"No closing costs — you save {format_currency(monthly_savings)}/mo immediately."
            ),
        }

    break_even_months = closing_costs / monthly_savings
    should_alert = break_even_months <= threshold_months

    if should_alert:
        reason = (
            f"Break-even in {break_even_months:.1f} months "
            f"({break_even_months / 12:.1f} years), which is within your "
            f"{threshold_months}-month threshold. You save "
            f"{format_currency(monthly_savings)}/mo and "
            f"{format_currency(lifetime_savings)} over the life of the loan."
        )
    else:
        reason = (
            f"Break-even in {break_even_months:.1f} months "
            f"({break_even_months / 12:.1f} years), which exceeds your "
            f"{threshold_months}-month threshold. Rates are not low enough yet."
        )

    return {
        "monthly_savings": monthly_savings,
        "break_even_months": break_even_months,
        "lifetime_savings": lifetime_savings,
        "should_alert": should_alert,
        "reason": reason,
    }


def format_currency(value: float) -> str:
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def format_percent(value: float) -> str:
    s = f"{value * 100:.3f}".rstrip("0").rstrip(".")
    return f"{s}%"
