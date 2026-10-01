"""Net foreign assets from the External Wealth of Nations database (Lane & Milesi-Ferretti).

The EWN workbook (Brookings, one vintage a year, ~3 MB) is located from its landing
page, downloaded to ``data/raw/ewn/`` and reduced to a compact CSV of the panel
countries, ``data/raw/ewn/ewn_nfa.csv`` (country, year, nfa_ewn, nfa_official, in % of
GDP). Runs read the CSV, so they are reproducible without the network; ``refresh``
looks for a newer vintage and keeps the cached CSV if the site cannot be reached.

* ``nfa_ewn``: net IIP excluding gold / GDP, the authors' estimates (portfolio equity
  at market value, consistent across countries and back to 1970).
* ``nfa_official``: net IIP as reported by national authorities (incl. gold) / GDP.

Both ratios are computed by EWN with GDP in domestic currency, so exchange-rate
swings do not move the ratio through the denominator.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import requests

PAGE = "https://www.brookings.edu/articles/the-external-wealth-of-nations-database/"
NAMES = {  # EWN country name -> ISO3
    "India": "IND", "China,P.R.: Mainland": "CHN", "Brazil": "BRA", "Mexico": "MEX",
    "Indonesia": "IDN", "Turkey": "TUR", "South Africa": "ZAF", "Korea": "KOR",
    "Thailand": "THA", "Malaysia": "MYS", "Philippines": "PHL", "Chile": "CHL",
    "Colombia": "COL", "Peru": "PER", "Poland": "POL", "Hungary": "HUN",
    "Czech Republic": "CZE", "Israel": "ISR", "Romania": "ROU",
}
COLUMNS = {"net IIP excl gold / GDP domestic currency": "nfa_ewn",
           "net IIP / GDP domestic currency": "nfa_official"}
HEADERS = {"User-Agent": "Mozilla/5.0 (inr-fair-value research pipeline)"}


def latest_url(page: str = PAGE) -> str:
    r = requests.get(page, headers=HEADERS, timeout=60)
    r.raise_for_status()
    links = sorted(set(re.findall(r'https://[^"\']+EWN[^"\']+\.xlsx', r.text)))
    if not links:
        raise ValueError("No EWN workbook link found on the Brookings page")
    return links[-1]


def parse(xlsx: Path, countries: list[str]) -> pd.DataFrame:
    df = pd.read_excel(xlsx, sheet_name="Dataset")
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"EWN workbook layout changed; missing columns {sorted(missing)}")
    df["country"] = df["Country"].map(NAMES)
    df = df[df["country"].isin(countries)]
    out = df[["country", "Year"] + list(COLUMNS)].rename(columns={"Year": "year", **COLUMNS})
    for c in COLUMNS.values():
        out[c] = pd.to_numeric(out[c], errors="coerce") * 100
    return out.sort_values(["country", "year"]).reset_index(drop=True)


def load(countries: list[str], cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    """Long table: country, year, nfa_ewn, nfa_official (% of GDP)."""
    csv = cache_dir / "ewn_nfa.csv"
    if refresh or not csv.exists():
        try:
            url = latest_url()
            xlsx = cache_dir / url.rsplit("/", 1)[-1]
            if not xlsx.exists():
                cache_dir.mkdir(parents=True, exist_ok=True)
                r = requests.get(url, headers=HEADERS, timeout=300)
                r.raise_for_status()
                xlsx.write_bytes(r.content)
            df = parse(xlsx, countries)
            df.to_csv(csv, index=False, float_format="%.6g")
            (cache_dir / "SOURCE.txt").write_text(url + "\n")
        except (requests.RequestException, ValueError):
            if not csv.exists():
                raise
    df = pd.read_csv(csv)
    absent = set(countries) - set(df["country"])
    if absent:
        raise ValueError(f"EWN cache lacks {sorted(absent)}; rerun with refresh")
    return df
