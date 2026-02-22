import io
import warnings
from datetime import datetime, timedelta

import pandas as pd
import requests
from fredapi import Fred


class RateFetchError(Exception):
    pass


_STALENESS_DAYS = 10
_REQUEST_TIMEOUT = 15
_FREDDIE_MAC_URL = (
    "https://www.freddiemac.com/pmms/docs/historicalweeklydata.xls"
)


def fetch_current_rate(api_key: str = "") -> dict:
    errors = []

    if api_key:
        try:
            return _fetch_from_fred(api_key)
        except Exception as exc:
            errors.append(f"FRED: {exc}")

    try:
        return _fetch_from_freddie_mac()
    except Exception as exc:
        errors.append(f"Freddie Mac: {exc}")

    raise RateFetchError(
        "All rate sources failed. Details:\n  " + "\n  ".join(errors)
    )


def fetch_rate_history(api_key: str = "", months: int = 12) -> pd.Series:
    start = (pd.Timestamp.today() - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    errors = []

    if api_key:
        try:
            fred = Fred(api_key=api_key)
            series = fred.get_series("MORTGAGE30US", observation_start=start)
            return series.dropna()
        except Exception as exc:
            errors.append(f"FRED history: {exc}")

    try:
        df = _load_freddie_mac_df()
        return df["rate_30yr"].dropna().loc[start:]
    except Exception as exc:
        errors.append(f"Freddie Mac history: {exc}")

    raise RateFetchError(
        "Could not fetch rate history. Details:\n  " + "\n  ".join(errors)
    )


def _fetch_from_fred(api_key: str) -> dict:
    fred = Fred(api_key=api_key)
    series = fred.get_series("MORTGAGE30US").dropna()
    if series.empty:
        raise RateFetchError("MORTGAGE30US series is empty")
    latest_date = series.index[-1]
    latest_rate = float(series.iloc[-1])
    _check_staleness(latest_date.to_pydatetime(), "FRED")
    return {
        "rate": round(latest_rate, 2),
        "date": latest_date.strftime("%Y-%m-%d"),
        "source": "FRED MORTGAGE30US (Freddie Mac PMMS)",
    }


def _fetch_from_freddie_mac() -> dict:
    df = _load_freddie_mac_df()
    latest = df["rate_30yr"].dropna()
    if latest.empty:
        raise RateFetchError("Freddie Mac Excel file contains no rate data")
    latest_date = latest.index[-1]
    latest_rate = float(latest.iloc[-1])
    _check_staleness(
        latest_date.to_pydatetime() if hasattr(latest_date, "to_pydatetime") else latest_date,
        "Freddie Mac",
    )
    return {
        "rate": round(latest_rate, 2),
        "date": pd.Timestamp(latest_date).strftime("%Y-%m-%d"),
        "source": "Freddie Mac PMMS (direct download)",
    }


def _load_freddie_mac_df() -> pd.DataFrame:
    resp = requests.get(_FREDDIE_MAC_URL, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(io.BytesIO(resp.content), header=None)
    header_row = _find_header_row(df)
    df = pd.read_excel(io.BytesIO(resp.content), header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    rate_col = df.columns[1]
    df = df[[date_col, rate_col]].copy()
    df.columns = ["date", "rate_30yr"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    df["rate_30yr"] = pd.to_numeric(df["rate_30yr"], errors="coerce")
    return df


def _find_header_row(df: pd.DataFrame) -> int:
    for i, row in df.iterrows():
        values = [str(v).lower() for v in row.values if pd.notna(v)]
        if any("date" in v or "week" in v or "1971" in v for v in values):
            return i
        if any(v.replace(".", "").isdigit() and 1960 < float(v) < 2100 for v in values if v.replace(".", "").isdigit()):
            return i
    return 6


def _check_staleness(date: datetime, source: str) -> None:
    if isinstance(date, pd.Timestamp):
        date = date.to_pydatetime()
    age_days = (datetime.now() - date.replace(tzinfo=None)).days
    if age_days > _STALENESS_DAYS:
        print(
            f"[mortgage-monitor] WARNING: {source} data is {age_days} days old "
            f"(last observation: {date.date()}). The source may not have updated yet."
        )
