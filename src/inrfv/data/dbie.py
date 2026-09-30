"""RBI DBIE data via the Reserve Bank Innovation Hub's public Data API.

The DBIE portal (data.rbi.org.in) has no public API; its gateway uses encrypted,
session-bound requests behind bot protection, and we do not try to replicate that.
The Reserve Bank Innovation Hub (an RBI subsidiary) scrapes DBIE's SDMX series and
serves them read-only, without credentials, at https://data-api.dbie.rbihub.in
(MIT-licensed; source: github.com/Reserve-Bank-Innovation-Hub/dbie.rbihub.in).

Each series is fetched once, normalised to month-start (or quarter-start) dates,
and cached as ``data/raw/dbie/<name>.csv`` so runs are reproducible offline and
the cache is covered by the raw-data checksum manifest. ``refresh=True`` re-downloads.

The DBIE Excel downloads in data/raw stay as a second source: ``merge`` combines
the two, preferring the API where both have a value and reporting disagreements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DEFAULT_BASE = "https://data-api.dbie.rbihub.in"
PAGE = 5000


@dataclass(frozen=True)
class Spec:
    """One output series: a table, the filters that select it, and how to scale it."""

    table: str                       # "<schema>/<table>"
    filters: dict = field(default_factory=dict)
    scale: float = 1.0               # multiply obs_value (e.g. 1e-6 for US$ -> US$ mn)
    quarterly: bool = False          # time_period is a quarter end -> stamp at quarter start


_MN = 1e-6
_BOP = dict(tranc_typ_rn="TRANC_NET", unit_measure="USD")

SERIES: dict[str, Spec] = {
    "inr_usd": Spec("financial_markets/forexrt_avg_rn", {"currency": "USD", "measure_rn": "AVG"}),
    "reer": Spec("external_sector/inx_neer_reer_m_rn",
                 {"typ_of_rate": "REER", "curr_bask_rn": "CURR_BASK_40CURR", "typ_trd_wts_rn": "TRD_WTS"}),
    "neer": Spec("external_sector/inx_neer_reer_m_rn",
                 {"typ_of_rate": "NEER", "curr_bask_rn": "CURR_BASK_40CURR", "typ_trd_wts_rn": "TRD_WTS"}),
    "fx_reserves_usd_mn": Spec("external_sector/fr_exg_resv_m_rn",
                               {"typ_maj_fr_exc_res_rn": "FER_TTL", "unit_measure": "USD"}, _MN),
    "exports_usd_mn": Spec("external_sector/ift_oil_non_oil_rn",
                           {"typ_of_com_trd": "TERM_TRD_EXP", "unit_measure": "USD"}, _MN),
    "imports_usd_mn": Spec("external_sector/ift_oil_non_oil_rn",
                           {"typ_of_com_trd": "TERM_TRD_IMP", "unit_measure": "USD"}, _MN),
    "fdi_usd_mn": Spec("external_sector/fr_inv_inflw_rn", {"invt_cat_rn": "INV_CAT_NET_FR_DIR_INV"}, _MN),
    "fpi_usd_mn": Spec("external_sector/fr_inv_inflw_rn", {"invt_cat_rn": "INV_CAT_NET_PORTF_INV"}, _MN),
    "wacr": Spec("financial_markets/war_call_money_rn", {"hi_lw_avg_rates_rn": "AVERAGE_RATE"}),
    # Quarterly BoP, net, US$ mn. Names match rbi.BOP_ITEMS.
    "bop.current_account": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CURR_ACC", **_BOP}, _MN, True),
    "bop.merch_balance": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CURR_MERCH", **_BOP}, _MN, True),
    "bop.private_transfers": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CURR_INVIS_TRA_PRV", **_BOP}, _MN, True),
    "bop.capital_account": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CAP_ACC", **_BOP}, _MN, True),
    "bop.fdi_bop": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CA_FI_FDI", **_BOP}, _MN, True),
    "bop.portfolio_bop": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CA_FI_FPI", **_BOP}, _MN, True),
    "bop.loans": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CA_LN", **_BOP}, _MN, True),
    "bop.banking_capital": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CA_BNK_CAP", **_BOP}, _MN, True),
    "bop.reserve_change": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "MV_FER", **_BOP}, _MN, True),
}


class DbieError(RuntimeError):
    pass


def _get_rows(base: str, spec: Spec, session: requests.Session) -> pd.DataFrame:
    url = f"{base}/api/tables/{spec.table}/rows"
    out, offset = [], 0
    while True:
        r = session.get(url, params={**spec.filters, "limit": PAGE, "offset": offset,
                                     "order": "time_period"}, timeout=120)
        if r.status_code != 200:
            raise DbieError(f"{spec.table}: HTTP {r.status_code} {r.text[:200]}")
        body = r.json()
        rows = body.get("rows", [])
        out += [dict(zip(body["columns"], x)) for x in rows]
        if len(rows) < PAGE:
            break
        offset += PAGE
    return pd.DataFrame(out)


def to_series(df: pd.DataFrame, spec: Spec, name: str) -> pd.Series:
    """Tidy SDMX rows -> one value per month (or quarter start)."""
    if df.empty:
        raise DbieError(f"{name}: no rows for filters {spec.filters}")
    t = pd.to_datetime(df["time_period"])
    per = t.dt.to_period("Q-MAR" if spec.quarterly else "M")
    stamp = (per.dt.start_time if spec.quarterly else per.dt.to_timestamp()).dt.normalize()
    vals = pd.to_numeric(df["obs_value"], errors="coerce") * spec.scale
    s = pd.Series(vals.to_numpy(), index=stamp.to_numpy(), name=name)
    dup = s.index.duplicated(keep=False)
    if dup.any():
        # Exact duplicates (seen in some tables) collapse; conflicting ones are an error.
        g = s[dup].groupby(level=0)
        if (g.max() - g.min()).abs().max() > 1e-9 * max(1.0, s.abs().max()):
            raise DbieError(f"{name}: conflicting duplicate observations")
        s = s[~s.index.duplicated(keep="last")]
    s.index.name = "date"
    return s.sort_index().dropna()


def fetch(name: str, cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
          session: requests.Session | None = None) -> pd.Series:
    cache = cache_dir / f"{name}.csv"
    if cache.exists() and not refresh:
        df = pd.read_csv(cache, parse_dates=["date"])
        return df.set_index("date")["value"].rename(name)
    spec = SERIES[name]
    s = to_series(_get_rows(base, spec, session or requests.Session()), spec, name)
    cache_dir.mkdir(parents=True, exist_ok=True)
    s.rename("value").to_frame().to_csv(cache, date_format="%Y-%m-%d")
    return s


def fetch_all(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE) -> dict[str, pd.Series]:
    session = requests.Session()
    session.headers["User-Agent"] = "inrfv (https://github.com/georgeqanfin-stack/inr-fair-value)"
    out = {name: fetch(name, cache_dir, refresh, base, session) for name in SERIES}
    if refresh:
        meta = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "base": base}
        try:
            meta["api_health"] = session.get(f"{base}/health", timeout=30).json()
        except (requests.RequestException, ValueError):
            pass
        (cache_dir / "_fetch.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def newer_first(api: pd.Series, xlsx: pd.Series) -> tuple[pd.Series, pd.Series, str]:
    """Order two sources by vintage: the one whose data reach further is the later release.

    RBI revises recent months, so where the sources overlap the later release is the
    better value. Ties go to the API.
    """
    a_end, x_end = api.last_valid_index(), xlsx.last_valid_index()
    if x_end is not None and (a_end is None or x_end > a_end):
        return xlsx, api, "xlsx"
    return api, xlsx, "api"


def reconcile(api: pd.Series, xlsx: pd.Series, rel_tol: float = 0.005, revision_window: int = 12) -> dict:
    """Compare two sources of the same series over their overlap.

    Differences within ``revision_window`` periods of the older source's end are
    expected revisions; ``n_unexpected`` counts the rest, which point to a definition
    or parsing problem.
    """
    newer, older, which = newer_first(api, xlsx)
    both = pd.concat([newer, older], axis=1, keys=["new", "old"]).dropna()
    info = {"api_range": _range(api), "xlsx_range": _range(xlsx), "newer_source": which, "overlap": len(both)}
    if len(both):
        denom = both["old"].abs().where(both["old"].abs() > 1e-12, np.nan)
        rel = ((both["new"] - both["old"]).abs() / denom).fillna(0)
        bad = rel[rel > rel_tol]
        cutoff = both.index[max(len(both) - revision_window, 0)]
        info.update({
            "max_rel_diff": float(rel.max()),
            "n_revised": int((bad.index >= cutoff).sum()),
            "n_unexpected": int((bad.index < cutoff).sum()),
            "worst": [(d.strftime("%Y-%m"), float(both.loc[d, "new"]), float(both.loc[d, "old"]))
                      for d in rel.sort_values(ascending=False).index[:3] if rel[d] > rel_tol],
        })
    return info


def merge(api: pd.Series, xlsx: pd.Series) -> pd.Series:
    """Later-vintage source where both have a value, the other source elsewhere."""
    newer, older, _ = newer_first(api, xlsx)
    return newer.combine_first(older).sort_index().rename(api.name or xlsx.name)


def monthly_gaps(s: pd.Series) -> list[str]:
    s = s.dropna()
    if s.empty:
        return []
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    return [d.strftime("%Y-%m") for d in full.difference(s.index)]


def _range(s: pd.Series) -> list[str] | None:
    s = s.dropna()
    return [s.index.min().strftime("%Y-%m"), s.index.max().strftime("%Y-%m")] if len(s) else None
