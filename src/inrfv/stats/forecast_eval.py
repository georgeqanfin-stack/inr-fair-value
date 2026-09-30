"""Forecast evaluation for overlapping multi-horizon exchange-rate forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def newey_west_var_of_mean(x: np.ndarray, lags: int) -> float:
    """Newey-West (Bartlett) long-run variance of the sample mean of x."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    n = len(x)
    lrv = x @ x / n
    for k in range(1, min(lags, n - 1) + 1):
        w = 1 - k / (lags + 1)
        lrv += 2 * w * (x[k:] @ x[:-k]) / n
    return max(lrv, 1e-300) / n


def clark_west(y: np.ndarray, f_null: np.ndarray, f_alt: np.ndarray, h: int) -> dict:
    """Clark & West (2007) test of equal MSPE for nested models.

    H0: the larger model (f_alt) does not improve on the nested null (f_null).
    One-sided: a significant positive statistic favours f_alt.
    """
    e1, e2 = y - f_null, y - f_alt
    adj = e1**2 - (e2**2 - (f_null - f_alt) ** 2)
    t = adj.mean() / np.sqrt(newey_west_var_of_mean(adj, max(h - 1, 0)))
    return {"stat": float(t), "pvalue_one_sided": float(1 - stats.norm.cdf(t))}


def diebold_mariano(y: np.ndarray, f1: np.ndarray, f2: np.ndarray, h: int) -> dict:
    """DM test on squared errors with the Harvey-Leybourne-Newbold small-sample correction.

    Positive statistic: f2 has lower MSPE than f1.
    """
    d = (y - f1) ** 2 - (y - f2) ** 2
    n = len(d)
    dm = d.mean() / np.sqrt(newey_west_var_of_mean(d, max(h - 1, 0)))
    hln = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    stat = dm * hln
    return {"stat": float(stat), "pvalue_two_sided": float(2 * (1 - stats.t.cdf(abs(stat), df=n - 1)))}


def oos_r2(y: np.ndarray, f_null: np.ndarray, f_alt: np.ndarray) -> float:
    """Campbell-Thompson out-of-sample R^2 of f_alt relative to f_null."""
    return float(1 - np.sum((y - f_alt) ** 2) / np.sum((y - f_null) ** 2))


def hodrick_1b(log_level: pd.Series, x: pd.Series, h: int) -> dict:
    """Regression of h-period change on x_t with Hodrick (1992) 1B standard errors.

    Hodrick's estimator rolls the overlapping regressor backwards instead of the
    overlapping residual forwards, which keeps the test well sized when h is large
    relative to the sample - the Newey-West alternative over-rejects here.
    """
    df = pd.DataFrame({"p": log_level, "x": x}).dropna()
    p, xv = df["p"].to_numpy(), df["x"].to_numpy()
    n = len(df)
    y = np.full(n, np.nan)
    y[: n - h] = p[h:] - p[: n - h]
    r1 = np.full(n, np.nan)
    r1[: n - 1] = p[1:] - p[:-1]
    X = np.column_stack([np.ones(n), xv])

    ok = ~np.isnan(y)
    Xo, yo = X[ok], y[ok]
    beta = np.linalg.lstsq(Xo, yo, rcond=None)[0]

    # Under H0 (no predictability) one-period residuals are demeaned returns.
    eps = r1 - np.nanmean(r1[: n - 1])
    T = 0
    S = np.zeros((2, 2))
    for t in range(h - 1, n - 1):
        z = X[t - h + 1: t + 1].sum(axis=0)
        S += eps[t] ** 2 * np.outer(z, z)
        T += 1
    S /= T
    Zxx = Xo.T @ Xo / len(yo)
    inv = np.linalg.inv(Zxx)
    V = inv @ S @ inv / len(yo)
    se = float(np.sqrt(V[1, 1]))
    tstat = beta[1] / se
    return {"beta": float(beta[1]), "const": float(beta[0]), "se_hodrick": se,
            "t_hodrick": float(tstat), "pvalue": float(2 * (1 - stats.norm.cdf(abs(tstat)))),
            "nobs": int(ok.sum())}


def non_overlapping_betas(log_level: pd.Series, x: pd.Series, h: int) -> dict:
    """OLS slope using every h-th observation, for each of the h possible offsets."""
    df = pd.DataFrame({"p": log_level, "x": x}).dropna()
    df["y"] = df["p"].shift(-h) - df["p"]
    df = df.dropna()
    betas, tstats = [], []
    for off in range(h):
        d = df.iloc[off::h]
        if len(d) < 8:
            continue
        X = np.column_stack([np.ones(len(d)), d["x"]])
        b, res, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
        resid = d["y"].to_numpy() - X @ b
        s2 = resid @ resid / (len(d) - 2)
        se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
        betas.append(b[1])
        tstats.append(b[1] / se)
    if not betas:
        return {}
    return {"beta_median": float(np.median(betas)), "beta_min": float(min(betas)),
            "beta_max": float(max(betas)), "t_median": float(np.median(tstats)),
            "n_per_offset": int(len(df) // h), "offsets": len(betas)}
