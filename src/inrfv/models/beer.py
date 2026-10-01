"""BEER: behavioural equilibrium for the bilateral INR/USD rate (Clark & MacDonald 1998).

Long-run relation for the real INR/USD rate, with PPP imposed:

    q_t = log INR/USD_t - (log CPI India_t - log CPI US_t)
    q_t = c + b' X_t + e_t

X (config): log broad dollar index (b > 0: a stronger dollar weakens the rupee),
relative productivity log(India / US real GDP per capita, PPP) (b < 0: Balassa-Samuelson
real appreciation), real interest differential (b < 0), optionally log Brent.
Short-lived drivers (VIX, portfolio flows) are deliberately left out of the long run.

Estimated by dynamic OLS (levels plus leads and lags of the differenced regressors)
with Newey-West errors, on an expanding window of data public at each month.

* Current BEER: INR/USD* = exp(c + b' X_t + relative price level_t).
* Total BEER:   the same with each fundamental at its permanent level, a one-sided
  HP trend (the Clark-MacDonald "total misalignment").
* Band: coefficient uncertainty (HAC covariance) around the current BEER.

The legacy version regressed log INR/USD on levels of DXY, the real rate gap, FPI/GDP,
Brent and VIX by OLS and read full-sample fitted values as fair value.

On 2001-2026 data none of the tested specifications is cointegrated (see report), so
the BEER gap is a description of where fundamentals would put the rupee, not an
equilibrium the rate reverts to. The report's out-of-sample test says whether the gap
has any predictive value anyway.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .. import backtest
from ..stats.cointegration import engle_granger, johansen_rank
from .reer_anchor import annual_to_quarters
from .structural import one_sided_hp

EXPECTED_SIGN = {"log_dxy": "+", "rel_prod": "-", "real_rate_diff": "-", "log_brent": "+", "real_fwd_diff": "-"}


def build_inputs(ds, cfg: dict) -> pd.DataFrame:
    """Monthly BEER inputs as public at each month-end (values for month t known at t)."""
    pit, panel, lag = ds.pit, ds.panel, cfg["publication_lag"]
    p = cfg["models"]["beer"]
    d = pd.DataFrame(index=pit.index)
    d["log_inr"] = pit["log_inr"]
    lp_in = np.log(panel["cpi_india"]).shift(lag["cpi_india"]).reindex(pit.index)
    lp_us = np.log(panel["cpi_us"]).shift(lag["cpi_us"]).reindex(pit.index)
    d["rel_price"] = (lp_in - lp_us).ffill(limit=2)
    d["q"] = d["log_inr"] - d["rel_price"]
    d["log_dxy"] = pit["log_dxy"]
    d["log_brent"] = pit["log_brent"]
    d["real_rate_diff"] = pit["real_rate_diff"]
    if "real_fwd_diff" in pit:
        d["real_fwd_diff"] = pit["real_fwd_diff"]
    a = ds.annual
    if {"gdp_pc_ppp_india", "gdp_pc_ppp_usa"} <= set(a):
        # Annual inputs follow each month's information set; the value at t uses years public at t.
        vals = []
        for t in pit.index:
            ind = annual_to_quarters(a["gdp_pc_ppp_india"], pd.DatetimeIndex([t]), t, p["worldbank_release_lag"])
            usa = annual_to_quarters(a["gdp_pc_ppp_usa"], pd.DatetimeIndex([t]), t, p["worldbank_release_lag"])
            vals.append(float(np.log(ind.iloc[0] / usa.iloc[0])))
        d["rel_prod"] = vals
    return d


def dols(d: pd.DataFrame, regs: list[str], k: int, hac_lags: int):
    X = d[regs].copy()
    for c in regs:
        dc = d[c].diff()
        for j in range(-k, k + 1):
            X[f"d_{c}_{j:+d}"] = dc.shift(-j)
    df = pd.concat([d["q"], X], axis=1).dropna()
    res = sm.OLS(df["q"], sm.add_constant(df.drop(columns="q"), has_constant="add")).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    cols = ["const"] + regs
    return res.params[cols], res.cov_params().loc[cols, cols], res


def run(ds, cfg: dict) -> tuple[pd.DataFrame, dict]:
    p = cfg["models"]["beer"]
    regs = p["specs"][p["central_spec"]]
    d = build_inputs(ds, cfg)
    rng = np.random.default_rng(p["seed"])
    lo_p, hi_p = min(p["band_percentiles"]), max(p["band_percentiles"])

    # Permanent components: one-sided HP of each fundamental (value at t uses data to t).
    perm = pd.DataFrame({c: one_sided_hp(d[c], p["hp_lambda"], p["min_obs"]) for c in regs}, index=d.index)

    out = pd.DataFrame(index=d.index, dtype=float,
                       columns=["fair_inr", "fair_inr_total", "gap_log", "gap_log_total", "gap_log_lo", "gap_log_hi"])
    coefs, fit = [], None
    usable = d[["q"] + regs].dropna()
    for i, t in enumerate(d.index):
        hist = d.loc[:t]
        n = len(hist[["q"] + regs].dropna())
        if n < p["min_obs"] or t not in usable.index:
            continue
        if fit is None or (i % p["refit_every"] == 0):
            b, V, _ = dols(hist, regs, p["dols_k"], p["hac_lags"])
            fit = (b, V)
            coefs.append({"date": t.strftime("%Y-%m"), **b.to_dict()})
        b, V = fit
        x = np.r_[1.0, d.loc[t, regs].to_numpy(dtype=float)]
        xp = np.r_[1.0, perm.loc[t, regs].to_numpy(dtype=float)]
        star = float(x @ b.to_numpy()) + d.loc[t, "rel_price"]
        draws = rng.multivariate_normal(b.to_numpy(), (V.to_numpy() + V.to_numpy().T) / 2, p["band_draws"],
                                        check_valid="ignore") @ x + d.loc[t, "rel_price"]
        li = d.loc[t, "log_inr"]
        star_total = float(xp @ b.to_numpy()) + d.loc[t, "rel_price"] if not np.isnan(xp).any() else np.nan
        # gap > 0: INR weaker than the BEER (undervalued). The band's low gap is the high BEER.
        out.loc[t] = [np.exp(star), np.exp(star_total), li - star, li - star_total,
                      li - np.percentile(draws, hi_p), li - np.percentile(draws, lo_p)]
    out["misalignment_pct"] = (np.exp(out["gap_log"]) - 1) * 100
    out["misalignment_total_pct"] = (np.exp(out["gap_log_total"]) - 1) * 100
    return out, diagnostics(d, cfg, pd.DataFrame(coefs), out)


def diagnostics(d: pd.DataFrame, cfg: dict, coefs: pd.DataFrame, out: pd.DataFrame) -> dict:
    p = cfg["models"]["beer"]
    specs = {}
    for name, regs in p["specs"].items():
        if not set(regs) <= set(d.columns):     # e.g. forward premia need the RBIH API
            continue
        x = d[["q"] + regs].dropna()
        b, V, res = dols(d, regs, p["dols_k"], p["hac_lags"])
        se = np.sqrt(np.diag(V))
        specs[name] = {
            "regressors": regs, "nobs": int(res.nobs),
            "sample": [x.index[0].strftime("%Y-%m"), x.index[-1].strftime("%Y-%m")],
            "coef": {k: float(v) for k, v in b.items()},
            "t_hac": {k: float(v) for k, v in zip(b.index, b.to_numpy() / se)},
            "expected_sign": {r: EXPECTED_SIGN[r] for r in regs},
            "engle_granger": engle_granger(x["q"], x[regs]),
            "johansen_rank": johansen_rank(x)["rank"],
        }
    central = specs[p["central_spec"]]
    # Does the BEER gap predict INR? Same out-of-sample test as the composite ECT.
    comp = pd.DataFrame({"log_inr": d["log_inr"], "ect": out["gap_log"]})
    oos = {h: backtest.evaluate(backtest.forecasts(comp, h, cfg["backtest"]["min_train"]), h)
           for h in cfg["backtest"]["horizons"]}
    path = {r: [float(coefs[r].min()), float(coefs[r].max())] for r in p["specs"][p["central_spec"]]} if len(coefs) else {}
    return {"central_spec": p["central_spec"], "specs": specs, "sample": central["sample"], "nobs": central["nobs"],
            "coef": central["coef"], "engle_granger": central["engle_granger"],
            "coef_path": path, "first_estimate": coefs["date"].min() if len(coefs) else None, "oos": oos}
