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

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import path
from . import alfred, dbie, fred, rbi, worldbank

MS = pd.offsets.MonthBegin


@dataclass
class Dataset:
    panel: pd.DataFrame
    pit: pd.DataFrame
    bop: pd.DataFrame
    gdp_inr_annual: pd.Series
    annual: dict = field(default_factory=dict)       # other World Bank annual series, by config key
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


MONTHLY_PAIRS = {  # panel column -> (key in load_rbi output, column or None)
    "inr_usd": ("inr_usd", None),
    "reer": ("reer", "reer"),
    "neer": ("reer", "neer"),
    "fx_reserves_usd_mn": ("reserves", None),
    "exports_usd_mn": ("trade", "exports_usd_mn"),
    "imports_usd_mn": ("trade", "imports_usd_mn"),
    "fdi_usd_mn": ("fi", "fdi_usd_mn"),
    "fpi_usd_mn": ("fi", "fpi_usd_mn"),
}


MERGERS = {"merge": dbie.merge, "merge_early": dbie.merge_older}


def load_rbi_sources(cfg: dict, refresh: bool, warnings: list[str], meta: dict) -> dict:
    """RBI series from the DBIE Excel files, the RBIH Data API, or both merged.

    Returns ``{"monthly": {column: Series}, "bop": DataFrame, "wacr": Series | None}``.
    """
    raw = path(cfg, "raw")
    dcfg = cfg.get("dbie", {"mode": "xlsx"})
    mode = dcfg["mode"]
    xl = load_rbi(raw)
    xl_monthly = {col: (xl[k] if c is None else xl[k][c]).rename(col) for col, (k, c) in MONTHLY_PAIRS.items()}
    if mode == "xlsx":
        meta["rbi_source"] = "DBIE Excel files only"
        return {"monthly": xl_monthly, "bop": xl["bop"], "wacr": None, "extra": {}, "intervention": None}

    api = dbie.fetch_all(path(cfg, "dbie_cache"), refresh=refresh, base=dcfg.get("base_url", dbie.DEFAULT_BASE))
    fetch_meta = path(cfg, "dbie_cache") / "_fetch.json"
    if fetch_meta.exists():
        meta["dbie_fetch"] = json.loads(fetch_meta.read_text(encoding="utf-8"))
    tol = dcfg.get("reconcile_rel_tol", 0.005)
    window = dcfg.get("revision_window", 24)
    recon, monthly = {}, {}
    for col, xs in xl_monthly.items():
        a = api[col]
        recon[col] = dbie.reconcile(a, xs, tol, window)
        monthly[col] = MERGERS[mode](a, xs).rename(col) if mode in MERGERS else a.rename(col)
    bop_cols = {}
    for name in rbi.BOP_ITEMS.values():
        a, xs = api[f"bop.{name}"], xl["bop"][name]
        recon[f"bop.{name}"] = dbie.reconcile(a, xs, tol, window)
        bop_cols[name] = MERGERS[mode](a, xs) if mode in MERGERS else a
    bop = pd.DataFrame(bop_cols).sort_index()
    bop.index.name = "date"

    for k, v in recon.items():
        if v.get("n_unexpected", 0):
            warnings.append(f"RBI sources disagree on {k} outside the recent-revision window: "
                            f"{v['n_unexpected']} of {v['overlap']} periods differ by more than {tol:.1%} "
                            f"(worst {v['worst'][:1]}). Check for a definition change or a parsing error.")
    meta["rbi_source"] = {"merge": "RBIH Data API merged with DBIE Excel (later vintage preferred)",
                          "merge_early": "RBIH Data API merged with DBIE Excel (earlier vintage preferred; revision check)",
                          "api": "RBIH Data API only"}[mode]
    meta["rbi_reconciliation"] = recon
    intervention = dbie.fetch_intervention(path(cfg, "dbie_cache"), refresh=refresh,
                                           base=dcfg.get("base_url", dbie.DEFAULT_BASE))
    return {"monthly": monthly, "bop": bop, "wacr": api.get("wacr"),
            "extra": {k: api[k] for k in dbie.EXTRA}, "intervention": intervention}


