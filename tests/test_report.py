import pandas as pd
from pathlib import Path
from src.report import build_report_data, render_markdown, save_report, print_console_report
from src.calculator import compute_scenario_a, compute_scenario_b, compute_break_even


def _fixture():
    a = compute_scenario_a(800_000, 0.065, 360)
    b = compute_scenario_b(800_000, 0.055, 360, 6_000)
    analysis = compute_break_even(a, b, 6_000, threshold_months=24)
    rate_data = {"rate": 5.5, "date": "2025-08-07", "source": "FRED MORTGAGE30US"}
    idx = pd.date_range("2025-01-01", periods=12, freq="W")
    history = pd.Series([6.5, 6.4, 6.3, 6.2, 6.1, 6.0, 5.9, 5.8, 5.7, 5.6, 5.5, 5.5], index=idx)
    return build_report_data(rate_data, a, b, analysis, history, run_date="2025-08-07")


def test_render_markdown_contains_key_sections():
    md = render_markdown(_fixture())
    assert "## Scenario Comparison" in md
    assert "## Break-Even Analysis" in md
    assert "## Recommendation" in md
    assert "ALERT" in md or "NOT YET" in md


def test_render_markdown_contains_numbers():
    md = render_markdown(_fixture())
    assert "$800,000" in md
    assert "6.5%" in md
    assert "5.5%" in md


def test_render_markdown_contains_52_week_range():
    md = render_markdown(_fixture())
    assert "52-week range" in md


def test_save_report_creates_files(tmp_path):
    import src.report as report_module
    original = report_module.REPORTS_DIR
    report_module.REPORTS_DIR = tmp_path
    try:
        md = render_markdown(_fixture())
        path = save_report(md, "2025-08-07")
        assert path.exists()
        assert (tmp_path / "latest.md").exists()
        assert path.name == "report_2025-08-07.md"
    finally:
        report_module.REPORTS_DIR = original


def test_print_console_report_runs_without_error(capsys):
    print_console_report(_fixture())
    captured = capsys.readouterr()
    assert "MORTGAGE REFINANCE WATCHDOG" in captured.out
    assert "RECOMMENDATION" in captured.out
