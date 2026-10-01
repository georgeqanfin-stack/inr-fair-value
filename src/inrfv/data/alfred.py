"""US data as first published: FRED's real-time archive (ALFRED).

FRED revises US CPI (mostly seasonal factors). The pipeline otherwise uses today's
revised series with a fixed one-month publication lag. With ALFRED, US inflation at
month-end t is computed from the CPI vintage that was public at t: the latest
observation released by then, over the same month a year earlier, both as known at t.
That captures revisions and the actual release calendar.

ALFRED's vintage history needs a FRED API key (environment variable FRED_API_KEY, or
a .env file). All releases are cached in data/raw/alfred/<series>.csv
(date, realtime_start, value), so runs stay reproducible without the key once the
cache exists. Without a key or cache the pipeline falls back to the revised series
and says so in the run metadata.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def fetch_releases(sid: str, cache_dir: Path, api_key: str | None, refresh: bool = False) -> pd.DataFrame | None:
    cache = cache_dir / f"{sid}.csv"
    if cache.exists() and not (refresh and api_key):
        return pd.read_csv(cache, parse_dates=["date", "realtime_start"])
    if not api_key:
        return None
    from fredapi import Fred

    df = Fred(api_key=api_key).get_series_all_releases(sid)
    df = df[["date", "realtime_start", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["realtime_start"] = pd.to_datetime(df["realtime_start"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna().sort_values(["date", "realtime_start"]).reset_index(drop=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False, date_format="%Y-%m-%d")
    return df


def as_known(releases: pd.DataFrame, t: pd.Timestamp) -> pd.Series:
    """The whole series as it stood at the end of month ``t``."""
    cut = t + pd.offsets.MonthEnd(0)
    known = releases[releases["realtime_start"] <= cut]
    return known.groupby("date")["value"].last().sort_index()


def yoy_as_known(releases: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.Series:
    """Year-on-year % change of the latest observation public at each month-end."""
    out = {}
    for t in idx:
        s = as_known(releases, t)
        if s.empty:
            continue
        last = s.index[-1]
        prev = last - pd.DateOffset(years=1)
        out[t] = (s[last] / s[prev] - 1) * 100 if prev in s.index else np.nan
    return pd.Series(out, dtype=float).reindex(idx)


def first_release(releases: pd.DataFrame) -> pd.Series:
    """Each observation as first published."""
    return releases.sort_values("realtime_start").groupby("date")["value"].first().sort_index()
