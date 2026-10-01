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
import re
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
    # Net primary (investment and employee) income, overall-BoP presentation (to 2014; BPM6 table after).
    "bopx.primary_income": Spec("external_sector/ind_ovr_bop_rn", {"io_bop_rn": "CURR_INVIS_TRA_INC", **_BOP}, _MN, True),
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


# --------------------------------------------------------------------------- BoP (BPM6 standard presentation)

BOP_BPM6_TABLE = "external_sector/r143_standard_presentation_of_india_s_balance_of_payments_as_pe"
QUARTERS = {"Jan-Mar": 1, "Apr-Jun": 4, "Jul-Sep": 7, "Oct-Dec": 10}
# Pipeline BoP item -> (BPM6 code(s), column). Checked against RBI's overall-BoP series over
# 59 common quarters (identical up to revisions). Loans and banking capital are classified
# differently under BPM6 and are deliberately not mapped.
BPM6_MAP = {
    "current_account": (["1"], "net"),
    "merch_balance": (["1.A.a"], "net"),
    "private_transfers": (["1.C.1"], "net"),
    "capital_account": (["2", "3", "-3.5"], "net"),
    "fdi_bop": (["3.1"], "net"),
    "portfolio_bop": (["3.2"], "net"),
    "reserve_change": (["3.5"], "net"),
    "primary_income": (["1.B"], "net"),
    "goods_credit": (["1.A.a"], "credit"),
    "goods_debit": (["1.A.a"], "debit"),
    "services_credit": (["1.A.b"], "credit"),
    "services_debit": (["1.A.b"], "debit"),
}


def parse_bop_bpm6(rows: pd.DataFrame) -> pd.DataFrame:
    """RBI Bulletin BPM6 standard presentation (sheet layout) -> quarterly US$ mn at quarter start."""
    t = rows.copy()
    t["row_no"] = t["row_no"].astype(int)
    t = t.sort_values("row_no").reset_index(drop=True)
    cols = [c for c in t.columns if c[:1] == "c" and c[1:].isdigit()]
    title = " ".join(t["c1"].dropna().astype(str).head(6))
    head_i = t.index[t["c1"].astype("string").str.strip() == "Item"]
    if "Standard Presentation" not in title or not len(head_i):
        raise DbieError("BPM6 BoP table layout changed (title or header not found)")
    hdr = t.loc[head_i[0]]
    qcols = {}
    for i, c in enumerate(cols):
        m = re.match(r"(Jan-Mar|Apr-Jun|Jul-Sep|Oct-Dec)\s+(\d{4})", str(hdr[c]).strip())
        if m:
            qcols[pd.Timestamp(int(m.group(2)), QUARTERS[m.group(1)], 1)] = cols[i:i + 3]
    body = t.loc[head_i[0] + 3:]
    codes = body["c1"].astype("string").str.strip().str.split(" ", n=1).str[0]
    out = {}
    for q, (cc, cd, cn) in qcols.items():
        vals = {"credit": _num(body[cc]), "debit": _num(body[cd]), "net": _num(body[cn])}
        rec = {}
        for item, (parts, col) in BPM6_MAP.items():
            total = 0.0
            for p in parts:
                sign, code = (-1, p[1:]) if p.startswith("-") else (1, p)
                hit = vals[col][(codes == code).to_numpy()]
                if hit.empty:
                    raise DbieError(f"BPM6 BoP: item {code} not found")
                total += sign * float(hit.iloc[0])
            rec[item] = total
        out[q] = rec
    df = pd.DataFrame.from_dict(out, orient="index").sort_index()
    df.index.name = "date"
    return df


def fetch_bop_bpm6(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
                   session: requests.Session | None = None) -> pd.DataFrame:
    cache = cache_dir / "bop_bpm6.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")
    out = parse_bop_bpm6(_get_rows(base, Spec(BOP_BPM6_TABLE, order="row_no"), session or requests.Session()))
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, date_format="%Y-%m-%d")
    return out


