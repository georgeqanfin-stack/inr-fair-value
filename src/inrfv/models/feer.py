"""FEER: exchange rate consistent with a sustainable current account.

Per quarter, using only information public when that quarter's BoP is released:
  underlying CAD = CAD/GDP - oil_elasticity * (log Brent_q - log Brent_norm)
  misalignment%  = -(underlying CAD - norm) / reer_semi_elasticity

* Brent norm: median of monthly Brent public at release (legacy: full-sample median).
* Oil elasticity: OLS of CAD/GDP on log Brent over quarters already released
  (legacy: estimated on the full sample, then "locked").
* REER semi-elasticity: an external assumption from config, with a sensitivity table.

The conditional (financing-adjusted) norm is kept for continuity but is ad hoc:
it moves with each quarter's FDI and loans, so it is reported, not used in the composite.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def _oil_elasticity(q: pd.DataFrame, upto: pd.Timestamp, min_q: int) -> float:
    d = q[q["available"] <= upto][["current_account_pct_gdp", "brent_q"]].dropna()
    if len(d) < min_q:
        return np.nan
    X = sm.add_constant(np.log(d["brent_q"]))
    return float(sm.OLS(d["current_account_pct_gdp"], X).fit().params.iloc[1])


def run(bop: pd.DataFrame, pit: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = cfg["models"]["feer"]
    q = bop.copy()
    q.index.name = "quarter"
    brent_m = pit["brent"]

    norms, elast = [], []
    for _, row in q.iterrows():
        avail = row["available"]
        norms.append(float(brent_m[brent_m.index <= avail].median()))
        if isinstance(p["oil_elasticity"], (int, float)):
            elast.append(float(p["oil_elasticity"]))
        else:
            elast.append(_oil_elasticity(q, avail, p["oil_min_quarters"]))
    q["brent_norm"] = norms
    q["oil_elasticity"] = elast
    q["oil_drag"] = q["oil_elasticity"] * (np.log(q["brent_q"]) - np.log(q["brent_norm"]))
    q["cad_underlying"] = q["current_account_pct_gdp"] - q["oil_drag"]

    semi = p["reer_semi_elasticity"]
    q["misalignment_pct"] = -(q["cad_underlying"] - p["cad_norm"]) / semi
    q["fair_inr_q"] = q["inr_q"] / (1 + q["misalignment_pct"] / 100)
    for s in p["semi_sensitivity"]:
        q[f"misalignment_pct_semi_{s}"] = -(q["cad_underlying"] - p["cad_norm"]) / s

    stable = q["fdi_bop"] + q["loans"]
    q["stable_financing_pct_gdp"] = stable * 4 / q["gdp_usd_mn"] * 100
    q["cad_norm_conditional"] = np.where(stable > 0, -q["stable_financing_pct_gdp"], 0.0)
    q["misalignment_pct_conditional"] = -(q["cad_underlying"] - q["cad_norm_conditional"]) / semi

    # Monthly view: the latest quarter public at each month-end.
    rel = q.dropna(subset=["misalignment_pct"]).reset_index().set_index("available").sort_index()
    rel = rel[~rel.index.duplicated(keep="last")]
    monthly = rel[["quarter", "misalignment_pct", "misalignment_pct_conditional"]] \
        .reindex(pit.index, method="ffill")
    monthly["gap_log"] = np.log1p(monthly["misalignment_pct"] / 100)
    monthly["fair_inr"] = pit["inr_usd"] * np.exp(-monthly["gap_log"])
    return q, monthly
