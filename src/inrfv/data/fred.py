"""FRED series with a local CSV cache.

A cached series is reused unless ``refresh=True``, so runs are reproducible
offline and the cache is checksummed with the rest of data/raw.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import requests

FREDGRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def _download(sid: str, api_key: str | None) -> pd.Series:
    if api_key:
        from fredapi import Fred

        s = Fred(api_key=api_key).get_series(sid)
    else:
        r = requests.get(FREDGRAPH_URL.format(sid=sid), timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), na_values=["."])
        df.columns = ["date", "value"]
        s = df.set_index(pd.to_datetime(df["date"]))["value"]
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    s.index.name = "date"
    s.name = sid
    return s.sort_index()


def fetch_series(sid: str, cache_dir: Path, refresh: bool = False,
                 api_key: str | None = None) -> pd.Series:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{sid}.csv"
    if cache.exists() and not refresh:
        df = pd.read_csv(cache, parse_dates=["date"])
        s = df.set_index("date")["value"]
        s.name = sid
        return s
    s = _download(sid, api_key if api_key is not None else os.environ.get("FRED_API_KEY") or None)
    s.rename("value").to_frame().to_csv(cache, date_format="%Y-%m-%d")
    return s


def to_monthly(s: pd.Series, how: str = "mean") -> pd.Series:
    """Collapse to month-start timestamps. Monthly input passes through unchanged."""
    grouped = s.groupby(s.index.to_period("M"))
    out = getattr(grouped, how)()
    out.index = out.index.to_timestamp()
    return out


def ratio_splice(primary: pd.Series, backfill: pd.Series, overlap_months: int = 12) -> tuple[pd.Series, float]:
    """Extend ``primary`` backwards with ``backfill`` rescaled to primary's level.

    The scale factor is the mean ratio primary/backfill over the first
    ``overlap_months`` months where both exist. Raises if there is no overlap.
    """
    both = pd.concat([primary, backfill], axis=1, keys=["p", "b"]).dropna()
    if both.empty:
        raise ValueError("ratio_splice: series do not overlap")
    ratio = float((both["p"] / both["b"]).iloc[:overlap_months].mean())
    start = primary.dropna().index.min()
    early = backfill[backfill.index < start] * ratio
    return pd.concat([early, primary[primary.index >= start]]).sort_index(), ratio
