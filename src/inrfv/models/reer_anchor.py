"""Fundamentals-based REER anchor (behavioural equilibrium for the real exchange rate).

Long-run relation, quarterly:

    log REER = c + b1 * relative productivity + b2 * log terms of trade + b3 * NFA/GDP

* Relative productivity: log(India / world real GDP per capita, PPP), World Bank.
  Balassa-Samuelson: faster productivity growth -> real appreciation (b1 > 0).
* Terms of trade: World Bank net barter ToT index (b2 > 0).
* NFA/GDP: net international investment position / GDP. RBI BPM6 series from 2018,
  BPM5 series before (they agree over 2018-21), back-cast before 2006 by cumulating the
  current account (Lane & Milesi-Ferretti) (b3 > 0: creditors sustain stronger currencies).

Estimated by dynamic OLS (Stock & Watson 1993: levels plus leads and lags of the
differenced regressors) with Newey-West errors, re-estimated each quarter on data public
at that date. Annual series enter only through years already published (placed at
mid-year, linearly interpolated, held flat after the last published year).

At month t the equilibrium is exp(b' X_t) with X_t the latest-known fundamentals, and
gap = log REER* - log REER (positive = REER below equilibrium = INR undervalued).
The band comes from drawing b from its estimated (HAC) distribution.

With 20-odd years of mostly annual fundamentals the effective sample is small: read the
coefficient stability and cointegration diagnostics in the report before the point estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from ..stats.cointegration import engle_granger

MS = pd.offsets.MonthBegin
REGRESSORS = ["rel_prod", "log_tot", "nfa_gdp"]


# --------------------------------------------------------------------------- inputs

def annual_to_quarters(annual: pd.Series, quarters: pd.DatetimeIndex, info: pd.Timestamp,
                       release_lag: int) -> pd.Series:
    """Quarterly path of an annual series using only years published by ``info``.

    Year Y is placed at the quarter starting in July Y; values are linearly interpolated
    between published years and held flat after the last one. Nothing before the first.
    """
    published = annual[[pd.Timestamp(f"{y}-12-01") + MS(release_lag) <= info for y in annual.index]]
    if published.empty:
        return pd.Series(np.nan, index=quarters)
    pts = pd.Series(published.to_numpy(), index=pd.to_datetime([f"{y}-07-01" for y in published.index]))
    grid = pts.index.union(quarters)
    s = pts.reindex(grid).interpolate(method="time", limit_area="inside")
    s = s.ffill().where(grid >= pts.index.min())
    return s.reindex(quarters)


def nfa_quarterly(bop: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """NIIP (US$ mn, quarter-end stock) and its source label per quarter."""
    niip = bop.get("niip", pd.Series(dtype=float)).copy()
    old = bop.get("niip_bpm5", pd.Series(dtype=float))
    src = pd.Series(np.where(niip.notna(), "BPM6", "not yet published"), index=bop.index, dtype=object)
    fill = niip.isna() & old.reindex(bop.index).notna()
    niip = niip.reindex(bop.index)
    niip[fill] = old.reindex(bop.index)[fill]
    src[fill] = "BPM5"
    first = niip.first_valid_index()
    inside = niip.index >= first if first is not None else np.zeros(len(niip), bool)
    gaps = niip.isna() & inside
    niip = niip.where(~gaps, niip.interpolate(limit_area="inside"))
    src[gaps & niip.notna()] = "interpolated"
    # Back-cast: stock at the end of the previous quarter = this stock - this quarter's CA.
    if first is not None:
        ca = bop["current_account"]
        for q in reversed(niip.index[niip.index < first]):
            nxt = q + MS(3)
            if pd.notna(niip.get(nxt)) and pd.notna(ca.get(nxt)):
                niip[q] = niip[nxt] - ca[nxt]
                src[q] = "cumulated CA"
    return niip, src


def build_quarterly(ds, cfg: dict, info: pd.Timestamp) -> pd.DataFrame:
    """Quarterly estimation dataset as it could be assembled at month-end ``info``."""
    p = cfg["models"]["reer_anchor"]
    lag = cfg["publication_lag"]
    reer_m = ds.panel["reer"].dropna()
    quarters = pd.date_range(reer_m.index.min(), info, freq="QS-JAN")
    q = pd.DataFrame(index=quarters)
    q.index.name = "quarter"

    # REER: quarterly average of months published by info.
    months_pub = reer_m[reer_m.index + MS(lag["reer"]) <= info]
    rq = months_pub.groupby(months_pub.index.to_period("Q")).agg(["mean", "count"])
    rq.index = rq.index.to_timestamp()
    q["log_reer"] = np.log(rq.loc[rq["count"] == 3, "mean"]).reindex(quarters)

    a = ds.annual
    wl = p["worldbank_release_lag"]
    prod = (annual_to_quarters(a["gdp_pc_ppp_india"], quarters, info, wl)
            / annual_to_quarters(a["gdp_pc_ppp_world"], quarters, info, wl))
    q["rel_prod"] = np.log(prod)
    q["log_tot"] = np.log(annual_to_quarters(a["tot_india"], quarters, info, p["tot_release_lag"]))

    niip, _ = nfa_quarterly(ds.bop)
    known = ds.bop["available"] <= info
    ratio = (niip / ds.bop["gdp_usd_mn"])[known]
    q["nfa_gdp"] = ratio.reindex(quarters).ffill()
    return q


# --------------------------------------------------------------------------- estimation

def dols(q: pd.DataFrame, k: int, hac_lags: int):
    """Dynamic OLS with k leads and lags of the differenced regressors."""
    X = q[REGRESSORS].copy()
    for c in REGRESSORS:
        d = q[c].diff()
        for j in range(-k, k + 1):
            X[f"d_{c}_{j:+d}"] = d.shift(-j)
    df = pd.concat([q["log_reer"], X], axis=1).dropna()
    res = sm.OLS(df["log_reer"], sm.add_constant(df.drop(columns="log_reer"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    cols = ["const"] + REGRESSORS
    return res.params[cols], res.cov_params().loc[cols, cols], res


def latest_fundamentals(q: pd.DataFrame) -> pd.Series:
    return q[REGRESSORS].ffill().iloc[-1]


def run(ds, cfg: dict) -> tuple[pd.DataFrame, dict]:
    p = cfg["models"]["reer_anchor"]
    pit = ds.pit
    rng = np.random.default_rng(p["seed"])
    out = pd.DataFrame(index=pit.index, columns=["reer", "reer_star", "gap_log", "gap_log_lo", "gap_log_hi"],
                       dtype=float)
    out["reer"] = pit["reer"]
    coefs = []
    fit = None
    lo_p, hi_p = min(p["band_percentiles"]), max(p["band_percentiles"])
    for t in pit.index:
        if pd.isna(pit.loc[t, "reer"]):
            continue
        q = build_quarterly(ds, cfg, t)
        if fit is None or t.month in (1, 4, 7, 10):          # re-estimate once per quarter
            n = len(q.dropna())
            if n >= p["min_quarters"]:
                b, V, _ = dols(q, p["dols_k"], p["hac_lags"])
                fit = (b, V)
                coefs.append({"date": t, **b.to_dict(), "nobs": n})
        if fit is None:
            continue
        b, V = fit
        x = np.r_[1.0, latest_fundamentals(q)]
        if np.isnan(x).any():
            continue
        star = float(x @ b.to_numpy())
        Vs = (V.to_numpy() + V.to_numpy().T) / 2
        draws = rng.multivariate_normal(b.to_numpy(), Vs, p["band_draws"], check_valid="ignore") @ x
        lr = np.log(pit.loc[t, "reer"])
        out.loc[t, ["reer_star", "gap_log", "gap_log_lo", "gap_log_hi"]] = [
            np.exp(star), star - lr, np.percentile(draws, lo_p) - lr, np.percentile(draws, hi_p) - lr]
    out["misalignment_pct"] = (np.exp(out["gap_log"]) - 1) * 100
    out["fair_inr"] = pit["inr_usd"] * np.exp(-out["gap_log"])

    diag = diagnostics(ds, cfg, pit.index[-1], pd.DataFrame(coefs))
    return out, diag


def diagnostics(ds, cfg: dict, info: pd.Timestamp, coefs: pd.DataFrame) -> dict:
    p = cfg["models"]["reer_anchor"]
    q = build_quarterly(ds, cfg, info)
    b, V, res = dols(q, p["dols_k"], p["hac_lags"])
    est = q.dropna()
    se = np.sqrt(np.diag(V))
    _, nfa_src = nfa_quarterly(ds.bop)
    d = {
        "sample": [est.index[0].strftime("%Y-%m"), est.index[-1].strftime("%Y-%m")],
        "nobs": int(res.nobs),
        "coef": {k: float(v) for k, v in b.items()},
        "t_hac": {k: float(v) for k, v in zip(b.index, b.to_numpy() / se)},
        "expected_sign": {"rel_prod": "+", "log_tot": "+", "nfa_gdp": "+"},
        "engle_granger": engle_granger(est["log_reer"], est[REGRESSORS]),
        "nfa_sources": nfa_src.reindex(est.index).value_counts().to_dict(),
    }
    if len(coefs):
        d["coef_path"] = {c: [float(coefs[c].min()), float(coefs[c].max())] for c in REGRESSORS}
        d["first_estimate"] = coefs["date"].min().strftime("%Y-%m")
    return d
