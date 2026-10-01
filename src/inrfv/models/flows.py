"""Flow attribution: what moved INR/USD month to month.

The fair-value models say where the rupee should be; this module asks what moved the
spot rate. A monthly regression, by reference month, of the INR/USD log change on
net portfolio (FPI) and direct investment (FDI) flows and on the global drivers:

    100 * dlog INR/USD_t = c + b_fpi FPI_t + b_fdi FDI_t + b_dxy 100 dlog DXY_t
                             + b_oil 100 dlog Brent_t + e_t

with flows in US$ bn (positive = inflow) and Newey-West standard errors. Each month's
move is split into contributions b_k x_kt, the constant ("drift": India's average
trend depreciation) and a residual. Windows of the latest months are summed.

This is an ex-post decomposition, not a forecast: it uses each month's own flows, which
RBI publishes about two months later, and it is not point-in-time. Two checks keep it
honest:

* Out-of-window fit: the coefficients are re-estimated without the months being
  explained, so the attribution does not rest on those months' own data.
* Direction: flows and the rupee feed each other (foreign investors sell a falling
  currency). Lead-lag regressions test whether FPI this month predicts next month's INR
  move and whether last month's INR move predicts this month's FPI. Significance in
  both directions means the contemporaneous coefficient is association, not causation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

LABELS = {"fpi": "Portfolio flows (FPI)", "fdi": "Direct investment (FDI)",
          "dxy": "Dollar index", "brent": "Oil (Brent)"}


def frame(panel: pd.DataFrame, start: str | None = None) -> pd.DataFrame:
    """Monthly changes and flows, by reference month (rows with any gap dropped)."""
    x = pd.DataFrame({
        "inr": np.log(panel["inr_usd"]).diff() * 100,
        "fpi": panel["fpi_usd_mn"] / 1000,
        "fdi": panel["fdi_usd_mn"] / 1000,
        "dxy": np.log(panel["dxy"]).diff() * 100,
        "brent": np.log(panel["brent"]).diff() * 100,
    })
    if start:
        x = x.loc[start:]
    return x.dropna()


def fit(x: pd.DataFrame, regs: list[str], hac_lags: int):
    return sm.OLS(x["inr"], sm.add_constant(x[regs], has_constant="add")).fit(
        cov_type="HAC", cov_kwds={"maxlags": hac_lags})


def contributions(x: pd.DataFrame, res, regs: list[str]) -> pd.DataFrame:
    out = x[regs].mul(res.params[regs])
    out["drift"] = res.params["const"]
    out["residual"] = x["inr"] - out.sum(axis=1)
    out["actual"] = x["inr"]
    return out


def window(contrib: pd.DataFrame, months: int) -> dict:
    w = contrib.iloc[-months:]
    return {"start": w.index[0].strftime("%Y-%m"), "end": w.index[-1].strftime("%Y-%m"), "months": months,
            **{k: float(v) for k, v in w.sum().items()}}


def direction_tests(x: pd.DataFrame, hac_lags: int) -> dict:
    lead = sm.OLS(x["inr"].shift(-1), sm.add_constant(x[["fpi", "dxy"]]), missing="drop").fit(
        cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    rev = sm.OLS(x["fpi"], sm.add_constant(pd.DataFrame({"inr_lag": x["inr"].shift(1), "dxy": x["dxy"]})),
                 missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    out = {"fpi_predicts_next_inr": {"coef": float(lead.params["fpi"]), "t": float(lead.tvalues["fpi"]),
                                     "p": float(lead.pvalues["fpi"])},
           "inr_predicts_next_fpi": {"coef": float(rev.params["inr_lag"]), "t": float(rev.tvalues["inr_lag"]),
                                     "p": float(rev.pvalues["inr_lag"])}}
    both = out["fpi_predicts_next_inr"]["p"] < 0.05 and out["inr_predicts_next_fpi"]["p"] < 0.05
    out["reading"] = ("two-way: flows and the rupee feed each other, so contributions are associations"
                      if both else "one-way or none at the 5% level")
    return out


def run(panel: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    p = cfg["models"]["flows"]
    regs, lags = p["regressors"], p["hac_lags"]
    x = frame(panel, p.get("start"))
    res = fit(x, regs, lags)
    contrib = contributions(x, res, regs)

    windows = {}
    for m in p["windows"]:
        w = window(contrib, m)
        pre = fit(x.iloc[:-m], regs, lags)          # coefficients that never saw the window
        w["out_of_window"] = window(contributions(x, pre, regs), m)
        windows[str(m)] = w

    diag = {
        "sample": [x.index[0].strftime("%Y-%m"), x.index[-1].strftime("%Y-%m")], "nobs": int(res.nobs),
        "r2": float(res.rsquared), "regressors": regs,
        "coef": {k: float(res.params[k]) for k in ["const"] + regs},
        "t": {k: float(res.tvalues[k]) for k in ["const"] + regs},
        "p": {k: float(res.pvalues[k]) for k in ["const"] + regs},
        "windows": windows, "direction": direction_tests(x, lags),
        "latest_flows_month": x.index[-1].strftime("%Y-%m"),
        "units": "INR/USD % change (log x 100; positive = rupee weaker); flows in US$ bn, positive = inflow",
    }
    return contrib, diag
