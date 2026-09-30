"""Composite equilibrium and error-correction term (ECT).

ECT_t = weighted average of the REER and FEER log gaps public at t
      (positive = INR weaker than the composite fair value).
Fair value_t = INR_t * exp(-ECT_t).

The corridor combines the REER point estimate with the FEER uncertainty band
(norm and elasticity); the REER gap itself carries no parameter uncertainty.

BEER is left out on purpose: its drivers are the same market variables the
short-run dynamics respond to.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def run(pit: pd.DataFrame, reer: pd.DataFrame, feer_m: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    w = cfg["composite"]
    wr, wf = w["weight_reer"], w["weight_feer"]
    out = pd.DataFrame(index=pit.index)
    out["inr_usd"] = pit["inr_usd"]
    out["log_inr"] = pit["log_inr"]
    out["gap_reer"] = reer["gap_log"]
    out["gap_feer"] = feer_m["gap_log"]
    both = out["gap_reer"].notna() & out["gap_feer"].notna()

    def blend(feer_gap):
        return np.where(both, (wr * out["gap_reer"] + wf * feer_gap) / (wr + wf), np.nan)

    out["ect"] = blend(out["gap_feer"])
    out["fair_inr"] = out["inr_usd"] * np.exp(-out["ect"])
    out["misalignment_pct"] = (np.exp(out["ect"]) - 1) * 100
    if {"gap_log_lo", "gap_log_hi"} <= set(feer_m.columns):
        out["ect_lo"] = blend(feer_m["gap_log_lo"])
        out["ect_hi"] = blend(feer_m["gap_log_hi"])
        out["fair_inr_strong"] = out["inr_usd"] * np.exp(-out["ect_hi"])   # larger gap -> stronger fair INR
        out["fair_inr_weak"] = out["inr_usd"] * np.exp(-out["ect_lo"])
    return out