def dbie_gaps(monthly: dict[str, pd.Series], start: pd.Timestamp) -> dict[str, list[str]]:
    """Missing months inside each RBI monthly series from ``start`` (INR/USD is patched separately)."""
    return {k: g for k, s in monthly.items()
            if k != "inr_usd" and (g := dbie.monthly_gaps(s[s.index >= start]))}


def _carry(s: pd.Series, months: int) -> pd.Series:
    return s.ffill(limit=months) if months else s


def patch_inr_with_fred(inr: pd.Series, fred_inr: pd.Series, extend: bool, lookback: int = 12) -> tuple[pd.Series, dict]:
    """Fill interior gaps (and optionally extend) RBI INR/USD with FRED's monthly rate, rescaled.

    FRED's EXINUS (noon buying rates in New York) differs slightly from RBI's reference
    rate, so each patched month is scaled by the mean RBI/FRED ratio over the preceding
    ``lookback`` months where both exist.
    """
    both = pd.concat([inr, fred_inr], axis=1, keys=["rbi", "fred"]).dropna()
    rel = (both["rbi"] / both["fred"] - 1).abs()
    info = {"overlap": len(both), "mean_abs_rel_diff": float(rel.mean()) if len(rel) else None,
            "filled": [], "extended": []}
    out = inr.copy()
    targets = list(pd.date_range(inr.index.min(), inr.index.max(), freq="MS").difference(inr.dropna().index))
    if extend:
        targets += [d for d in fred_inr.index if d > inr.index.max()]
    for d in targets:
        if d not in fred_inr.index or np.isnan(fred_inr[d]):
            continue
        prior = both[both.index < d].tail(lookback)
        if prior.empty:
            continue
        out[d] = fred_inr[d] * float((prior["rbi"] / prior["fred"]).mean())
        info["extended" if d > inr.index.max() else "filled"].append(d.strftime("%Y-%m"))
    return out.sort_index().rename("inr_usd"), info


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


