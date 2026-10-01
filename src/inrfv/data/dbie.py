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
    order: str = "time_period"       # sheet-layout tables (publications) have row_no instead


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

# API-only inputs for the FEER (no Excel counterpart in data/raw).
_GROSS = dict(unit_measure="USD")
EXTRA: dict[str, Spec] = {
    "oil_imports_usd_mn": Spec("external_sector/bcci_mer_trd_rn", {"typ_of_com_trd": "COMM_OIL", "unit_measure": "USD"}, _MN),
    "oil_exports_usd_mn": Spec("external_sector/bcci_mer_trd_rn", {"typ_of_com_trd": "COMM_OIL1", "unit_measure": "USD"}, _MN),
    "bopx.goods_credit": Spec("external_sector/ind_ovr_bop_rn",
                              {"io_bop_rn": "CURR_MERCH", "tranc_typ_rn": "TRANC_CRD", **_GROSS}, _MN, True),
    "bopx.goods_debit": Spec("external_sector/ind_ovr_bop_rn",
                             {"io_bop_rn": "CURR_MERCH", "tranc_typ_rn": "TRANC_DEB", **_GROSS}, _MN, True),
    "bopx.services_credit": Spec("external_sector/ind_ovr_bop_rn",
                                 {"io_bop_rn": "CURR_INVIS_SER", "tranc_typ_rn": "TRANC_CRD", **_GROSS}, _MN, True),
    "bopx.services_debit": Spec("external_sector/ind_ovr_bop_rn",
                                {"io_bop_rn": "CURR_INVIS_SER", "tranc_typ_rn": "TRANC_DEB", **_GROSS}, _MN, True),
    "bopx.niip": Spec("external_sector/intr_inv_pos_ind_bpm6_rn",
                      {"inter_invs_typ_rn": "IIA_NET_IIP", "unit_measure": "USD"}, _MN, True),
    # Official India CPI (MOSPI CPI-Combined; Labour Bureau CPI-IW before 2011).
    "cpi.combined_2012": Spec("real_sector/cpi_ruc_rn",
                              {"base_per": "BY_2012", "comd_item": "C_GIAG", "coverage_geo_rn": "ALL_INDIA"}),
    "cpi.combined_2012_bs": Spec("real_sector/cpi_ruc_rn",
                                 {"base_per": "BY_2012_BS", "comd_item": "C_GIAG", "coverage_geo_rn": "ALL_INDIA"}),
    "cpi.iw_1982": Spec("real_sector/cpi_iw_rn", {"base_per": "BY_1982", "comd_item": "CO_GIAG"}),
    "cpi.iw_2001": Spec("real_sector/cpi_iw_rn", {"base_per": "BY_2001", "comd_item": "CO_GIAG"}),
    # Older BPM5-basis IIP (2006-2021), spliced onto the BPM6 series by the REER anchor.
    "bopx.niip_bpm5": Spec("external_sector/intr_inv_pos_ind_rn",
                           {"intl_inv_typ_rn": "IIA_NET_IIP", "unit_measure": "USD"}, _MN, True),
    # Inter-bank forward premia, monthly average, % a year (the market's INR-USD rate differential).
    "fwd_premium_1m": Spec("financial_markets/fw_pre_rn", {"avg_month_rn": "1_MON"}),
    "fwd_premium_3m": Spec("financial_markets/fw_pre_rn", {"avg_month_rn": "3_MON"}),
    "fwd_premium_6m": Spec("financial_markets/fw_pre_rn", {"avg_month_rn": "6_MON"}),
}
SERIES.update(EXTRA)


class DbieError(RuntimeError):
    pass


def _get_rows(base: str, spec: Spec, session: requests.Session) -> pd.DataFrame:
    url = f"{base}/api/tables/{spec.table}/rows"
    out, offset = [], 0
    while True:
        r = session.get(url, params={**spec.filters, "limit": PAGE, "offset": offset,
                                     "order": spec.order}, timeout=120)
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
    downloaded = refresh or any(not (cache_dir / f"{n}.csv").exists() for n in SERIES)
    out = {name: fetch(name, cache_dir, refresh, base, session) for name in SERIES}
    if downloaded:
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


def merge_older(api: pd.Series, xlsx: pd.Series) -> pd.Series:
    """Earlier-vintage source where both have a value: the data as first seen, for revision checks."""
    newer, older, _ = newer_first(api, xlsx)
    return older.combine_first(newer).sort_index().rename(api.name or xlsx.name)


def monthly_gaps(s: pd.Series) -> list[str]:
    s = s.dropna()
    if s.empty:
        return []
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    return [d.strftime("%Y-%m") for d in full.difference(s.index)]


def _range(s: pd.Series) -> list[str] | None:
    s = s.dropna()
    return [s.index.min().strftime("%Y-%m"), s.index.max().strftime("%Y-%m")] if len(s) else None


# --------------------------------------------------------------------------- RBI intervention

INTERVENTION_TABLE = "financial_sector/r14_sale_purchase_of_u_s_dollar_by_the_rbi"   # RBI Bulletin Table 4
INTERVENTION_TAB = "Sale/Purchase of USD by RBI"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                      "August", "September", "October", "November", "December"], 1)}


def _num(s: pd.Series) -> pd.Series:
    """Bulletin cells: Indian digit grouping ("1,39,197"), "-" for no transaction."""
    s = s.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(s.mask(s.isin(["-", "–"]), "0"), errors="coerce")


def parse_intervention(rows: pd.DataFrame) -> pd.DataFrame:
    """RBI Bulletin Table 4 (sheet layout) -> monthly US$ mn.

    Columns: net_purchase (spot, incl. swap and forward legs at value date; + = purchase),
    purchase, sale, fwd_book (outstanding net forward position at month end; - = net
    forward sales). The table's header is checked so a layout change fails loudly.
    """
    t = rows[rows["tab"].str.strip() == INTERVENTION_TAB].copy()
    head = " ".join(t[["c3", "c9"]].astype("string").fillna("").agg(" ".join, axis=1))
    if "Net Purchase" not in head or "Outstanding Net Forward" not in head:
        raise DbieError("RBI intervention table layout changed (header not found)")
    t = t[t["c1"].astype("string").str.strip().isin(MONTHS)
          & t["c2"].astype("string").str.strip().str.fullmatch(r"\d{4}").fillna(False)]
    idx = pd.to_datetime({"year": t["c2"].astype(int), "month": t["c1"].str.strip().map(MONTHS), "day": 1})
    out = pd.DataFrame({"net_purchase": _num(t["c3"]).values, "purchase": _num(t["c4"]).values,
                        "sale": _num(t["c5"]).values, "fwd_book": _num(t["c9"]).values},
                       index=pd.DatetimeIndex(idx.values, name="date")).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    # The net column agrees with the table's cumulative column; where a gross leg does not
    # add up (e.g. Mar 2014 prints sales equal to purchases), rebuild sales from the net.
    bad = (out["purchase"] - out["sale"] - out["net_purchase"]).abs() > 1
    out.loc[bad, "sale"] = out.loc[bad, "purchase"] - out.loc[bad, "net_purchase"]
    out["gross_fixed"] = bad
    return out


def fetch_intervention(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
                       session: requests.Session | None = None) -> pd.DataFrame:
    """Monthly RBI FX intervention, cached as data/raw/dbie/rbi_intervention.csv."""
    cache = cache_dir / "rbi_intervention.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")
    rows = _get_rows(base, Spec(INTERVENTION_TABLE, order="row_no"), session or requests.Session())
    out = parse_intervention(rows)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, date_format="%Y-%m-%d")
    return out
