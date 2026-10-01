"""Composite weights: tested, not assumed.

The composite averages the REER component's and the FEER's log gaps. This module
compares weighting schemes, all point in time, through the same out-of-sample backtest
as the headline composite:

* equal: 1/2 each (the configured default);
* inverse variance: each month, weights proportional to 1 / variance of each
  component's gap, the variance read from its own 10th-90th percentile band
  (sd = band width / 2.563);
* performance (Bates-Granger): each month, weights proportional to 1 / mean squared
  error of each component's own error-correction forecasts at the headline horizon,
  using only forecasts whose outcomes were known by then (equal until 24 are);
* REER only and FEER only, as references.

Decision rule, set before seeing the results ([composite] weight_rule): keep equal
weights unless a scheme lowers the headline-horizon RMSE ratio vs drift by at least
``min_rmse_gain`` and also has a lower Clark-West p-value. Equal weights are a strong
default in the forecast-combination literature because estimated weights add noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import backtest

Z90 = 2 * 1.2816       # width of a 10th-90th percentile band in standard deviations


def _comp(comp: pd.DataFrame, ect: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"log_inr": comp["log_inr"], "ect": ect})


def inverse_variance(reer: pd.DataFrame, feer_m: pd.DataFrame) -> pd.Series:
    """Weight on the REER component, month by month."""
    vr = ((reer["gap_log_hi"] - reer["gap_log_lo"]) / Z90) ** 2
    vf = ((feer_m["gap_log_hi"] - feer_m["gap_log_lo"]) / Z90) ** 2
    w = (1 / vr) / (1 / vr + 1 / vf)
    return w.where(np.isfinite(w))


def performance(comp: pd.DataFrame, h: int, min_train: int, min_errors: int = 24, window: int | None = None) -> pd.Series:
    """Bates-Granger weight on the REER component from past squared forecast errors."""
    err = {}
    for k in ("gap_reer", "gap_feer"):
        fc = backtest.forecasts(_comp(comp, comp[k]), h, min_train, window).dropna(subset=["y"])
        e2 = (fc["y"] - fc["f_ecm"]) ** 2
        e2.index = e2.index + pd.DateOffset(months=h)            # known once the target is realised
        err[k] = e2
    out = pd.Series(np.nan, index=comp.index)
    for t in comp.index:
        r, f = err["gap_reer"].loc[:t], err["gap_feer"].loc[:t]
        if len(r) >= min_errors and len(f) >= min_errors:
            ir, if_ = 1 / r.mean(), 1 / f.mean()
            out[t] = ir / (ir + if_)
    return out.fillna(0.5).where(comp["ect"].notna())


def schemes(comp: pd.DataFrame, reer: pd.DataFrame, feer_m: pd.DataFrame, cfg: dict) -> dict[str, pd.Series]:
    """REER-component weight per month for each scheme."""
    h, mt = cfg["backtest"]["headline_horizon"], cfg["backtest"]["min_train"]
    ones = pd.Series(1.0, index=comp.index)
    out = {"equal": ones * 0.5, "reer_only": ones, "feer_only": ones * 0.0}
    if {"gap_log_lo", "gap_log_hi"} <= set(reer.columns) and {"gap_log_lo", "gap_log_hi"} <= set(feer_m.columns):
        out["inverse_variance"] = inverse_variance(reer, feer_m).reindex(comp.index)
    out["performance"] = performance(comp, h, mt, window=cfg["backtest"].get("window_months"))
    return out


LABELS = {"equal": "Equal (1/2 each)", "inverse_variance": "Inverse variance (bands)",
          "performance": "Performance (Bates-Granger)", "reer_only": "REER component only", "feer_only": "FEER only"}


def run(comp: pd.DataFrame, reer: pd.DataFrame, feer_m: pd.DataFrame, cfg: dict) -> dict:
    b, rule = cfg["backtest"], cfg["composite"].get("weight_rule", {"min_rmse_gain": 0.01})
    h = b["headline_horizon"]
    res, weights = {}, {}
    for name, w in schemes(comp, reer, feer_m, cfg).items():
        ect = w * comp["gap_reer"] + (1 - w) * comp["gap_feer"]
        evals = {k: backtest.evaluate(backtest.forecasts(_comp(comp, ect), k, b["min_train"], b.get("window_months")), k)
                 for k in b["horizons"]}
        last_w = w.dropna()
        res[name] = {"label": LABELS[name], "weight_reer_last": float(last_w.iloc[-1]) if len(last_w) else None,
                     "weight_reer_mean": float(last_w.mean()) if len(last_w) else None,
                     "misalignment_last": float((np.exp(ect.dropna().iloc[-1]) - 1) * 100),
                     "by_horizon": {k: {"rmse_ratio": e.get("rmse_ratio_ecm_vs_drift"),
                                        "cw_p": (e.get("clark_west") or {}).get("pvalue_one_sided"),
                                        "n": e.get("n_oos")} for k, e in evals.items()}}
        weights[name] = w
    base = res["equal"]["by_horizon"][h]
    better = [n for n, v in res.items()
              if n not in ("equal", "reer_only", "feer_only")
              and v["by_horizon"][h]["rmse_ratio"] is not None
              and base["rmse_ratio"] - v["by_horizon"][h]["rmse_ratio"] >= rule["min_rmse_gain"]
              and v["by_horizon"][h]["cw_p"] < base["cw_p"]]
    best = min(better, key=lambda n: res[n]["by_horizon"][h]["rmse_ratio"]) if better else "equal"
    configured = "equal" if cfg["composite"]["weight_reer"] == cfg["composite"]["weight_feer"] else "custom"
    mis = [v["misalignment_last"] for k, v in res.items() if k in ("equal", "inverse_variance", "performance")]
    return {"schemes": res, "horizon": h, "rule": rule, "rule_choice": best, "configured": configured,
            "headline_range": [float(min(mis)), float(max(mis))],
            "weights": pd.DataFrame(weights)}
