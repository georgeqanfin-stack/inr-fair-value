"""Nonlinear and time-varying adjustment, and structural breaks.

The linear error-correction model (backtest.py) forecasts the h-month change in log
INR/USD as a + b x ECT. Two classic reasons it might under-use the signal:

* nonlinear adjustment: large misalignments revert faster than small ones
  (transaction costs, intervention bands; Taylor, Peel & Sarno 2001);
* time-varying adjustment: the strength of reversion drifts.

Variants, all re-estimated point in time exactly like the linear model (same training
cut, same targets) and scored with the same out-of-sample tests:

* threshold ECM: y = a + b_in ECT 1(|ECT| <= c) + b_out ECT 1(|ECT| > c), with c chosen
  on each training window from the 15th-85th percentiles of |ECT| by least squares;
* cubic: y = a + b ECT + g ECT^3, the standard Taylor approximation of an exponential
  smooth-transition (ESTAR) adjustment (Kapetanios, Shin & Snell 2003); g < 0 means
  faster reversion of large gaps;
* rolling: the linear model on the last ``rolling_months`` of training data only;
* time-varying parameters: a and b follow random walks, filtered by the Kalman filter;
  the state-noise ratio is chosen by maximum likelihood on each training window.
  Overlapping h-month targets make the errors MA(h-1), so this is a filter for drift,
  not an exact likelihood.

Breaks: sup-Wald tests (Andrews 1993) for one break in the coefficients of a
regression, with 15% trimming and a block-bootstrap p-value (overlapping targets and
persistent gaps make tabulated critical values unreliable); a second break is searched
on the larger segment when the first is significant (sequential, Bai & Perron 1998).
Applied to the 12-month ECM and to the mean of each misalignment series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import backtest

# --------------------------------------------------------------------------- forecasting variants


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def fit_linear(e, y, x):
    a, b = _ols(np.column_stack([np.ones(len(e)), e]), y)
    return a + b * x, {"b": b}


def fit_threshold(e, y, x, grid=np.linspace(0.15, 0.85, 15)):
    best = None
    for qn in np.quantile(np.abs(e), grid):
        inside = np.abs(e) <= qn
        if inside.sum() < 12 or (~inside).sum() < 12:
            continue
        X = np.column_stack([np.ones(len(e)), e * inside, e * ~inside])
        beta = _ols(X, y)
        ssr = float(np.sum((y - X @ beta) ** 2))
        if best is None or ssr < best[0]:
            best = (ssr, qn, beta)
    if best is None:
        return fit_linear(e, y, x)
    _, c, (a, b_in, b_out) = best
    return a + (b_in if abs(x) <= c else b_out) * x, {"c": c, "b_in": b_in, "b_out": b_out}


def fit_cubic(e, y, x):
    a, b, g = _ols(np.column_stack([np.ones(len(e)), e, e ** 3]), y)
    return a + b * x + g * x ** 3, {"b": b, "g": g}


def _kalman(e, y, q):
    """Random-walk (a, b); returns log-likelihood and the final filtered state."""
    s2 = np.var(y) if np.var(y) > 0 else 1.0
    beta = _ols(np.column_stack([np.ones(len(e)), e]), y)
    P = np.eye(2) * s2 * 10
    Q = np.diag([q * s2, q * s2 / max(np.var(e), 1e-12)])
    R = s2
    ll = 0.0
    for et, yt in zip(e, y):
        P = P + Q
        z = np.array([1.0, et])
        f = z @ P @ z + R
        v = yt - z @ beta
        K = P @ z / f
        beta = beta + K * v
        P = P - np.outer(K, z) @ P
        ll += -0.5 * (np.log(f) + v * v / f)
    return ll, beta


def fit_tvp(e, y, x, qs=(1e-5, 1e-4, 1e-3, 1e-2, 1e-1)):
    best = max(((q, *_kalman(e, y, q)) for q in qs), key=lambda r: r[1])
    q, _, (a, b) = best
    return a + b * x, {"q": q, "b": b}


def forecasts(comp: pd.DataFrame, h: int, min_train: int, fit, window: int | None = None) -> pd.DataFrame:
    """Same loop as backtest.forecasts, with any fit(e_train, y_train, x_now) -> (forecast, params)."""
    df = comp[["log_inr", "ect"]].copy()
    df["y"] = df["log_inr"].shift(-h) - df["log_inr"]
    rows = []
    for i, t in enumerate(df.index):
        if np.isnan(df["ect"].iloc[i]) or i - h < 0:
            continue
        tr = df.iloc[: i - h + 1].dropna(subset=["y", "ect"])
        if len(tr) < min_train:
            continue
        if window:
            tr = tr.iloc[-window:]
        f, par = fit(tr["ect"].to_numpy(), tr["y"].to_numpy(), df["ect"].iloc[i])
        rows.append({"date": t, "ect": df["ect"].iloc[i], "y": df["y"].iloc[i], "f_drift": tr["y"].mean() if not window
                     else df.iloc[: i - h + 1]["y"].dropna().mean(), "f_ecm": f, "alpha": par.get("b", np.nan),
                     **{f"p_{k}": v for k, v in par.items()}})
    return pd.DataFrame(rows).set_index("date")


VARIANTS = {"linear": (fit_linear, None), "threshold": (fit_threshold, None), "cubic": (fit_cubic, None),
            "rolling": (fit_linear, "rolling"), "tvp": (fit_tvp, None)}
LABELS = {"linear": "Linear ECM (headline)", "threshold": "Threshold ECM", "cubic": "Cubic (ESTAR approximation)",
          "rolling": "Rolling-window ECM", "tvp": "Time-varying parameters (Kalman)"}


# --------------------------------------------------------------------------- breaks


def sup_wald(y: np.ndarray, X: np.ndarray, trim: float = 0.15) -> tuple[float, int]:
    """Largest Chow-type F statistic over candidate break points, and its position."""
    n, k = X.shape
    beta = _ols(X, y)
    ssr0 = float(np.sum((y - X @ beta) ** 2))
    best, at = -np.inf, None
    for j in range(int(n * trim), int(n * (1 - trim))):
        Z = np.hstack([X, X * (np.arange(n) >= j)[:, None]])
        b = _ols(Z, y)
        ssr1 = float(np.sum((y - Z @ b) ** 2))
        F = (ssr0 - ssr1) / k / (ssr1 / (n - 2 * k))
        if F > best:
            best, at = F, j
    return best, at


def break_test(y: pd.Series, X: pd.DataFrame, reps: int, block: int, rng, trim: float = 0.15) -> dict:
    """One-break sup-Wald with a moving-block bootstrap p-value under no break."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    yv, Xv = d["y"].to_numpy(), d.drop(columns="y").to_numpy()
    stat, at = sup_wald(yv, Xv, trim)
    beta = _ols(Xv, yv)
    fit, res = Xv @ beta, yv - Xv @ beta
    n = len(yv)
    exceed = 0
    for _ in range(reps):
        starts = rng.integers(0, n - block + 1, int(np.ceil(n / block)))
        e = np.concatenate([res[s:s + block] for s in starts])[:n]
        exceed += sup_wald(fit + e, Xv, trim)[0] >= stat
    idx = d.index
    pre, post = slice(0, at), slice(at, n)
    return {"stat": float(stat), "p": float((exceed + 1) / (reps + 1)), "date": idx[at].strftime("%Y-%m"),
            "n": int(n), "sample": [idx[0].strftime("%Y-%m"), idx[-1].strftime("%Y-%m")],
            "before": _ols(Xv[pre], yv[pre]).tolist(), "after": _ols(Xv[post], yv[post]).tolist()}


