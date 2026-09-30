"""Assemble the monthly dataset and its point-in-time (PIT) view.

Two views of the data:

* ``panel`` – values indexed by the month they *refer to* (unlagged).
* ``pit``   – values indexed by the month-end at which they were *public*.
  Every model and every backtest reads only ``pit`` (and ``bop``, which carries
  an explicit ``available`` date), so a result at month t never uses
  information published after t.

Revisions are not modelled (no vintage data); publication delays are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import path
from . import fred, rbi, worldbank

MS = pd.offsets.MonthBegin


@dataclass
class Dataset:
    panel: pd.DataFrame
    pit: pd.DataFrame
    bop: pd.DataFrame
    gdp_inr_annual: pd.Series
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def asof(self) -> pd.Timestamp:
        return self.pit["inr_usd"].last_valid_index()


# --------------------------------------------------------------------------- sources

def load_rbi(raw: Path) -> dict:
    return {
        "inr_usd": rbi.parse_inr_usd(raw / "rbi_inr_usd.xlsx"),
        "reer": rbi.parse_reer(raw / "rbi_reer.xlsx"),
        "reserves": rbi.parse_reserves(raw / "rbi_reserves.xlsx"),
        "trade": rbi.parse_trade(raw / "rbi_trade.xlsx"),
        "bop": rbi.parse_bop_quarterly(raw / "rbi_cab.xlsx"),
        "fi": rbi.parse_foreign_investment_monthly(raw / "rbi_fpi_flows.xlsx"),
    }


def load_fred(cfg: dict, refresh: bool) -> dict[str, pd.Series]:
    cache = path(cfg, "fred_cache")
    agg = cfg["fred"].get("monthly_agg", {})
    out = {}
    for col, sid in cfg["fred"]["series"].items():
        s = fred.fetch_series(sid, cache, refresh=refresh)
        out[col] = fred.to_monthly(s, agg.get(col, "mean")).rename(col)
    return out


def splice_cpi_india(oecd: pd.Series, mospi: pd.Series) -> tuple[pd.Series, dict]:
    """Ratio-splice the MOSPI 2024-base CPI onto the OECD series over their overlap."""
    both = pd.concat([oecd, mospi], axis=1, keys=["o", "m"]).dropna()
    if both.empty:
        raise ValueError("CPI splice: OECD and MOSPI series do not overlap")
    ratios = both["o"] / both["m"]
    ratio = float(ratios.mean())
    end = oecd.dropna().index.max()
    ext = mospi[mospi.index > end] * ratio
    spliced = pd.concat([oecd[oecd.index <= end], ext]).sort_index().rename("cpi_india")
    return spliced, {"ratio": ratio, "ratio_std": float(ratios.std(ddof=0)),
                     "overlap": [d.strftime("%Y-%m") for d in both.index], "oecd_end": end.strftime("%Y-%m")}


def flat_runs(s: pd.Series, min_len: int = 3) -> list[tuple[str, str, float]]:
    """Runs of >= min_len identical consecutive values (a sign of placeholder data)."""
    s = s.dropna()
    grp = (s != s.shift()).cumsum()
    runs = []
    for _, g in s.groupby(grp):
        if len(g) >= min_len:
            runs.append((g.index[0].strftime("%Y-%m"), g.index[-1].strftime("%Y-%m"), float(g.iloc[0])))
    return runs


# --------------------------------------------------------------------------- GDP (PIT)

def annual_gdp_inr(gdp_usd: pd.Series, inr_usd: pd.Series) -> pd.Series:
    """Nominal INR GDP by calendar year = USD GDP x average INR/USD of that year."""
    fx = inr_usd.groupby(inr_usd.index.year).agg(["mean", "count"])
    fx = fx.loc[fx["count"] >= 6, "mean"]
    return (gdp_usd * fx).dropna()


class GdpNowcaster:
    """Nominal GDP (US$ mn, annual rate) for a target month using only years public at ``info``."""

    def __init__(self, gdp_inr: pd.Series, release_lag_months: int, lookback: int):
        self.gdp = gdp_inr.sort_index()
        self.lag = release_lag_months
        self.lookback = lookback

    def available_years(self, info: pd.Timestamp) -> pd.Series:
        release = pd.to_datetime([f"{y}-12-01" for y in self.gdp.index]) + MS(self.lag)
        return self.gdp[release <= info]

    def inr(self, target: pd.Timestamp, info: pd.Timestamp) -> float:
        avail = self.available_years(info)
        if len(avail) < 2:
            return np.nan
        k = min(self.lookback, len(avail) - 1)
        growth = (avail.iloc[-1] / avail.iloc[-1 - k]) ** (1 / k)
        last_year = avail.index[-1]
        months = (target.year - last_year) * 12 + (target.month - 7)   # annual flow centred mid-year
        return float(avail.iloc[-1] * growth ** (months / 12))

    def usd_mn(self, target: pd.Timestamp, info: pd.Timestamp, fx: float) -> float:
        return self.inr(target, info) / fx / 1e6 if fx and not np.isnan(fx) else np.nan


# --------------------------------------------------------------------------- build

def build_dataset(cfg: dict, refresh: bool = False) -> Dataset:
    raw = path(cfg, "raw")
    manual = path(cfg, "manual")
    warnings: list[str] = []
    meta: dict = {}

    r = load_rbi(raw)
    f = load_fred(cfg, refresh)

    # Dollar index: broad index, backfilled with the ratio-rescaled major-currency index.
    dxy, dxy_ratio = fred.ratio_splice(f["dxy_broad"], f["dxy_major"],
                                       cfg["dxy_splice"]["overlap_months"])
    meta["dxy_splice_ratio"] = dxy_ratio
    seam = f["dxy_broad"].dropna().index.min()
    jump = float(np.log(dxy.loc[seam] / dxy.loc[seam - MS(1)]))
    meta["dxy_seam"] = {"month": seam.strftime("%Y-%m"), "log_change_pct": round(100 * jump, 2)}

    # India CPI.
    mospi = pd.read_csv(manual / "mospi_cpi_2024base.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]
    cpi_india, splice_meta = splice_cpi_india(f["cpi_india_oecd"], mospi)
    meta["cpi_india_splice"] = splice_meta
    verified = set(cfg.get("data_checks", {}).get("verified_flat_runs", []))
    for a, b, v in flat_runs(mospi):
        if f"mospi_cpi:{a}:{b}" not in verified:
            warnings.append(f"MOSPI CPI is flat at {v} from {a} to {b}: verify against MOSPI releases, "
                            "then list it under [data_checks] verified_flat_runs.")

    # India policy rate: call rate by default; RBI repo rate if configured.
    call = f["india_stir"]
    repo_file = manual / cfg["rates"]["repo_file"]
    repo = None
    if repo_file.exists():
        repo = pd.read_csv(repo_file, parse_dates=["date"]).set_index("date")["repo_rate"]
        both = pd.concat([call, repo], axis=1, keys=["call", "repo"]).dropna()
        meta["call_vs_repo"] = {
            "overlap": [both.index[0].strftime("%Y-%m"), both.index[-1].strftime("%Y-%m")],
            "mean_call_minus_repo_pp": round(float((both["call"] - both["repo"]).mean()), 3),
            "mean_abs_gap_pp": round(float((both["call"] - both["repo"]).abs().mean()), 3),
            "corr": round(float(both["call"].corr(both["repo"])), 3),
        }
    source = cfg["rates"]["india_policy_source"]
    if source == "repo":
        if repo is None:
            raise FileNotFoundError(f"india_policy_source='repo' but {repo_file} is missing")
        policy = repo.combine_first(call[call.index < repo.index.min()])
        meta["india_policy_rate_source"] = (f"RBI repo rate ({repo_file.name}) from {repo.index.min():%Y-%m}, "
                                            "overnight call rate before")
    else:
        policy = call
        meta["india_policy_rate_source"] = f"FRED {cfg['fred']['series']['india_stir']} (overnight call rate)"

    # Portfolio flows: legacy FII series (INR crore) before Mar 2011, BoP net portfolio after.
    inr = r["inr_usd"]
    legacy = pd.read_csv(raw / "parsed_fpi_inr.csv", index_col=0, parse_dates=True).iloc[:, 0]
    legacy_usd = (legacy * 10 / inr.reindex(legacy.index)).dropna()
    fi = r["fi"]
    seam_fpi = fi["fpi_usd_mn"].dropna().index.min()
    fpi = pd.concat([legacy_usd[legacy_usd.index < seam_fpi], fi["fpi_usd_mn"]]).sort_index()
    meta["fpi_seam"] = seam_fpi.strftime("%Y-%m")

    start = pd.Timestamp(cfg["sample"]["start"])
    end = max(inr.index.max(), max(s.dropna().index.max() for s in f.values()))
    idx = pd.date_range(start, end, freq="MS")

    panel = pd.DataFrame(index=idx)
    panel.index.name = "date"
    panel["inr_usd"] = inr
    panel["reer"] = r["reer"]["reer"]
    panel["neer"] = r["reer"]["neer"]
    panel["fx_reserves_usd_mn"] = r["reserves"]
    panel["exports_usd_mn"] = r["trade"]["exports_usd_mn"]
    panel["imports_usd_mn"] = r["trade"]["imports_usd_mn"]
    panel["fpi_usd_mn"] = fpi
    panel["fdi_usd_mn"] = fi["fdi_usd_mn"]
    panel["dxy"] = dxy
    for col in ["cpi_us", "fed_funds_rate", "vix", "us_10y_yield", "brent", "fed_balance_sheet", "india_stir"]:
        panel[col] = f[col]
    panel["cpi_india"] = cpi_india
    panel["india_policy_rate"] = policy
    if repo is not None:
        panel["india_repo_rate"] = repo
    panel = panel.reindex(idx)

    # Annual GDP.
    wb = cfg["worldbank"]
    gdp_usd = worldbank.fetch_annual(wb["gdp_india_usd"][0], wb["gdp_india_usd"][1],
                                     raw / wb["gdp_india_usd"][2], refresh=refresh)
    gdp_inr = annual_gdp_inr(gdp_usd, inr)
    lag = cfg["publication_lag"]
    nowcast = GdpNowcaster(gdp_inr, lag["annual_worldbank"], cfg["gdp"]["growth_lookback_years"])

    pit = build_pit(panel, lag, nowcast)
    bop = build_bop(r["bop"], panel, lag["bop_quarterly"], nowcast)

    ends = {c: panel[c].last_valid_index().strftime("%Y-%m") for c in panel.columns
            if panel[c].last_valid_index() is not None}
    meta["series_end"] = ends
    meta["asof"] = pit["inr_usd"].last_valid_index().strftime("%Y-%m")
    return Dataset(panel=panel, pit=pit, bop=bop, gdp_inr_annual=gdp_inr, warnings=warnings, meta=meta)


def build_pit(panel: pd.DataFrame, lag: dict, nowcast: GdpNowcaster) -> pd.DataFrame:
    """Information set at the end of each month."""
    last = panel["inr_usd"].last_valid_index()
    idx = panel.index[panel.index <= last]
    pit = pd.DataFrame(index=idx)
    pit.index.name = "date"

    def lagged(col, key=None):
        return panel[col].shift(lag[key or col]).reindex(idx)

    pit["inr_usd"] = lagged("inr_usd")
    pit["reer"] = lagged("reer")
    pit["neer"] = lagged("neer")
    pit["fx_reserves_usd_mn"] = lagged("fx_reserves_usd_mn")
    pit["dxy"] = lagged("dxy")
    pit["vix"] = lagged("vix")
    pit["brent"] = lagged("brent")
    pit["us_10y_yield"] = lagged("us_10y_yield")
    pit["fed_balance_sheet"] = lagged("fed_balance_sheet")
    # Rates and CPI: carry the latest print forward up to 2 months when a release is
    # missing (e.g. the Oct 2025 US CPI that was never published).
    pit["fed_funds_rate"] = lagged("fed_funds_rate").ffill(limit=2)
    pit["india_policy_rate"] = lagged("india_policy_rate").ffill(limit=2)
    pit["cpi_us_yoy"] = (panel["cpi_us"].pct_change(12, fill_method=None) * 100) \
        .shift(lag["cpi_us"]).reindex(idx).ffill(limit=2)
    pit["cpi_india_yoy"] = (panel["cpi_india"].pct_change(12, fill_method=None) * 100) \
        .shift(lag["cpi_india"]).reindex(idx).ffill(limit=2)
    pit["exports_usd_mn"] = lagged("exports_usd_mn")
    pit["imports_usd_mn"] = lagged("imports_usd_mn")
    pit["fpi_usd_mn"] = lagged("fpi_usd_mn")

    pit["inflation_diff"] = pit["cpi_india_yoy"] - pit["cpi_us_yoy"]
    pit["real_rate_diff"] = (pit["india_policy_rate"] - pit["cpi_india_yoy"]) - \
                            (pit["fed_funds_rate"] - pit["cpi_us_yoy"])
    pit["log_inr"] = np.log(pit["inr_usd"])
    pit["log_dxy"] = np.log(pit["dxy"])
    pit["log_brent"] = np.log(pit["brent"])
    pit["import_cover"] = pit["fx_reserves_usd_mn"] / pit["imports_usd_mn"]

    fpi_lag = lag["fpi_usd_mn"]
    gdp = []
    for t in idx:
        ref = t - MS(fpi_lag)
        fx = panel["inr_usd"].get(ref, np.nan)
        gdp.append(nowcast.usd_mn(ref, t, fx))
    pit["gdp_usd_mn_for_fpi"] = gdp
    pit["fpi_pct_gdp"] = pit["fpi_usd_mn"] * 12 / pit["gdp_usd_mn_for_fpi"] * 100
    return pit


def build_bop(bop: pd.DataFrame, panel: pd.DataFrame, lag: int, nowcast: GdpNowcaster) -> pd.DataFrame:
    """Quarterly BoP with the month-end at which each quarter became public."""
    rows = []
    for q, rec in bop.iterrows():
        months = pd.date_range(q, periods=3, freq="MS")
        available = q + MS(lag)
        inr_q = panel["inr_usd"].reindex(months).mean()
        gdp = nowcast.usd_mn(q + MS(1), available, inr_q)
        row = {"quarter": q, "available": available, **rec.to_dict(),
               "inr_q": inr_q,
               "brent_q": panel["brent"].reindex(months).mean(),
               "reer_q": panel["reer"].reindex(months).mean(),
               "gdp_usd_mn": gdp}
        for c in ["current_account", "fdi_bop", "loans", "portfolio_bop", "capital_account"]:
            row[f"{c}_pct_gdp"] = rec[c] * 4 / gdp * 100 if gdp else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("quarter").sort_index()
