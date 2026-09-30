"""World Bank annual indicators with a local CSV cache (data/raw/wb_*.csv)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

WB_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"


def fetch_annual(country: str, indicator: str, cache: Path, refresh: bool = False) -> pd.Series:
    """Annual series indexed by integer year."""
    if cache.exists() and not refresh:
        return read_cached(cache)
    r = requests.get(WB_URL.format(country=country, indicator=indicator),
                     params={"format": "json", "per_page": 1000}, timeout=60)
    r.raise_for_status()
    rows = {int(d["date"]): d["value"] for d in r.json()[1] if d["value"] is not None}
    s = pd.Series(rows, dtype=float).sort_index()
    out = pd.DataFrame({"value": s.values},
                       index=pd.to_datetime([f"{y}-01-01" for y in s.index]))
    out.index.name = "date"
    out.to_csv(cache, date_format="%Y-%m-%d")
    return s


def fetch_panel(countries: list[str], indicator: str, cache: Path, refresh: bool = False) -> pd.DataFrame:
    """Annual indicator for several countries: long table with columns country, year, value.

    One request covers every country; the result is cached as a CSV so runs are reproducible.
    """
    if cache.exists() and not refresh:
        return pd.read_csv(cache)
    r = requests.get(WB_URL.format(country=";".join(countries), indicator=indicator),
                     params={"format": "json", "per_page": 20000}, timeout=120)
    r.raise_for_status()
    payload = r.json()
    if len(payload) < 2 or payload[1] is None:
        raise ValueError(f"World Bank returned no data for {indicator}")
    df = pd.DataFrame([{"country": d["countryiso3code"], "year": int(d["date"]), "value": d["value"]}
                       for d in payload[1] if d["value"] is not None])
    df = df.sort_values(["country", "year"]).reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def read_cached(cache: Path) -> pd.Series:
    df = pd.read_csv(cache, index_col=0)
    # Legacy caches were re-saved by Excel as dd-mm-yyyy; new ones are ISO.
    idx = pd.to_datetime(df.index, format="mixed", dayfirst=not str(df.index[0])[:4].isdigit())
    s = pd.Series(pd.to_numeric(df.iloc[:, 0], errors="coerce").values, index=idx.year, dtype=float)
    return s.dropna().sort_index()