# --------------------------------------------------------------------------- CPI 2024 = 100

CPI_TABLE = "real_sector/r45_consumer_price_index"
CPI_2024_TAB = "CPI - 2024=100 (All India)"
MON3 = {m.upper()[:3]: i for m, i in MONTHS.items()}


def parse_cpi_2024(rows: pd.DataFrame) -> pd.DataFrame:
    """RBI Bulletin CPI table, 2024 = 100 sheet -> monthly All-India General Index (combined).

    Columns: index (combined), inflation (combined, % y/y as published; blank before 2026),
    provisional (True for the latest, provisional print).
    """
    t = rows[rows["tab"].astype("string").str.strip() == CPI_2024_TAB].copy()
    if t.empty or not t.astype("string").apply(lambda c: c.str.contains("2024 = 100", na=False)).any().any():
        raise DbieError("CPI 2024=100 sheet not found or base changed")
    t = t[t["c2"].astype("string").str.strip().str.startswith("A) General Index")]
    m = t["c1"].astype("string").str.strip().str.extract(r"^([A-Z]{3})-(\d{4})$")
    t = t[m[0].notna().to_numpy()]
    m = m.dropna()
    idx = pd.to_datetime({"year": m[1].astype(int), "month": m[0].map(MON3), "day": 1})
    out = pd.DataFrame({"index": _num(t["c8"]).to_numpy(), "inflation": pd.to_numeric(
        t["c9"].astype("string").str.strip().replace("", None), errors="coerce").to_numpy(),
        "provisional": t["c3"].astype("string").str.strip().str.lower().eq("provisional").to_numpy()},
        index=pd.DatetimeIndex(idx.to_numpy(), name="date")).sort_index()
    return out[~out.index.duplicated(keep="first")]


def fetch_cpi_2024(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
                   session: requests.Session | None = None) -> pd.DataFrame:
    cache = cache_dir / "cpi_2024base.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")
    out = parse_cpi_2024(_get_rows(base, Spec(CPI_TABLE, order="row_no"), session or requests.Session()))
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, date_format="%Y-%m-%d")
    return out


# --------------------------------------------------------------------------- INR/USD from daily reference rates

DAILY_RATE = Spec("financial_markets/forex_rate_d_rn", {"currency": "USD"})


def monthly_from_daily(daily: pd.Series, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """Monthly mean of RBI's daily INR/USD reference rate; the current (unfinished) month is dropped."""
    today = pd.Timestamp.today().normalize() if today is None else today
    m = daily.resample("MS").agg(["mean", "count"])
    m = m[m["count"] > 0]
    return m[m.index < today.to_period("M").to_timestamp()]


def fetch_inr_daily(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
                    session: requests.Session | None = None) -> pd.DataFrame:
    """Monthly averages of the daily reference rate (columns mean, count), cached."""
    cache = cache_dir / "inr_usd_daily_avg.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")
    rows = _get_rows(base, DAILY_RATE, session or requests.Session())
    daily = pd.Series(pd.to_numeric(rows["obs_value"], errors="coerce").to_numpy(),
                      index=pd.to_datetime(rows["time_period"])).dropna().sort_index()
    out = monthly_from_daily(daily)
    out.index.name = "date"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, date_format="%Y-%m-%d")
    return out


# --------------------------------------------------------------------------- reserves, weekly

WEEKLY_RESERVES = Spec("external_sector/fr_exg_resv_rn", {"typ_maj_fr_exc_res_rn": "FER_TTL", "unit_measure": "USD"}, _MN)


def fetch_reserves_weekly(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
                          session: requests.Session | None = None) -> pd.Series:
    """Total FX reserves, US$ mn, weekly (Friday dates), cached."""
    cache = cache_dir / "fx_reserves_weekly.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")["value"]
    rows = _get_rows(base, WEEKLY_RESERVES, session or requests.Session())
    s = pd.Series(pd.to_numeric(rows["obs_value"], errors="coerce").to_numpy() * _MN,
                  index=pd.DatetimeIndex(pd.to_datetime(rows["time_period"]), name="date"), name="value")
    s = s.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    cache_dir.mkdir(parents=True, exist_ok=True)
    s.to_frame().to_csv(cache, date_format="%Y-%m-%d")
    return s


