"""Cross-country data for the panel REER anchor.

* REER: BIS broad real effective exchange rate indices (monthly, 2020 = 100), from
  FRED series ``RB<ISO2>BIS``, cached in ``data/raw/fred``.
* Fundamentals: World Bank WDI annual indicators for every panel country plus the
  world aggregate, cached in ``data/raw/worldbank_panel/<indicator>.csv``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import path
from . import fred, worldbank


@dataclass
class PanelData:
    reer: pd.DataFrame          # monthly, columns = ISO3 codes
    wdi: dict[str, pd.DataFrame]  # indicator key -> wide annual table (index year, columns ISO3 incl. WLD)
    countries: list[str]


def load(cfg: dict, refresh: bool = False) -> PanelData:
    p = cfg["panel"]
    countries = list(p["countries"])                 # ISO3
    iso2 = p["iso2"]
    fred_cache = path(cfg, "fred_cache")
    reer = {}
    for c in countries:
        s = fred.fetch_series(f"RB{iso2[c]}BIS", fred_cache, refresh=refresh)
        reer[c] = fred.to_monthly(s, "mean")
    reer = pd.DataFrame(reer).sort_index()

    wb_cache = path(cfg, "raw") / "worldbank_panel"
    wdi = {}
    for key, indicator in p["indicators"].items():
        long = worldbank.fetch_panel(countries + ["WLD"], indicator, wb_cache / f"{indicator}.csv", refresh)
        wdi[key] = long.pivot(index="year", columns="country", values="value").sort_index()
    return PanelData(reer=reer, wdi=wdi, countries=countries)
