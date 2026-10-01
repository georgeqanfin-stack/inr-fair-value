"""Formal panel cointegration tests with bootstrap p-values, and multiple testing.

Statistics (H0: no cointegration in any country; left tail rejects):

* Pedroni-type residual tests (Pedroni 1999, 2004): each country's own cointegrating
  regression y_it = a_i + b_i'x_it + e_it (heterogeneous slopes), then
  - group ADF: the mean of the countries' ADF t-statistics on e_it;
  - panel ADF: the t-statistic of a common rho in a pooled ADF regression on e_it
    (country-specific lag terms).
* Westerlund (2007) error-correction tests, per country
      dy_t = d_i + alpha_i y_{t-1} + lambda_i'x_{t-1} + phi_i dy_{t-1} + g0_i'dx_t + g1_i'dx_{t-1} + e_t
  - Gt: the mean of the alpha_i t-statistics (group mean; heterogeneous adjustment);
  - Pt: the t-statistic of a pooled alpha after partialling out each country's other terms.

P-values come from one bootstrap under H0 (Westerlund 2007's approach): each country's
restricted model without the error-correction terms is fitted, years are resampled
jointly across countries (keeping cross-sectional dependence), dy is rebuilt
recursively and cumulated, and every statistic is recomputed on the artificial
non-cointegrated panel. Tabulated asymptotic moments are not used: with T around 30 and
correlated countries they are unreliable.

Multiple testing: a specification search inflates the chance of a spurious "pass".
Holm (family-wise error) and Benjamini-Hochberg (false discovery rate) adjust the
p-values over an explicit family of specifications.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd


def _ols(X, y):
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    res = y - X @ beta
    df = len(y) - X.shape[1]
    s2 = res @ res / df if df > 0 else np.nan
    cov = s2 * np.linalg.pinv(X.T @ X)
    return beta, res, cov


def balanced(panel: pd.DataFrame, regs: list[str]) -> dict[str, tuple[np.ndarray, np.ndarray]] | None:
    """Country -> (y, X) over the years every country covers for these variables."""
    d = panel[["log_reer"] + regs].dropna()
    years = d.reset_index().groupby("year")["country"].nunique()
    n_c = d.index.get_level_values("country").nunique()
    common = years[years == n_c].index
    if len(common) < 10:
        return None
    d = d[d.index.get_level_values("year").isin(common)]
    return {c: (g["log_reer"].to_numpy(), g[regs].to_numpy()) for c, g in d.groupby(level="country")}


def _westerlund_parts(y, X):
    dy, dX = np.diff(y), np.diff(X, axis=0)
    t = np.arange(2, len(y))                      # rows usable with one lag of dy and dx
    Z = np.column_stack([np.ones(len(t)), y[t - 1], X[t - 1], dy[t - 2], dX[t - 1], dX[t - 2]])
    return dy[t - 1], Z


def westerlund(data: dict) -> dict:
    tg, num, den, s2s = [], 0.0, 0.0, []
    for y, X in data.values():
        dy, Z = _westerlund_parts(y, X)
        if len(dy) - Z.shape[1] < 6:
            return {"Gt": np.nan, "Pt": np.nan}
        beta, res, cov = _ols(Z, dy)
        tg.append(beta[1] / np.sqrt(cov[1, 1]))
        others = np.delete(Z, 1, axis=1)
        py = dy - others @ np.linalg.lstsq(others, dy, rcond=None)[0]
        pz = Z[:, 1] - others @ np.linalg.lstsq(others, Z[:, 1], rcond=None)[0]
        num += pz @ py
        den += pz @ pz
        s2s.append((res @ res) / (len(dy) - Z.shape[1]))
    a = num / den
    se = np.sqrt(np.mean(s2s) / den)
    return {"Gt": float(np.mean(tg)), "Pt": float(a / se)}


def _adf_t(e, lags=1):
    de = np.diff(e)
    t = np.arange(lags + 1, len(e))
    Z = np.column_stack([e[t - 1]] + [de[t - 1 - j] for j in range(1, lags + 1)])
    beta, _, cov = _ols(Z, de[t - 1])
    return beta[0] / np.sqrt(cov[0, 0]), de[t - 1], Z


def pedroni(data: dict) -> dict:
    ts, dep, cols = [], [], []
    for y, X in data.values():
        Zc = np.column_stack([np.ones(len(y)), X])
        _, e, _ = _ols(Zc, y)
        t, d, Z = _adf_t(e)
        ts.append(t)
        dep.append(d)
        cols.append(Z)
    # Pooled ADF: common rho, country-specific lag coefficients (block-diagonal).
    n_l = cols[0].shape[1] - 1
    rows = sum(len(d) for d in dep)
    Zp = np.zeros((rows, 1 + n_l * len(cols)))
    r = 0
    for i, Z in enumerate(cols):
        Zp[r:r + len(Z), 0] = Z[:, 0]
        Zp[r:r + len(Z), 1 + i * n_l:1 + (i + 1) * n_l] = Z[:, 1:]
        r += len(Z)
    beta, _, cov = _ols(Zp, np.concatenate(dep))
    return {"group_adf": float(np.mean(ts)), "panel_adf": float(beta[0] / np.sqrt(cov[0, 0]))}


def statistics(data: dict) -> dict:
    return {**pedroni(data), **westerlund(data)}


def null_bootstrap(data: dict, reps: int, rng) -> list[dict]:
    """Panels generated under no cointegration (see module notes); statistics on each."""
    fits = {}
    for c, (y, X) in data.items():
        dy, dX = np.diff(y), np.diff(X, axis=0)
        t = np.arange(1, len(dy))
        Z = np.column_stack([np.ones(len(t)), dy[t - 1], dX[t], dX[t - 1]])
        beta, res, _ = _ols(Z, dy[t])
        fits[c] = (beta, res - res.mean(), dX)
    T = len(next(iter(fits.values()))[1])
    out = []
    for _ in range(reps):
        draw = rng.integers(0, T, T)                     # same years for every country
        sim = {}
        for c, (y, X) in data.items():
            beta, res, dX = fits[c]
            k = dX.shape[1]
            dxs = dX[1:][draw]
            dys = np.zeros(T)
            prev_dy, prev_dx = np.diff(y)[0], dX[0]
            for s in range(T):
                dys[s] = beta[0] + beta[1] * prev_dy + dxs[s] @ beta[2:2 + k] + prev_dx @ beta[2 + k:] + res[draw[s]]
                prev_dy, prev_dx = dys[s], dxs[s]
            ys = y[0] + np.concatenate([[0, np.diff(y)[0]], dys]).cumsum()[:len(y)]
            Xs = X[0] + np.vstack([np.zeros((1, k)), dX[:1], dxs]).cumsum(axis=0)[:len(y)]
            sim[c] = (ys, Xs)
        out.append(statistics(sim))
    return out


def test(panel: pd.DataFrame, regs: list[str], reps: int, seed: int) -> dict:
    data = balanced(panel, regs)
    if data is None:
        return {"regressors": regs, "testable": False}
    stat = statistics(data)
    if any(np.isnan(v) for v in stat.values()):
        return {"regressors": regs, "testable": False}
    boot = null_bootstrap(data, reps, np.random.default_rng(seed))
    pvals = {k: float((1 + sum(b[k] <= v for b in boot if not np.isnan(b[k]))) / (1 + reps)) for k, v in stat.items()}
    years = len(next(iter(data.values()))[0])
    return {"regressors": regs, "testable": True, "stats": stat, "p": pvals, "countries": len(data), "years": years}


def holm(p: dict[str, float]) -> dict[str, float]:
    items = sorted(p.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, v) in enumerate(items):
        run = max(run, min(1.0, (m - i) * v))
        out[k] = run
    return out


def bh(p: dict[str, float]) -> dict[str, float]:
    items = sorted(p.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 1.0
    for i in range(m - 1, -1, -1):
        k, v = items[i]
        run = min(run, v * m / (i + 1))
        out[k] = min(run, 1.0)
    return out


def family(candidates: list[str], required: str) -> dict[str, list[str]]:
    """All specifications that include ``required`` and any subset of the other candidates."""
    others = [c for c in candidates if c != required]
    out = {}
    for r in range(len(others) + 1):
        for combo in itertools.combinations(others, r):
            regs = [required, *combo]
            out["+".join(regs)] = regs
    return out


def family_tests(panel: pd.DataFrame, candidates: list[str], required: str, reps: int, seed: int,
                 primary: str, cache_dir=None) -> dict:
    """Every specification in the family, with Holm and BH adjustment of the primary
    statistic's p-values. Cached on a hash of the data and settings (it only changes when
    annual data do)."""
    import hashlib
    import json
    from pathlib import Path

    cols = ["log_reer"] + candidates
    key = hashlib.sha256(pd.util.hash_pandas_object(panel[cols], index=True).to_numpy().tobytes()
                         + json.dumps([candidates, required, reps, seed, primary]).encode()).hexdigest()[:16]
    if cache_dir is not None:
        f = Path(cache_dir) / f"panel_coint_{key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    specs = {name: test(panel, regs, reps, seed) for name, regs in family(candidates, required).items()}
    raw = {k: v["p"][primary] for k, v in specs.items() if v.get("testable")}
    h, b = holm(raw), bh(raw)
    for k in raw:
        specs[k]["p_holm"], specs[k]["p_bh"] = h[k], b[k]
    out = {"primary": primary, "reps": reps, "n_specs": len(specs), "n_testable": len(raw), "specs": specs,
           "n_pass_raw": int(sum(v < 0.05 for v in raw.values()))}
    if cache_dir is not None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out), encoding="utf-8")
    return out
