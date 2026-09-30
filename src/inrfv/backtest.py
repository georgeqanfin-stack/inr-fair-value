"""Out-of-sample evaluation of the error-correction signal.

For each horizon h and forecast origin t:
  target   y_t = log INR_{t+h} - log INR_t
  training rows s with s + h <= t  (the target must be fully realised at t;
           the legacy expanding window used rows whose targets ended after t)
  null     random walk with drift: mean of training targets
  model    OLS  y_s = a + b * ECT_s  ->  a + b * ECT_t

The benchmark is the random walk with drift because INR depreciated in most
12-month windows: a model that always says "depreciate" looks accurate without
using the signal at all (the legacy 92% hit rate was exactly that baseline).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .stats.forecast_eval import (clark_west, diebold_mariano, hodrick_1b,
                                  non_overlapping_betas, oos_r2)


def forecasts(comp: pd.DataFrame, h: int, min_train: int) -> pd.DataFrame:
    df = comp[["log_inr", "ect"]].copy()
    df["y"] = df["log_inr"].shift(-h) - df["log_inr"]
    idx = df.index
    rows = []
    for i, t in enumerate(idx):
        if np.isnan(df["ect"].iloc[i]):
            continue
        cut = i - h
        if cut < 0:
            continue
        tr = df.iloc[: cut + 1].dropna(subset=["y", "ect"])
        if len(tr) < min_train:
            continue
        a, b = np.linalg.lstsq(np.column_stack([np.ones(len(tr)), tr["ect"]]), tr["y"].to_numpy(), rcond=None)[0]
        rows.append({"date": t, "ect": df["ect"].iloc[i], "y": df["y"].iloc[i],
                     "f_drift": tr["y"].mean(), "f_ecm": a + b * df["ect"].iloc[i],
                     "alpha": b, "const": a, "n_train": len(tr)})
    return pd.DataFrame(rows).set_index("date")


def evaluate(fc: pd.DataFrame, h: int) -> dict:
    d = fc.dropna(subset=["y"])
    if len(d) < 12:
        return {"n_oos": len(d)}
    y, f0, f1 = d["y"].to_numpy(), d["f_drift"].to_numpy(), d["f_ecm"].to_numpy()
    rmse = lambda f: float(np.sqrt(np.mean((y - f) ** 2)))
    return {
        "n_oos": len(d),
        "oos_window": [d.index[0].strftime("%Y-%m"), d.index[-1].strftime("%Y-%m")],
        "rmse_zero": rmse(np.zeros_like(y)),
        "rmse_drift": rmse(f0),
        "rmse_ecm": rmse(f1),
        "rmse_ratio_ecm_vs_drift": rmse(f1) / rmse(f0),
        "oos_r2_vs_drift": oos_r2(y, f0, f1),
        "clark_west": clark_west(y, f0, f1, h),
        "diebold_mariano": diebold_mariano(y, f0, f1, h),
        "hit_rate_ecm_sign": float(np.mean(np.sign(f1) == np.sign(y))),
        "hit_rate_naive_depreciation": float(np.mean(y > 0)),
        "hit_rate_excess_over_drift": float(np.mean(np.sign(f1 - f0) == np.sign(y - f0))),
        "share_ecm_predicts_appreciation": float(np.mean(f1 < 0)),
        "alpha_min": float(fc["alpha"].min()), "alpha_max": float(fc["alpha"].max()),
        "alpha_last": float(fc["alpha"].iloc[-1]),
    }


def in_sample(comp: pd.DataFrame, h: int, p_stress: pd.Series | None = None) -> dict:
    out = {"hodrick": hodrick_1b(comp["log_inr"], comp["ect"], h),
           "non_overlapping": non_overlapping_betas(comp["log_inr"], comp["ect"], h)}
    if p_stress is not None:
        d = pd.DataFrame({"y": comp["log_inr"].shift(-h) - comp["log_inr"], "ect": comp["ect"],
                          "p": p_stress}).dropna()
        if len(d) > 30:
            X = sm.add_constant(pd.DataFrame({"ect_calm": d["ect"] * (1 - d["p"]),
                                              "ect_stress": d["ect"] * d["p"]}))
            r = sm.OLS(d["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": max(h - 1, 1)})
            out["regime_conditional"] = {
                "coef": {k: float(v) for k, v in r.params.items()},
                "pvalues_nw": {k: float(v) for k, v in r.pvalues.items()},
                "nobs": int(r.nobs),
                "note": "p_stress is the real-time filtered probability",
            }
    return out


def run(comp: pd.DataFrame, regimes: pd.DataFrame, cfg: dict) -> tuple[dict, dict[int, pd.DataFrame]]:
    b = cfg["backtest"]
    results, fcs = {}, {}
    for h in b["horizons"]:
        fc = forecasts(comp, h, b["min_train"])
        fcs[h] = fc
        results[h] = {"oos": evaluate(fc, h),
                      "in_sample": in_sample(comp, h, regimes["p_stress_filtered"])}
    return results, fcs


def current_forecast(comp: pd.DataFrame, h: int) -> dict:
    """Forecast from the latest ECT, estimated on every fully realised target."""
    df = comp[["log_inr", "ect"]].copy()
    df["y"] = df["log_inr"].shift(-h) - df["log_inr"]
    tr = df.dropna()
    a, b = np.linalg.lstsq(np.column_stack([np.ones(len(tr)), tr["ect"]]), tr["y"].to_numpy(), rcond=None)[0]
    last = df["ect"].dropna()
    e = float(last.iloc[-1])
    return {"asof": last.index[-1].strftime("%Y-%m"), "h": h, "ect": e, "const": float(a), "alpha": float(b),
            "forecast_log_change": float(a + b * e), "drift_only": float(tr["y"].mean()),
            "train_window": [tr.index[0].strftime("%Y-%m"), tr.index[-1].strftime("%Y-%m")]}
