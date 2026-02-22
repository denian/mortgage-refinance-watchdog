from datetime import date
from pathlib import Path

import pandas as pd

from .calculator import format_currency, format_percent

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def build_report_data(
    rate_data: dict,
    scenario_a: dict,
    scenario_b: dict,
    analysis: dict,
    history: pd.Series,
    run_date: str = "",
) -> dict:
    run_date = run_date or date.today().isoformat()
    week_high = float(history.max()) if not history.empty else None
    week_low = float(history.min()) if not history.empty else None
    return {
        "run_date": run_date,
        "rate_data": rate_data,
        "scenario_a": scenario_a,
        "scenario_b": scenario_b,
        "analysis": analysis,
        "week_high": week_high,
        "week_low": week_low,
    }


def print_console_report(report_data: dict) -> None:
    d = report_data
    a = d["scenario_a"]
    b = d["scenario_b"]
    analysis = d["analysis"]
    rate = d["rate_data"]

    sep = "=" * 60
    print(sep)
    print(f"  MORTGAGE REFINANCE WATCHDOG — {d['run_date']}")
    print(sep)

    print(f"\nData Source : {rate['source']}")
    print(f"Rate Date   : {rate['date']}")
    print(f"Current Rate: {rate['rate']}%  (30-yr fixed, national avg)")

    if d["week_high"] is not None:
        print(
            f"52-Wk Range : {d['week_low']:.2f}% — {d['week_high']:.2f}%"
        )

    print(f"\n{'─' * 60}")
    print(f"  SCENARIO COMPARISON")
    print(f"{'─' * 60}")
    rows = _comparison_rows(a, b)
    col_w = 28
    print(f"  {'Metric':<{col_w}} {'Current Loan':>16}  {'Refinanced':>16}")
    print(f"  {'─' * col_w} {'─' * 16}  {'─' * 16}")
    for label, va, vb in rows:
        print(f"  {label:<{col_w}} {va:>16}  {vb:>16}")

    print(f"\n{'─' * 60}")
    print(f"  BREAK-EVEN ANALYSIS")
    print(f"{'─' * 60}")
    be = analysis["break_even_months"]
    print(f"  Monthly savings  : {format_currency(analysis['monthly_savings'])}")
    if be == float("inf"):
        print(f"  Break-even       : N/A (no savings)")
    else:
        print(f"  Break-even       : {be:.1f} months ({be / 12:.1f} years)")
    print(f"  Lifetime savings : {format_currency(analysis['lifetime_savings'])}")

    print(f"\n{'─' * 60}")
    verdict = "✅  ALERT: REFINANCE NOW" if analysis["should_alert"] else "⏳  NOT YET: RATES TOO HIGH"
    print(f"  RECOMMENDATION: {verdict}")
    print(f"{'─' * 60}")
    print(f"  {analysis['reason']}")
    print(sep + "\n")


def render_markdown(report_data: dict) -> str:
    d = report_data
    a = d["scenario_a"]
    b = d["scenario_b"]
    analysis = d["analysis"]
    rate = d["rate_data"]
    be = analysis["break_even_months"]

    verdict = "✅ ALERT: REFINANCE NOW" if analysis["should_alert"] else "⏳ NOT YET: RATES TOO HIGH"

    lines = [
        f"# Mortgage Refinance Watchdog Report",
        f"",
        f"**Run date:** {d['run_date']}  ",
        f"**Data source:** {rate['source']}  ",
        f"**Rate observation date:** {rate['date']}  ",
        f"**Current 30-yr fixed rate:** {rate['rate']}%",
        f"",
    ]

    if d["week_high"] is not None:
        lines += [
            f"**52-week range:** {d['week_low']:.2f}% – {d['week_high']:.2f}%",
            f"",
        ]

    lines += [
        f"---",
        f"",
        f"## Scenario Comparison",
        f"",
        f"| Metric | Current Loan | Refinanced Loan |",
        f"|---|---|---|",
    ]
    for label, va, vb in _comparison_rows(a, b):
        lines.append(f"| {label} | {va} | {vb} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Break-Even Analysis",
        f"",
        f"```",
        f"monthly_savings    = {format_currency(analysis['monthly_savings'])}",
    ]
    if be == float("inf"):
        lines.append("break_even_months  = N/A (no monthly savings)")
    else:
        lines += [
            f"break_even_months  = {format_currency(b['closing_costs'])} ÷ "
            f"{format_currency(analysis['monthly_savings'])}/mo = {be:.1f} months",
        ]
    lines += [
        f"lifetime_savings   = {format_currency(analysis['lifetime_savings'])}",
        f"```",
        f"",
        f"---",
        f"",
        f"## Recommendation",
        f"",
        f"### {verdict}",
        f"",
        f"{analysis['reason']}",
        f"",
    ]

    return "\n".join(lines)


def save_report(markdown: str, run_date: str = "") -> Path:
    run_date = run_date or date.today().isoformat()
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamped = REPORTS_DIR / f"report_{run_date}.md"
    timestamped.write_text(markdown, encoding="utf-8")
    latest = REPORTS_DIR / "latest.md"
    latest.write_text(markdown, encoding="utf-8")
    return timestamped


def _comparison_rows(a: dict, b: dict) -> list[tuple[str, str, str]]:
    be_months = int(b["term_months"] / 12)
    a_months = int(a["term_months"] / 12)
    return [
        ("Loan Balance",
         format_currency(a["balance"]),
         format_currency(b["balance"])),
        ("Interest Rate",
         format_percent(a["annual_rate"]),
         format_percent(b["annual_rate"])),
        ("Term",
         f"{a_months} years ({a['term_months']} mo)",
         f"{be_months} years ({b['term_months']} mo)"),
        ("Monthly Payment",
         format_currency(a["monthly_payment"]),
         format_currency(b["monthly_payment"])),
        ("Total Interest",
         format_currency(a["total_interest"]),
         format_currency(b["total_interest"])),
        ("Closing Costs",
         "—",
         format_currency(b["closing_costs"])),
        ("Total Cost",
         format_currency(a["balance"] + a["total_interest"]),
         format_currency(b["balance"] + b["total_cost"])),
    ]
