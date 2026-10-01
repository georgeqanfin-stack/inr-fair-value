"""Regimes with time-varying transition probabilities (TVTP), tested against constant ones.

The headline regime model (regimes.py) has constant probabilities of switching between
calm and stress. Here the switching odds depend on drivers known the month before
(Filardo 1994; statsmodels' logistic TVTP):

* VIX, monthly change;   * Brent, monthly % change;
* net FPI flows (US$ bn, as published, two-month lag);
* RBI intervention (US$ bn, as published, two-month lag).

Each driver is standardised on the training window and lagged one month, so a month's
transition probability uses only information public before it.

Tests, set before running:

* full sample: likelihood-ratio test against the constant model, AIC and BIC;
* out of sample (the deciding test): one-step-ahead predictive density of each month's
  INR/USD return, from regime probabilities predicted with information up to the
  previous month and parameters re-estimated every ``refit_every`` months. Mean log
  score difference vs the constant model with a Newey-West t-test (Amisano & Giacomini
  2007), and the AUC of the predicted stress probability for big-move months (|return|
  in the top 20%).

The headline regime model changes only if a TVTP specification beats the constant one
out of sample with a one-sided p below ``switch_p``.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

DRIVERS = {"vix": "VIX (change)", "brent": "Brent (% change)", "fpi": "FPI flows", "rbi": "RBI intervention"}


def drivers(pit: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame({"vix": pit["vix"].diff(), "brent": np.log(pit["brent"]).diff() * 100,
                      "fpi": pit["fpi_usd_mn"] / 1000})
    if "rbi_intervention_usd_mn" in pit:
        d["rbi"] = pit["rbi_intervention_usd_mn"] / 1000
    return d.shift(1)


def _model(r: np.ndarray, Z: np.ndarray | None):
    ex = None if Z is None else np.column_stack([np.ones(len(r)), Z])
    return MarkovRegression(r, k_regimes=2, trend="c", switching_variance=True, exog_tvtp=ex)


def fit(r: np.ndarray, Z: np.ndarray | None, seed: int):
    np.random.seed(seed)
    mod = _model(r, Z)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = mod.fit(maxiter=500, em_iter=50, search_reps=10, disp=False)
    par = dict(zip(mod.param_names, np.asarray(res.params)))
    stress = int(np.argmax([par["sigma2[0]"], par["sigma2[1]"]]))
    return mod, res, stress


def _std(train: pd.DataFrame, cols: list[str]):
    mu, sd = train[cols].mean(), train[cols].std().replace(0, 1)
    return lambda df: ((df[cols] - mu) / sd).to_numpy()


def oos(d: pd.DataFrame, cols: list[str], min_obs: int, refit_every: int, seed: int) -> pd.DataFrame:
    rows, cur = [], None
    for i in range(min_obs, len(d)):
        if cur is None or i - cur[3] >= refit_every:
            train = d.iloc[:i]
            z = _std(train, cols) if cols else None
            _, res, stress = fit(train["r"].to_numpy(), z(train) if z else None, seed)
            cur = (res, stress, z, i)
        res, stress, z, _ = cur
        upto = d.iloc[: i + 1]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            f = _model(upto["r"].to_numpy(), z(upto) if z else None).filter(np.asarray(res.params))
        p = np.asarray(f.predicted_marginal_probabilities)[-1]
        par = dict(zip(f.model.param_names, np.asarray(res.params)))
        dens = sum(p[j] * stats.norm.pdf(d["r"].iloc[i], par[f"const[{j}]"], np.sqrt(par[f"sigma2[{j}]"]))
                   for j in range(2))
        rows.append({"date": d.index[i], "log_score": float(np.log(dens)), "p_stress_pred": float(p[stress])})
    return pd.DataFrame(rows).set_index("date")


def _auc(score: pd.Series, event: pd.Series) -> float:
    s, e = score.to_numpy(), event.to_numpy().astype(bool)
    if e.all() or (~e).all():
        return float("nan")
    ranks = stats.rankdata(s)
    return float((ranks[e].sum() - e.sum() * (e.sum() + 1) / 2) / (e.sum() * (~e).sum()))


def _nw_t(x: np.ndarray, lags: int = 3) -> float:
    """t-statistic of the mean of x with a Newey-West (Bartlett) long-run variance."""
    m, n = float(np.mean(x)), len(x)
    e = x - m
    v = e @ e / n
    for k in range(1, lags + 1):
        v += 2 * (1 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    return float(np.sqrt(n) * m / np.sqrt(v)) if v > 0 else float("nan")


def run(pit: pd.DataFrame, cfg: dict) -> dict:
    p = cfg["models"]["regimes_tvtp"]
    ret = (pit["log_inr"].diff() * 100).rename("r")
    drv = drivers(pit)
    d = pd.concat([ret, drv], axis=1).dropna()
    specs = {"constant": [], **{k: [k] for k in drv.columns}, "all": list(drv.columns)}
    from ..config import path
    key = hashlib.sha256(pd.util.hash_pandas_object(d, index=True).to_numpy().tobytes()
                         + json.dumps([p, sorted(specs)], sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache = path(cfg, "runs").parent / "cache" / f"regimes_tvtp_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    full = {}
    for name, cols in specs.items():
        z = _std(d, cols)(d) if cols else None
        _, res, stress = fit(d["r"].to_numpy(), z, p["seed"])
        full[name] = {"loglik": float(res.llf), "aic": float(res.aic), "bic": float(res.bic),
                      "k": int(len(res.params))}
    base = full["constant"]
    for name, v in full.items():
        if name == "constant":
            continue
        lr = 2 * (v["loglik"] - base["loglik"])
        v["lr"] = float(lr)
        v["lr_p"] = float(stats.chi2.sf(max(lr, 0), v["k"] - base["k"]))

    scores = {name: oos(d, cols, p["min_obs"], p["refit_every"], p["seed"]) for name, cols in specs.items()}
    big = d["r"].abs() >= d["r"].abs().quantile(0.8)
    out_oos = {}
    for name, s in scores.items():
        diff = s["log_score"] - scores["constant"]["log_score"]
        t = _nw_t(diff.to_numpy()) if name != "constant" else float("nan")
        out_oos[name] = {"mean_log_score": float(s["log_score"].mean()), "n": int(len(s)),
                         "diff_vs_constant": float(diff.mean()) if name != "constant" else 0.0,
                         "t": t, "p_one_sided": float(stats.norm.sf(t)) if name != "constant" else None,
                         "auc_big_moves": _auc(s["p_stress_pred"], big.reindex(s.index))}
    cands = [n for n, v in out_oos.items() if n != "constant" and v["p_one_sided"] is not None
             and v["p_one_sided"] < p["switch_p"] and v["diff_vs_constant"] > 0]
    choice = max(cands, key=lambda n: out_oos[n]["diff_vs_constant"]) if cands else "constant"
    result = {"specs": {n: {"drivers": [DRIVERS[c] for c in cols]} for n, cols in specs.items()},
              "full_sample": full, "oos": out_oos, "choice": choice, "switch_p": p["switch_p"],
              "sample": [d.index[0].strftime("%Y-%m"), d.index[-1].strftime("%Y-%m")],
              "oos_window": [scores["constant"].index[0].strftime("%Y-%m"),
                             scores["constant"].index[-1].strftime("%Y-%m")]}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result), encoding="utf-8")
    return result
