import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.rate_fetcher import fetch_current_rate, fetch_rate_history, RateFetchError


def _make_fred_series(rate=6.72, date="2025-08-07"):
    idx = pd.DatetimeIndex([date])
    return pd.Series([rate], index=idx)


def test_fetch_current_rate_fred_success():
    mock_fred = MagicMock()
    mock_fred.get_series.return_value = _make_fred_series(6.72, "2025-08-07")
    with patch("src.rate_fetcher.Fred", return_value=mock_fred):
        result = fetch_current_rate(api_key="fake_key")
    assert result["rate"] == 6.72
    assert result["date"] == "2025-08-07"
    assert "FRED" in result["source"]


def test_fetch_current_rate_falls_back_on_fred_error():
    mock_fred = MagicMock()
    mock_fred.get_series.side_effect = Exception("network error")

    mock_df = pd.DataFrame(
        {"date": ["2025-08-07"], "rate_30yr": [6.55]}
    ).assign(date=lambda df: pd.to_datetime(df["date"])).set_index("date")

    with patch("src.rate_fetcher.Fred", return_value=mock_fred), \
         patch("src.rate_fetcher._load_freddie_mac_df", return_value=mock_df):
        result = fetch_current_rate(api_key="fake_key")
    assert result["rate"] == 6.55
    assert "Freddie Mac" in result["source"]


def test_fetch_current_rate_no_key_uses_freddie_mac():
    mock_df = pd.DataFrame(
        {"date": ["2025-08-07"], "rate_30yr": [6.55]}
    ).assign(date=lambda df: pd.to_datetime(df["date"])).set_index("date")

    with patch("src.rate_fetcher._load_freddie_mac_df", return_value=mock_df):
        result = fetch_current_rate(api_key="")
    assert result["rate"] == 6.55


def test_fetch_current_rate_all_fail_raises():
    with patch("src.rate_fetcher._load_freddie_mac_df", side_effect=Exception("fail")):
        with pytest.raises(RateFetchError):
            fetch_current_rate(api_key="")


def test_fetch_rate_history_fred():
    idx = pd.date_range("2025-01-01", periods=4, freq="W")
    mock_series = pd.Series([6.8, 6.9, 6.7, 6.72], index=idx)
    mock_fred = MagicMock()
    mock_fred.get_series.return_value = mock_series
    with patch("src.rate_fetcher.Fred", return_value=mock_fred):
        history = fetch_rate_history(api_key="fake_key", months=12)
    assert len(history) == 4