# --------------------------------------------------------------------------- real GDP, quarterly

GDP_TYPED = "real_sector/qtr_gdp_mrkt_prc_rn"
GDP_NEW_TABLE = "real_sector/r161_quarterly_estimates_of_gross_domestic_product_at_constant"
GDP_NEW_TAB = "NAS : 2022-23"


def parse_gdp_new_base(rows: pd.DataFrame) -> pd.Series:
    """Handbook sheet, GDP at constant prices, base 2022-23 -> quarterly series (quarter start).

    Rows are fiscal years (label in c1 on the Q1 row only) and quarters Q1-Q4 (Apr-Jun = Q1);
    GDP is the last column, headed "Gross Domestic Product"."""
    t = rows[rows["tab"].astype("string").str.strip() == GDP_NEW_TAB].copy()
    t["row_no"] = t["row_no"].astype(int)
    t = t.sort_values("row_no")
    head = t[t["c1"].astype("string").str.contains("Item", na=False)]
    if head.empty:
        raise DbieError("GDP 2022-23 sheet: header not found")
    gcol = next((c for c in head.columns if c[:1] == "c" and "Gross Domestic Product" in str(head.iloc[0][c])), None)
    if gcol is None:
        raise DbieError("GDP 2022-23 sheet: GDP column not found")
    fy = t["c1"].astype("string").str.extract(r"^(\d{4})-\d{2}")[0].ffill()
    q = t["c2"].astype("string").str.strip().str.extract(r"^Q([1-4])$")[0]
    ok = fy.notna() & q.notna()
    start_month = {"1": 4, "2": 7, "3": 10, "4": 1}
    dates = [pd.Timestamp(int(y) + (1 if qq == "4" else 0), start_month[qq], 1) for y, qq in zip(fy[ok], q[ok])]
    return pd.Series(_num(t.loc[ok, gcol]).to_numpy(), index=pd.DatetimeIndex(dates, name="date"),
                     name="gdp_real").sort_index()


def fetch_real_gdp(cache_dir: Path, refresh: bool = False, base: str = DEFAULT_BASE,
                   session: requests.Session | None = None) -> pd.Series:
    """Quarterly real GDP (not seasonally adjusted), all bases linked by growth rates onto the
    newest base; cached as data/raw/dbie/gdp_real_quarterly.csv."""
    cache = cache_dir / "gdp_real_quarterly.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"]).set_index("date")["gdp_real"]
    s = session or requests.Session()
    typed = _get_rows(base, Spec(GDP_TYPED, {"class_exp_rn": "CEXP_GDP_MARK_CST", "prc_typ_rn": "CNST_PRC"}), s)
    typed["date"] = pd.to_datetime(typed["time_period"]).dt.to_period("Q").dt.start_time
    wide = typed.assign(v=pd.to_numeric(typed["obs_value"], errors="coerce")).pivot_table(
        index="date", columns="base_per", values="v")
    series = [parse_gdp_new_base(_get_rows(base, Spec(GDP_NEW_TABLE, order="row_no"), s))]
    series += [wide[b].dropna() for b in ("BY_2011_12", "BY_2004_05", "BY_1999_2000") if b in wide]
    out = series[0]
    for older in series[1:]:
        first = out.index.min()
        overlap = older.index.intersection(out.index)
        if len(overlap):
            scale = float(out.loc[overlap[0]] / older.loc[overlap[0]])
            out = pd.concat([older[older.index < first] * scale, out]).sort_index()
    out.name = "gdp_real"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_frame().to_csv(cache, date_format="%Y-%m-%d")
    return out
