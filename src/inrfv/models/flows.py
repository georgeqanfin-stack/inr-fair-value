"""Flow attribution: what moved USD/INR month to month.

The fair-value models say where the rupee should be; this module asks what moved the
spot rate. A monthly regression, by reference month, of the USD/INR log change on
net portfolio (FPI) and direct investment (FDI) flows and on the global drivers:

    100 * dlog USD/INR_t = c + b_fpi FPI_t + b_fdi FDI_t + b_dxy 100 dlog DXY_t
                             + b_oil 100 dlog Brent_t + e_t

with flows in US$ bn (positive = inflow) and Newey-West standard errors. Each month's
move is split into contributions b_k x_kt, the constant ("drift": India's average
trend depreciation) and a residual. Windows of the latest months are summed.

This is an ex-post decomposition, not a forecast: it uses each month's own flows, which
RBI publishes about two months later, and it is not point-in-time. Two checks keep it
honest:

* Out-of-window fit: the coefficients are re-estimated without the months being
  explained, so the attribution does not rest on those months' own data.
* RBI intervention cannot be a regressor: the RBI sells dollars because the rupee is
  under pressure, so a regression of the rupee on intervention finds roughly nothing
  (simultaneity). Instead the module estimates the RBI's reaction function and values
  its net dollar sales at the market's price of a dollar, the FPI coefficient: a dollar
  the RBI sells is supplied to the same market as a dollar a foreign investor brings
  in. That gives the move the rupee would have made without the RBI (exchange market
  pressure) and the share the RBI absorbed. Because the FPI coefficient is itself
  estimated net of the RBI's usual response, the absorbed share is a lower bound.
  Intervention = spot net purchases + change in the outstanding forward book (RBI
  Bulletin Table 4), so forward sales count when made and swap legs cancel.
* Direction: flows and the rupee feed each other (foreign investors sell a falling
  currency). Lead-lag regressions test whether FPI this month predicts next month's INR
  move and whether last month's INR move predicts this month's FPI. Significance in
  both directions means the contemporaneous coefficient is association, not causation.
"""

from __future__ import annotations

from typing import Any

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
    out: dict[str, Any] = {"fpi_predicts_next_inr": {"coef": float(lead.params["fpi"]), "t": float(lead.tvalues["fpi"]),
                                     "p": float(lead.pvalues["fpi"])},
           "inr_predicts_next_fpi": {"coef": float(rev.params["inr_lag"]), "t": float(rev.tvalues["inr_lag"]),
                                     "p": float(rev.pvalues["inr_lag"])}}
    both = out["fpi_predicts_next_inr"]["p"] < 0.05 and out["inr_predicts_next_fpi"]["p"] < 0.05
    out["reading"] = ("two-way: flows and the rupee feed each other, so contributions are associations"
                      if both else "one-way or none at the 5% level")
    return out


def intervention(panel: pd.DataFrame, x: pd.DataFrame, res, contrib: pd.DataFrame, windows: list[int],
                 hac_lags: int, price: float | None = None) -> tuple[dict, pd.DataFrame] | None:
    """RBI reaction function, absorbed pressure and the forward book (see module notes)."""
    if "rbi_intervention_usd_mn" not in panel or panel["rbi_intervention_usd_mn"].dropna().empty:
        return None
    rbi = (panel["rbi_intervention_usd_mn"] / 1000).rename("rbi")
    d = x.join(rbi, how="inner").dropna()
    react = sm.OLS(d["rbi"], sm.add_constant(d[["inr", "fpi"]])).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    regs = [c for c in res.params.index if c != "const"]
    naive = sm.OLS(d["inr"], sm.add_constant(d[regs + ["rbi"]])).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    rho = price if price is not None else -float(res.params["fpi"])      # % rupee move per US$1bn supplied
    m = contrib.join(rbi, how="left")
    m["rbi_effect"] = rho * m["rbi"]            # purchases (+) weaken the rupee, sales (-) strengthen it
    m["pressure"] = m["actual"] - m["rbi_effect"]
    wins = {}
    for k in windows:
        w = m.iloc[-k:]
        sold = -float(w["rbi"].sum())
        absorbed = -float(w["rbi_effect"].sum())
        pressure = float(w["pressure"].sum())
        wins[str(k)] = {"start": w.index[0].strftime("%Y-%m"), "end": w.index[-1].strftime("%Y-%m"),
                        "net_sold_bn": sold, "actual": float(w["actual"].sum()), "absorbed": absorbed,
                        "pressure": pressure,
                        "absorbed_share": absorbed / pressure if pressure > 0 and absorbed > 0 else None}
    book = panel["rbi_fwd_book_usd_mn"].dropna()
    res_ = panel["fx_reserves_usd_mn"].reindex(book.index).ffill()
    return {
        "price_pct_per_bn": rho, "price_source": "override" if price is not None else "FPI coefficient",
        "reaction": {"coef": {k: float(v) for k, v in react.params.items()},
                     "t": {k: float(v) for k, v in react.tvalues.items()}, "r2": float(react.rsquared),
                     "nobs": int(react.nobs)},
        "naive_coef": float(naive.params["rbi"]), "naive_t": float(naive.tvalues["rbi"]),
        "windows": wins,
        "fwd_book_bn": float(book.iloc[-1] / 1000), "fwd_book_month": book.index[-1].strftime("%Y-%m"),
        "fwd_book_pct_reserves": float(book.iloc[-1] / res_.iloc[-1] * 100) if pd.notna(res_.iloc[-1]) else None,
        "latest_month": panel["rbi_intervention_usd_mn"].last_valid_index().strftime("%Y-%m"),
        "latest_bn": float(panel["rbi_intervention_usd_mn"].dropna().iloc[-1] / 1000),
    }, m[["rbi", "rbi_effect", "pressure"]]


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
        "rbi": None,
        "units": "USD/INR % change (log x 100; positive = rupee weaker); flows in US$ bn, positive = inflow",
    }
    iv = intervention(panel, x, res, contrib, p["windows"], lags, p.get("dollar_price"))
    if iv is not None:
        diag["rbi"], monthly = iv
        contrib = contrib.join(monthly)
    return contrib, diag