def official_cpi_india(extra: dict[str, pd.Series], mospi_2024: pd.Series,
                       cfg: dict) -> tuple[pd.Series, pd.Series, pd.Series, dict]:
    """Official India CPI: a linked level (base 2024 = 100), a per-month source label,
    and year-on-year inflation as published at the time.

    See [cpi_india] in the config for the segments. MOSPI's 2012 -> 2024 linking factor
    is an annual average, so the linked level steps at Jan 2025 and level-based
    inflation for 2025 differs from what MOSPI published. Models therefore use ``yoy``:
    2024-base inflation once a year of the new series exists (Jan 2026 on), 2012-base
    inflation before that (what was published during 2025), and CPI-IW inflation
    before CPI-Combined starts. The level is used only for long-run PPP diagnostics.
    """
    c = cfg["cpi_india"]
    lf = c["linking_factor_2024"]
    c12, bs = extra["cpi.combined_2012"].dropna(), extra["cpi.combined_2012_bs"].dropna()
    ov = pd.concat([c12, bs], axis=1, keys=["o", "b"]).dropna()
    bs_ratio = float((ov["o"] / ov["b"]).mean()) if len(ov) else 1.0
    old = pd.concat([bs[bs.index < c12.index.min()] * bs_ratio, c12]).sort_index()   # 2012 = 100

    # Continuous level: 2012 base x LF while it is published, then the 2024 series'
    # month-on-month changes. (MOSPI's own linked back series switches in Jan 2025 and
    # steps by about -1.2% there, because the factor is an annual average.)
    new = mospi_2024.dropna()
    new_start = new.index.min()
    old_end = old.index.max()
    linked = old * lf
    after = new[new.index > old_end]
    if len(after):
        level = linked[old_end]
        for d in after.index:
            level = level * new[d] / new[d - MS(1)]
            linked[d] = level
    linked = linked.sort_index()
    src = pd.Series(np.where(linked.index > old_end, "MOSPI 2024 (chained)",
                             np.where(linked.index >= c12.index.min(), "MOSPI 2012 x LF", "MOSPI 2012 back series x LF")),
                    index=linked.index, dtype=object)

    # Before CPI-C: chain CPI-IW month-on-month changes backwards from the first CPI-C month.
    iw = pd.concat([extra["cpi.iw_1982"].dropna() / c["cpiiw_factor_1982_2001"], extra["cpi.iw_2001"].dropna()])
    iw = iw[~iw.index.duplicated(keep="last")].sort_index()
    first = linked.index.min()
    if first not in iw.index:
        raise ValueError(f"CPI-IW must cover {first:%b %Y} to chain the pre-CPI-C history onto it")
    back, level = {}, linked[first]
    for d in reversed(iw.index[iw.index < first]):
        nxt = d + MS(1)
        if nxt not in iw.index:
            break
        level = level * iw[d] / iw[nxt]
        back[d] = level
    back = pd.Series(back).sort_index()
    out = pd.concat([back, linked]).sort_index().rename("cpi_india")
    src = pd.concat([pd.Series("CPI-IW chained", index=back.index, dtype=object), src]).sort_index()

    # Inflation as published: new base where it has a year of history, else 2012 base, else CPI-IW.
    pct = lambda s: s.pct_change(12, fill_method=None) * 100
    yoy = pct(mospi_2024.dropna()).combine_first(pct(old)).combine_first(pct(iw)).rename("cpi_india_yoy")

    # Diagnostics: how the official link behaves over the 2025 overlap.
    both = pd.concat([mospi_2024, old], axis=1, keys=["new", "old"]).dropna()
    meta = {
        "method": "official",
        "segments": {k: [v.index.min().strftime("%Y-%m"), v.index.max().strftime("%Y-%m")]
                     for k, v in src.groupby(src)},
        "linking_factor_2024": lf,
        "overlap_2025_mean_ratio": float((both["new"] / both["old"]).mean()) if len(both) else None,
        "seam_2025_mom_pct": float((out[new_start] / out[new_start - MS(1)] - 1) * 100),
        "back_series_ratio": bs_ratio,
        "cpiiw_factor_1982_2001": c["cpiiw_factor_1982_2001"],
    }
    return out, src, yoy, meta


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

    src = load_rbi_sources(cfg, refresh, warnings, meta)
    rm = src["monthly"]
    f = load_fred(cfg, refresh)

    # INR/USD: patch interior gaps (and optionally the edge) with rescaled FRED EXINUS.
    inr = rm["inr_usd"]
    if "inr_usd_fred" in f:
        inr, inr_patch = patch_inr_with_fred(inr, f["inr_usd_fred"], cfg.get("dbie", {}).get("extend_inr_with_fred", False))
        meta["inr_usd_patch"] = inr_patch
        if inr_patch["filled"] or inr_patch["extended"]:
            warnings.append(f"INR/USD uses rescaled FRED EXINUS for {', '.join(inr_patch['filled'] + inr_patch['extended'])} "
                            f"(RBI data missing; typical RBI-FRED gap {inr_patch['mean_abs_rel_diff']:.2%}).")
    for k, v in dbie_gaps(rm, pd.Timestamp(cfg["sample"]["start"])).items():
        warnings.append(f"{k} has missing months inside its range: {', '.join(v[:6])}{' …' if len(v) > 6 else ''}.")

    # Dollar index: broad index, backfilled with the ratio-rescaled major-currency index.
    dxy, dxy_ratio = fred.ratio_splice(f["dxy_broad"], f["dxy_major"],
                                       cfg["dxy_splice"]["overlap_months"])
    meta["dxy_splice_ratio"] = dxy_ratio
    seam = f["dxy_broad"].dropna().index.min()
    jump = float(np.log(dxy.loc[seam] / dxy.loc[seam - MS(1)]))
    meta["dxy_seam"] = {"month": seam.strftime("%Y-%m"), "log_change_pct": round(100 * jump, 2)}

    # India CPI.
    mospi = pd.read_csv(manual / "mospi_cpi_2024base.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]
    cpi_oecd, oecd_meta = splice_cpi_india(f["cpi_india_oecd"], mospi)
    extra = src.get("extra", {})
    if cfg.get("cpi_india", {}).get("source", "oecd") == "official" and "cpi.combined_2012" in extra:
        cpi_india, cpi_src, cpi_yoy, splice_meta = official_cpi_india(extra, mospi, cfg)
        oecd_yoy = cpi_oecd.pct_change(12, fill_method=None) * 100
        cmp = pd.concat([cpi_yoy, oecd_yoy], axis=1, keys=["official", "oecd"]).dropna()
        splice_meta["vs_oecd_yoy"] = {"overlap": [cmp.index.min().strftime("%Y-%m"), cmp.index.max().strftime("%Y-%m")],
                                      "corr": round(float(cmp.corr().iloc[0, 1]), 3),
                                      "mean_abs_diff_pp": round(float((cmp["official"] - cmp["oecd"]).abs().mean()), 2)}
    else:
        cpi_india, cpi_yoy, splice_meta = cpi_oecd, None, {"method": "oecd", **oecd_meta}
        if cfg.get("cpi_india", {}).get("source") == "official":
            warnings.append("Official India CPI needs [dbie] mode 'merge' or 'api'; using the OECD series.")
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
    wacr = src.get("wacr")
    if wacr is not None and repo is not None:
        both = pd.concat([wacr, repo], axis=1, keys=["wacr", "repo"]).dropna()
        meta["wacr_vs_repo"] = {
            "overlap": [both.index[0].strftime("%Y-%m"), both.index[-1].strftime("%Y-%m")],
            "mean_abs_gap_pp": round(float((both["wacr"] - both["repo"]).abs().mean()), 3),
            "corr": round(float(both["wacr"].corr(both["repo"])), 3),
        }
    source = cfg["rates"]["india_policy_source"]
    if source == "wacr":
        if wacr is None:
            raise ValueError("india_policy_source='wacr' needs [dbie] mode 'merge' or 'api'")
        policy = wacr.combine_first(call[call.index > wacr.index.max()])
        meta["india_policy_rate_source"] = (f"RBI weighted average call rate (DBIE) to {wacr.index.max():%Y-%m}, "
                                            "OECD call rate after")
    elif source == "repo":
        if repo is None:
            raise FileNotFoundError(f"india_policy_source='repo' but {repo_file} is missing")
        policy = repo.combine_first(call[call.index < repo.index.min()])
        meta["india_policy_rate_source"] = (f"RBI repo rate ({repo_file.name}) from {repo.index.min():%Y-%m}, "
                                            "overnight call rate before")
    else:
        policy = call
        meta["india_policy_rate_source"] = f"FRED {cfg['fred']['series']['india_stir']} (overnight call rate)"

    # Portfolio flows: legacy FII series (INR crore) before Mar 2011, BoP net portfolio after.
    legacy = pd.read_csv(raw / "parsed_fpi_inr.csv", index_col=0, parse_dates=True).iloc[:, 0]
    legacy_usd = (legacy * 10 / inr.reindex(legacy.index)).dropna()
    seam_fpi = rm["fpi_usd_mn"].dropna().index.min()
    fpi = pd.concat([legacy_usd[legacy_usd.index < seam_fpi], rm["fpi_usd_mn"]]).sort_index()
    meta["fpi_seam"] = seam_fpi.strftime("%Y-%m")

    start = pd.Timestamp(cfg["sample"]["start"])
    end = max(inr.index.max(), max(s.dropna().index.max() for s in f.values()))
    idx = pd.date_range(start, end, freq="MS")

    panel = pd.DataFrame(index=idx)
    panel.index.name = "date"
    panel["inr_usd"] = inr
    for col in ["reer", "neer", "fx_reserves_usd_mn", "exports_usd_mn", "imports_usd_mn", "fdi_usd_mn"]:
        panel[col] = rm[col]
    panel["fpi_usd_mn"] = fpi
    panel["dxy"] = dxy
    for col in ["cpi_us", "fed_funds_rate", "vix", "us_10y_yield", "brent", "fed_balance_sheet", "india_stir"]:
        panel[col] = f[col]
    panel["cpi_india"] = cpi_india
    if cpi_yoy is not None:
        panel["cpi_india_yoy"] = cpi_yoy
    panel["india_policy_rate"] = policy
    if repo is not None:
        panel["india_repo_rate"] = repo
    if wacr is not None:
        panel["india_wacr"] = wacr
    for h in ("1m", "3m", "6m"):
        if f"fwd_premium_{h}" in extra:
            panel[f"fwd_premium_{h}"] = extra[f"fwd_premium_{h}"]
    iv = src.get("intervention")
    if iv is not None:
        # RBI Bulletin Table 4. Total intervention = spot net purchases (value dates) + change in
        # the outstanding net forward book: new forward commitments count when made, maturing
        # forwards are not double counted, and the two legs of a swap cancel.
        panel["rbi_net_purchase_usd_mn"] = iv["net_purchase"]
        panel["rbi_fwd_book_usd_mn"] = iv["fwd_book"]
        panel["rbi_intervention_usd_mn"] = iv["net_purchase"] + iv["fwd_book"].diff()
        meta["rbi_intervention"] = {"source": "RBI Bulletin Table 4 via the RBIH Data API",
                                    "range": [iv.index.min().strftime("%Y-%m"), iv.index.max().strftime("%Y-%m")],
                                    "gross_legs_rebuilt": list(iv.index[iv["gross_fixed"].astype(bool)].strftime("%Y-%m"))}
    panel = panel.reindex(idx)

    # Annual GDP.
    wb = cfg["worldbank"]
    gdp_usd = worldbank.fetch_annual(wb["gdp_india_usd"][0], wb["gdp_india_usd"][1],
                                     raw / wb["gdp_india_usd"][2], refresh=refresh)
    gdp_inr = annual_gdp_inr(gdp_usd, inr)
    annual = {k: worldbank.fetch_annual(v[0], v[1], raw / v[2], refresh=refresh)
              for k, v in wb.items() if k not in ("gdp_india_usd", "remittances_usd")}
    lag = cfg["publication_lag"]
    nowcast = GdpNowcaster(gdp_inr, lag["annual_worldbank"], cfg["gdp"]["growth_lookback_years"])

    us_yoy = us_cpi_vintages(cfg, panel, refresh, meta)
    pit = build_pit(panel, lag, nowcast, cfg.get("pit", {}).get("carry_forward_months", 0), us_yoy)
    bop = build_bop(src["bop"], panel, lag["bop_quarterly"], nowcast, src.get("extra", {}))
    last_q = src["bop"]["current_account"].last_valid_index()
    due = last_q + MS(3 + lag["bop_quarterly"])
    if due <= pit.index[-1]:
        warnings.append(f"Latest BoP quarter is {last_q:%b %Y} (quarter start); the next one was due by {due:%b %Y}. "
                        "Download a fresh BoP file from DBIE or wait for the RBIH API to update.")

    ends = {c: panel[c].last_valid_index().strftime("%Y-%m") for c in panel.columns
            if panel[c].last_valid_index() is not None}
    meta["series_end"] = ends
    meta["asof"] = pit["inr_usd"].last_valid_index().strftime("%Y-%m")
    return Dataset(panel=panel, pit=pit, bop=bop, gdp_inr_annual=gdp_inr, annual=annual,
                   warnings=warnings, meta=meta)


CARRY_FORWARD = ["reer", "neer", "fx_reserves_usd_mn", "exports_usd_mn", "imports_usd_mn"]


def us_cpi_vintages(cfg: dict, panel: pd.DataFrame, refresh: bool, meta: dict) -> pd.Series | None:
    """US CPI inflation as published at each month-end, from ALFRED (None without a key or cache)."""
    if not cfg.get("alfred", {}).get("enabled", False):
        return None
    rel = alfred.fetch_releases(cfg["fred"]["series"]["cpi_us"], path(cfg, "raw") / "alfred",
                                os.environ.get("FRED_API_KEY") or None, refresh=refresh)
    if rel is None:
        meta["cpi_us_vintage"] = "revised series with a fixed lag (ALFRED needs FRED_API_KEY; see data/alfred.py)"
        return None
    rt = alfred.yoy_as_known(rel, panel.index)
    revised = (panel["cpi_us"].pct_change(12, fill_method=None) * 100).shift(cfg["publication_lag"]["cpi_us"])
    both = pd.concat([rt, revised], axis=1, keys=["rt", "rev"]).dropna()
    meta["cpi_us_vintage"] = {
        "source": "ALFRED real-time vintages", "from": rt.first_valid_index().strftime("%Y-%m"),
        "mean_abs_diff_pp": round(float((both["rt"] - both["rev"]).abs().mean()), 3),
        "max_abs_diff_pp": round(float((both["rt"] - both["rev"]).abs().max()), 3)}
    return rt


def build_pit(panel: pd.DataFrame, lag: dict, nowcast: GdpNowcaster, carry: int = 0,
              us_yoy: pd.Series | None = None) -> pd.DataFrame:
    """Information set at the end of each month.

    Slow-moving levels in CARRY_FORWARD keep their latest published value for up to
    ``carry`` months when a release is late, so the ragged edge does not blank the models.
    """
    last = panel["inr_usd"].last_valid_index()
    idx = panel.index[panel.index <= last]
    pit = pd.DataFrame(index=idx)
    pit.index.name = "date"

    def lagged(col, key=None):
        return panel[col].shift(lag[key or col]).reindex(idx)

    pit["inr_usd"] = lagged("inr_usd")
    pit["reer"] = _carry(lagged("reer"), carry)
    pit["neer"] = _carry(lagged("neer"), carry)
    pit["fx_reserves_usd_mn"] = _carry(lagged("fx_reserves_usd_mn"), carry)
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
    if us_yoy is not None:
        # US inflation as published at each month-end (ALFRED vintages), where available.
        pit["cpi_us_yoy"] = us_yoy.reindex(idx).combine_first(pit["cpi_us_yoy"])
    # India: inflation as published when available (official CPI), else from the level.
    india_yoy = (panel["cpi_india_yoy"] if "cpi_india_yoy" in panel
                 else panel["cpi_india"].pct_change(12, fill_method=None) * 100)
    pit["cpi_india_yoy"] = india_yoy.shift(lag["cpi_india"]).reindex(idx).ffill(limit=2)
    pit["exports_usd_mn"] = _carry(lagged("exports_usd_mn"), carry)
    pit["imports_usd_mn"] = _carry(lagged("imports_usd_mn"), carry)
    pit["fpi_usd_mn"] = lagged("fpi_usd_mn")
    for col in ["rbi_net_purchase_usd_mn", "rbi_fwd_book_usd_mn", "rbi_intervention_usd_mn"]:
        if col in panel:
            pit[col] = lagged(col, "rbi_intervention")

    for h in ("1m", "3m", "6m"):
        if f"fwd_premium_{h}" in panel:
            # Market data, public as traded; the occasional missing month is bridged by the last value.
            pit[f"fwd_premium_{h}"] = _carry(lagged(f"fwd_premium_{h}", "fwd_premium"), 2)
    pit["inflation_diff"] = pit["cpi_india_yoy"] - pit["cpi_us_yoy"]
    pit["real_rate_diff"] = (pit["india_policy_rate"] - pit["cpi_india_yoy"]) - \
                            (pit["fed_funds_rate"] - pit["cpi_us_yoy"])
    if "fwd_premium_3m" in pit:
        # Forward premium over the policy-rate gap: hedging demand and expected depreciation beyond carry.
        pit["fwd_spread"] = pit["fwd_premium_3m"] - (pit["india_policy_rate"] - pit["fed_funds_rate"])
        pit["real_fwd_diff"] = pit["fwd_premium_3m"] - pit["inflation_diff"]
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


def build_bop(bop: pd.DataFrame, panel: pd.DataFrame, lag: int, nowcast: GdpNowcaster,
              extra: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    """Quarterly BoP with the month-end at which each quarter became public.

    ``extra`` (API-only series) adds gross goods/services flows, the net IIP and
    monthly oil trade, which the FEER uses for trade shares, the NIIP-stabilising
    norm and the oil adjustment. All are published no later than the BoP itself.
    """
    extra = extra or {}
    q_extra = {k.split(".", 1)[1]: v for k, v in extra.items() if k.startswith("bopx.")}
    oil_net = None
    if "oil_imports_usd_mn" in extra and "oil_exports_usd_mn" in extra:
        oil_net = (extra["oil_imports_usd_mn"] - extra["oil_exports_usd_mn"]).dropna()
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
        for k, s in q_extra.items():
            row[k] = s.get(q, np.nan)
        if oil_net is not None:
            vals = oil_net.reindex(months)
            row["net_oil_imports"] = vals.sum() if vals.notna().all() else np.nan
        rows.append(row)
    out = pd.DataFrame(rows).set_index("quarter").sort_index()
    out.index.name = "quarter"
    return out
