"""Calm/stress regimes for INR/USD returns.

* Markov-switching mean and variance (2 regimes). The probability used anywhere
  downstream is the *filtered* probability computed with parameters estimated
  on data public at t (re-estimated every ``refit_every`` months). Smoothed
  probabilities use future data and are only saved as an ex-post reference.
* statsmodels stores transitions as ``regime_transition[to, from]``; the
  row-stochastic matrix for forecasting is its transpose. The legacy notebook
  used it untransposed (rows summed to 1.15) and roughly doubled the 12-month
  stress probability.
* Oil x DXY quadrants use expanding medians so the split is also point-in-time.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression


def row_stochastic(res) -> np.ndarray:
    """P[i, j] = Pr(S_t = j | S_{t-1} = i)."""
    return np.asarray(res.regime_transition)[:, :, 0].T


def stress_forecast(P: np.ndarray, p_now: np.ndarray, horizons=(1, 3, 6, 12)) -> dict[int, np.ndarray]:
    P = np.asarray(P, dtype=float)
    if not np.allclose(P.sum(axis=1), 1):
        raise ValueError("transition matrix rows must sum to 1")
    return {h: np.asarray(p_now, dtype=float) @ np.linalg.matrix_power(P, h) for h in horizons}


def _fit(ret: pd.Series, seed: int):
    np.random.seed(seed)
    mod = MarkovRegression(ret.to_numpy(), k_regimes=2, trend="c", switching_variance=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = mod.fit(maxiter=500, em_iter=50, search_reps=10, disp=False)
    sig = [res.params[f"sigma2[{i}]"] if isinstance(res.params, pd.Series) else None for i in range(2)]
    if sig[0] is None:
        names = mod.param_names
        sig = [res.params[names.index(f"sigma2[{i}]")] for i in range(2)]
    stress = int(np.argmax(sig))
    return mod, res, stress


def _filtered_last(ret: np.ndarray, params: np.ndarray, stress: int) -> float:
    mod = MarkovRegression(ret, k_regimes=2, trend="c", switching_variance=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = mod.filter(params)
    return float(np.asarray(r.filtered_marginal_probabilities)[-1, stress])


def summarise(mod, res, stress: int) -> dict:
    names = mod.param_names
    par = dict(zip(names, np.asarray(res.params)))
    calm = 1 - stress
    P = row_stochastic(res)
    return {
        "calm": {"mean_pct": par[f"const[{calm}]"], "sd_pct": float(np.sqrt(par[f"sigma2[{calm}]"])),
                 "p_stay": float(P[calm, calm]), "expected_duration_m": float(1 / (1 - P[calm, calm]))},
        "stress": {"mean_pct": par[f"const[{stress}]"], "sd_pct": float(np.sqrt(par[f"sigma2[{stress}]"])),
                   "p_stay": float(P[stress, stress]), "expected_duration_m": float(1 / (1 - P[stress, stress]))},
        "transition_row_stochastic": P.tolist(),
        "stress_index": stress,
        "loglik": float(res.llf),
    }


def run(pit: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    p = cfg["models"]["regimes"]
    ret = (pit["log_inr"].diff() * 100).dropna()
    out = pd.DataFrame(index=pit.index)
    out["inr_ret_pct"] = ret

    p_rt = pd.Series(np.nan, index=pit.index)
    current = None
    refits = []
    for i in range(p["min_obs"] - 1, len(ret)):
        if current is None or (i - current[3]) >= p["refit_every"]:
            mod, res, stress = _fit(ret.iloc[: i + 1], p["seed"])
            current = (mod, res, stress, i)
            refits.append(ret.index[i].strftime("%Y-%m"))
        _, res, stress, _ = current
        p_rt[ret.index[i]] = _filtered_last(ret.iloc[: i + 1].to_numpy(), np.asarray(res.params), stress)
    out["p_stress_filtered"] = p_rt

    # Latest real-time model: summary + forward stress probabilities.
    mod, res, stress, _ = current
    summary = summarise(mod, res, stress)
    p_now = p_rt.dropna().iloc[-1]
    vec = np.zeros(2)
    vec[stress], vec[1 - stress] = p_now, 1 - p_now
    fc = stress_forecast(np.array(summary["transition_row_stochastic"]), vec)
    summary["p_stress_now"] = float(p_now)
    summary["p_stress_now_date"] = p_rt.dropna().index[-1].strftime("%Y-%m")
    summary["p_stress_forecast"] = {h: float(v[stress]) for h, v in fc.items()}
    P = np.array(summary["transition_row_stochastic"])
    summary["p_stress_steady_state"] = float(P[1 - stress, stress] / (P[1 - stress, stress] + P[stress, 1 - stress]))
    summary["refits"] = refits

    # Ex-post smoothed probabilities from the full-sample fit (reference only).
    mod_f, res_f, stress_f = _fit(ret, p["seed"])
    out.loc[ret.index, "p_stress_smoothed_expost"] = np.asarray(res_f.smoothed_marginal_probabilities)[:, stress_f]

    # Oil x DXY quadrant with expanding medians.
    b_med = pit["brent"].expanding(min_periods=36).median()
    d_med = pit["dxy"].expanding(min_periods=36).median()
    quad = np.where(pit["brent"] > b_med, "OilHi", "OilLo").astype(object)
    quad = quad + "_" + np.where(pit["dxy"] > d_med, "DXYHi", "DXYLo")
    out["oil_dxy_quadrant"] = pd.Series(quad, index=pit.index).where(b_med.notna() & d_med.notna())
    return out, summary