def sequential_breaks(y: pd.Series, X: pd.DataFrame, cfg: dict, rng) -> list[dict]:
    """Bai-Perron style: test the full sample; if significant, test the larger segment."""
    out = []
    first = break_test(y, X, cfg["break_reps"], cfg["break_block"], rng)
    out.append(first)
    if first["p"] < 0.05:
        d = pd.concat([y.rename("y"), X], axis=1).dropna()
        cut = pd.Timestamp(first["date"] + "-01")
        seg = d[d.index < cut] if (d.index < cut).sum() >= (d.index >= cut).sum() else d[d.index >= cut]
        if len(seg) >= 60:
            out.append(break_test(seg["y"], seg.drop(columns="y"), cfg["break_reps"], cfg["break_block"], rng))
    return out


# --------------------------------------------------------------------------- run


def run(comp: pd.DataFrame, components: dict[str, pd.Series], cfg: dict) -> dict:
    p = cfg["models"]["nonlinear"]
    b = cfg["backtest"]
    h = b["headline_horizon"]
    res, fcs = {}, {}
    for name, (fit, flag) in VARIANTS.items():
        res[name] = {"label": LABELS[name], "by_horizon": {}}
        for k in b["horizons"]:
            fc = forecasts(comp, k, b["min_train"], fit, window=p["rolling_months"] if flag == "rolling" else None)
            e = backtest.evaluate(fc, k)
            res[name]["by_horizon"][k] = {"rmse_ratio": e.get("rmse_ratio_ecm_vs_drift"),
                                          "cw_p": (e.get("clark_west") or {}).get("pvalue_one_sided"),
                                          "n": e.get("n_oos")}
            if k == h:
                fcs[name] = fc
    # Is reversion faster for large gaps? Last fit of each nonlinear variant.
    last = {n: {c[2:]: float(v) for c, v in fcs[n].iloc[-1].items() if c.startswith("p_")} for n in ("threshold", "cubic", "tvp")}
    base = res["linear"]["by_horizon"][h]
    better = [n for n, v in res.items() if n != "linear" and v["by_horizon"][h]["rmse_ratio"] is not None
              and base["rmse_ratio"] - v["by_horizon"][h]["rmse_ratio"] >= p["min_rmse_gain"]
              and v["by_horizon"][h]["cw_p"] < base["cw_p"]]
    choice = min(better, key=lambda n: res[n]["by_horizon"][h]["rmse_ratio"]) if better else "linear"
    # Robustness of the rolling window (added after the first results): the gain must hold
    # at the median of nearby window lengths, not just the pre-set one.
    robust = {}
    for w in p["robustness_windows"]:
        e = backtest.evaluate(forecasts(comp, h, b["min_train"], fit_linear, window=w), h)
        robust[w] = {"rmse_ratio": e.get("rmse_ratio_ecm_vs_drift"), "cw_p": (e.get("clark_west") or {}).get("pvalue_one_sided")}
    med = float(np.median([v["rmse_ratio"] for v in robust.values()]))
    rolling_robust = base["rmse_ratio"] - med >= p["min_rmse_gain"]
    adopted = choice if (choice != "rolling" or rolling_robust) else "linear"

    rng = np.random.default_rng(p["seed"])
    y12 = comp["log_inr"].shift(-h) - comp["log_inr"]
    breaks = {"ecm": {"label": f"{h}-month ECM (intercept and slope)",
                      "tests": sequential_breaks(y12, pd.DataFrame({"const": 1.0, "ect": comp["ect"]}, index=comp.index),
                                                 p, rng)}}
    for k, s in components.items():
        breaks[k] = {"label": f"Mean of {k} misalignment", "tests": sequential_breaks(
            s, pd.DataFrame({"const": 1.0}, index=s.index), p, rng)}
    tvp_path = fcs["tvp"]["p_b"] if "p_b" in fcs["tvp"] else None
    return {"variants": res, "horizon": h, "choice": choice, "adopted": adopted, "rolling_robustness": robust,
            "rolling_median_ratio": med, "rolling_robust": bool(rolling_robust), "rule": {"min_rmse_gain": p["min_rmse_gain"]},
            "last_params": last, "breaks": breaks,
            "tvp_slope": tvp_path, "threshold_path": fcs["threshold"][["p_c", "p_b_in", "p_b_out"]]
            if "p_c" in fcs["threshold"] else None}
