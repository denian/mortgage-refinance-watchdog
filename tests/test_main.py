import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def _mock_config():
    return {
        "loan": {"balance": 800_000, "rate": 0.065, "remaining_months": 360},
        "refinance": {"new_term_months": 360, "closing_costs": 6_000, "break_even_threshold_months": 24},
        "email": {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "", "recipient": ""},
        "secrets": {"FRED_API_KEY": "", "SMTP_PASSWORD": ""},
    }


def test_run_dry_run(tmp_path):
    import src.report as report_module
    original_dir = report_module.REPORTS_DIR
    report_module.REPORTS_DIR = tmp_path

    rate_data = {"rate": 5.5, "date": "2025-08-07", "source": "FRED"}
    history = pd.Series(dtype=float)

    try:
        with patch("main.get_full_config", return_value=_mock_config()), \
             patch("main.fetch_current_rate", return_value=rate_data), \
             patch("main.fetch_rate_history", return_value=history):
            from main import run
            run(dry_run=True)
    finally:
        report_module.REPORTS_DIR = original_dir

    assert (tmp_path / "latest.md").exists()


def test_run_exits_on_rate_fetch_failure():
    from src.rate_fetcher import RateFetchError
    with patch("main.get_full_config", return_value=_mock_config()), \
         patch("main.fetch_current_rate", side_effect=RateFetchError("fail")):
        from main import run
        with pytest.raises(SystemExit):
            run(dry_run=True)
