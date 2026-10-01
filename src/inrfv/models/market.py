"""Market pricing: what the rupee forward market says, next to the fair value.

The RBI's inter-bank forward premium (1, 3 and 6 months, monthly average, % a year) is
the market's rupee-dollar interest differential (covered interest parity). Three
uses:

* Implied forward rates: spot x (1 + premium x months/12), the rate at which the
  market will deliver dollars later. Under uncovered interest parity (UIP) this is
  also the expected future spot rate.
* UIP test: does the premium predict the depreciation that follows? Regress the
  realised h-month depreciation (annualised) on the h-month premium, overlapping
  monthly observations, Newey-West errors; UIP says slope 1.
* Spread over the policy-rate gap: the premium minus (India policy rate - Fed funds).
  A rising spread means dollars for future delivery cost more than the rate gap
  justifies: hedging demand and expected depreciation beyond carry. Tested as a
  predictor of next month's rupee move, controlling for the dollar.

Everything uses the point-in-time panel; the premium is market data, public as traded.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

HORIZONS = {"3m": 3, "6m": 6}


def uip(pit: pd.DataFrame, h: int, col: str, hac_lags: int) -> dict:
    lr = np.log(pit["inr_usd"])
    dep = (lr.shift(-h) - lr) * 1200 / h                     # realised depreciation, % a year
    d = pd.DataFrame({"dep": dep, "prem": pit[col]}).dropna()
    m = sm.OLS(d["dep"], sm.add_constant(d["prem"])).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    b, se = float(m.params["prem"]), float(m.bse["prem"])
    return {"h": h, "premium": col, "sample": [d.index[0].strftime("%Y-%m"), d.index[-1].strftime("%Y-%m")],
            "nobs": int(m.nobs), "slope": b, "se": se, "t_vs_0": b / se, "t_vs_1": (b - 1) / se,
            "r2": float(m.rsquared)}


def spread_test(pit: pd.DataFrame, hac_lags: int) -> dict:
    d = pd.DataFrame({"next": np.log(pit["inr_usd"]).diff().shift(-1) * 100,
                      "spread": pit["fwd_spread"], "dxy_next": np.log(pit["dxy"]).diff().shift(-1) * 100}).dropna()
    m = sm.OLS(d["next"], sm.add_constant(d[["spread"]])).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    m2 = sm.OLS(d["next"], sm.add_constant(d[["spread", "dxy_next"]])).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    return {"sample": [d.index[0].strftime("%Y-%m"), d.index[-1].strftime("%Y-%m")], "nobs": int(m.nobs),
            "coef": float(m.params["spread"]), "t": float(m.tvalues["spread"]), "p": float(m.pvalues["spread"]),
            "coef_given_dxy": float(m2.params["spread"]), "t_given_dxy": float(m2.tvalues["spread"])}


def run(pit: pd.DataFrame, panel: pd.DataFrame, cfg: dict) -> dict | None:
    """``pit`` carries a missing month forward; ``panel`` (by reference month) says when a
    premium was actually observed, so the report labels it honestly."""
    if "fwd_premium_3m" not in pit or pit["fwd_premium_3m"].dropna().empty:
        return None
    p = cfg["models"].get("market", {})
    lags = p.get("hac_lags", 6)
    spot, asof = float(pit["inr_usd"].dropna().iloc[-1]), pit["inr_usd"].last_valid_index()
    latest = {}
    for k, months in HORIZONS.items():
        s = panel[f"fwd_premium_{k}"].loc[:asof].dropna()
        latest[k] = {"premium": float(s.iloc[-1]), "month": s.index[-1].strftime("%Y-%m"),
                     "forward": spot * (1 + float(s.iloc[-1]) * months / 1200)}
    sp = pit["fwd_spread"].dropna()
    sp = sp.loc[: panel["fwd_premium_3m"].last_valid_index()]       # last month with an observed premium
    hist = sp
    return {
        "spot": spot, "asof": asof.strftime("%Y-%m"), "forwards": latest,
        "spread": {"value": float(sp.iloc[-1]), "month": sp.index[-1].strftime("%Y-%m"),
                   "percentile": float((hist <= sp.iloc[-1]).mean() * 100),
                   "mean": float(hist.mean()), "sd": float(hist.std())},
        "uip": {k: uip(pit, m, f"fwd_premium_{k}", lags) for k, m in HORIZONS.items()},
        "spread_test": spread_test(pit, lags),
    }
