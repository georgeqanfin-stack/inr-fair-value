"""Identifying the effect of portfolio flows on the rupee.

The flow attribution (flows.py) regresses the monthly INR/USD change on same-month net
FPI flows: about -0.13% per US$1 bn of inflow. Flows and the rupee feed each other
(lead-lag tests run both ways), so that is an association. No clean, free instrument
exists (EM-wide fund-flow data are proprietary), so the effect is bounded from several
angles, monthly, 2011 onward (RBI's BoP basis for FPI):

* Recursive identification, two orderings (Sims 1980; Plagborg-Moller & Wolf 2021 for
  the local-projection form). The FPI shock is the part of FPI not explained by its
  own and the other variables' lags and by the variables ordered before it:
  - A, global -> FPI -> INR: the rupee cannot move FPI within the month, so the
    same-month co-movement is attributed to flows (upper bound on the impact);
  - B, global -> INR -> FPI: FPI cannot move the rupee within the month, so the
    impact is zero by construction (lower bound); later horizons are informative.
  Global block: changes in VIX, the US 10-year yield and the dollar index.
* Instrumental variables (2SLS): FPI instrumented with "global push" shocks (changes in
  VIX and the US 10-year yield), controlling for the dollar, oil and FDI. Exclusion
  requires the push shocks to move the rupee only through portfolio flows, a strong
  assumption; first-stage F and Hansen's J are reported.
* Local projections (Jorda 2005): the cumulative rupee change from month t to t+h on
  the identified FPI shock (ordering A), h = 0..H, Newey-West errors with h+1 lags.

Signs follow the attribution: per US$1 bn of net inflow, % change of INR/USD
(negative = rupee stronger).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

GLOBAL = ["vix", "us10y", "dxy"]


def frame(panel: pd.DataFrame, start: str | None) -> pd.DataFrame:
    x = pd.DataFrame({
        "inr": np.log(panel["inr_usd"]).diff() * 100,
        "fpi": panel["fpi_usd_mn"] / 1000,
        "fdi": panel["fdi_usd_mn"] / 1000,
        "dxy": np.log(panel["dxy"]).diff() * 100,
        "brent": np.log(panel["brent"]).diff() * 100,
        "vix": panel["vix"].diff(),
        "us10y": panel["us_10y_yield"].diff(),
    })
    if start:
        x = x.loc[start:]
    return x.dropna()


def _lags(x: pd.DataFrame, cols: list[str], p: int) -> pd.DataFrame:
    return pd.concat({f"{c}_l{k}": x[c].shift(k) for c in cols for k in range(1, p + 1)}, axis=1)


def fpi_shock(x: pd.DataFrame, before: list[str], p: int) -> pd.Series:
    """Residual of FPI on same-month ``before`` variables and p lags of every variable."""
    X = pd.concat([x[before], _lags(x, ["inr", "fpi", "fdi"] + GLOBAL + ["brent"], p)], axis=1)
    d = pd.concat([x["fpi"], X], axis=1).dropna()
    res = sm.OLS(d["fpi"], sm.add_constant(d.drop(columns="fpi"))).fit()
    return res.resid.rename("shock")


def local_projection(x: pd.DataFrame, shock: pd.Series, horizons: int, p: int, contemporaneous: list[str]) -> list[dict]:
    out = []
    ctrl = pd.concat([x[contemporaneous], _lags(x, ["inr", "fpi"] + GLOBAL, p)], axis=1)
    for h in range(horizons + 1):
        y = sum(x["inr"].shift(-j) for j in range(h + 1)).rename("y")        # cumulative change t..t+h
        d = pd.concat([y, shock, ctrl], axis=1).dropna()
        m = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": h + 1})
        out.append({"h": h, "beta": float(m.params["shock"]), "se": float(m.bse["shock"]),
                    "t": float(m.tvalues["shock"]), "n": int(m.nobs)})
    return out


def two_sls(x: pd.DataFrame, instruments: list[str], controls: list[str], p: int) -> dict:
    """2SLS of the INR change on FPI with HAC errors; first-stage F and Hansen J."""
    ctrl = pd.concat([x[controls], _lags(x, ["inr", "fpi"], p)], axis=1)
    d = pd.concat([x[["inr", "fpi"]], x[instruments], ctrl], axis=1).dropna()
    W = sm.add_constant(d[list(ctrl.columns)])
    Z = pd.concat([W, d[instruments]], axis=1)
    fs = sm.OLS(d["fpi"], Z).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    F = float(fs.f_test(" = 0, ".join(instruments) + " = 0").fvalue)
    fpi_hat = fs.fittedvalues.rename("fpi")
    ss = sm.OLS(d["inr"], pd.concat([W, fpi_hat], axis=1)).fit()
    beta = float(ss.params["fpi"])
    # Correct 2SLS residuals use actual FPI; HAC variance via the projection formula.
    X = pd.concat([W, d["fpi"]], axis=1).to_numpy()
    Xh = pd.concat([W, fpi_hat], axis=1).to_numpy()
    u = d["inr"].to_numpy() - X @ ss.params.to_numpy()
    n, k = Xh.shape
    S = _nw(Xh * u[:, None], 3)
    A = np.linalg.inv(Xh.T @ Xh)
    V = A @ S @ A * n
    se = float(np.sqrt(V[-1, -1]))
    # Hansen J: regress 2SLS residuals on all instruments.
    Zm = Z.to_numpy()
    g = Zm * u[:, None]
    Sg = _nw(g, 3)
    gbar = g.mean(axis=0)
    J = float(n * gbar @ np.linalg.pinv(Sg) @ gbar)
    from scipy import stats
    dfj = len(instruments) - 1
    return {"beta": beta, "se": se, "t": beta / se, "first_stage_F": F, "n": int(n),
            "hansen_J": J, "J_p": float(stats.chi2.sf(J, dfj)) if dfj > 0 else None,
            "first_stage": {k_: float(fs.params[k_]) for k_ in instruments}}


def _nw(g: np.ndarray, lags: int) -> np.ndarray:
    g = g - g.mean(axis=0)
    n = len(g)
    S = g.T @ g / n
    for k in range(1, lags + 1):
        G = g[k:].T @ g[:-k] / n
        S += (1 - k / (lags + 1)) * (G + G.T)
    return S


def run(panel: pd.DataFrame, cfg: dict, ols_beta: float | None) -> dict:
    p = cfg["models"]["flow_id"]
    x = frame(panel, p["start"])
    lags, H = p["lags"], p["horizons"]
    shock_a = fpi_shock(x, GLOBAL, lags)                           # global -> FPI -> INR
    shock_b = fpi_shock(x, GLOBAL + ["inr"], lags)                  # global -> INR -> FPI
    sd = float(x["fpi"].std())
    lp_a = local_projection(x, shock_a, H, lags, GLOBAL + ["brent"])
    lp_b = local_projection(x, shock_b, H, lags, GLOBAL + ["brent"])
    # Under ordering B the shock is orthogonal to the same-month rupee change: impact zero.
    lp_b[0] = {**lp_b[0], "beta": 0.0, "se": 0.0, "t": float("nan"), "note": "zero by construction"}
    iv = two_sls(x, p["instruments"], ["dxy", "brent", "fdi"], lags)
    a0 = lp_a[0]["beta"]
    return {"sample": [x.index[0].strftime("%Y-%m"), x.index[-1].strftime("%Y-%m")], "n": int(len(x)),
            "fpi_sd_bn": sd, "ols_beta": ols_beta, "ordering_a": lp_a, "ordering_b": lp_b, "iv": iv,
            "impact_bounds": [min(0.0, a0), max(0.0, a0)],
            "settings": {"lags": lags, "horizons": H, "instruments": p["instruments"]}}
