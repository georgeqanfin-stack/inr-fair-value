"""Composite equilibrium and error-correction term (ECT).

ECT_t = weighted average of the REER and FEER log gaps public at t
      (positive = INR weaker than the composite fair value).
Fair value_t = INR_t * exp(-ECT_t).

BEER is left out on purpose: its drivers are the same market variables the
short-run dynamics respond to.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def run(pit: pd.DataFrame, reer: pd.DataFrame, feer_m: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    w = cfg["composite"]
    out = pd.DataFrame(index=pit.index)
    out["inr_usd"] = pit["inr_usd"]
    out["log_inr"] = pit["log_inr"]
    out["gap_reer"] = reer["gap_log"]
    out["gap_feer"] = feer_m["gap_log"]
    both = out["gap_reer"].notna() & out["gap_feer"].notna()
    out["ect"] = np.where(both, (w["weight_reer"] * out["gap_reer"] + w["weight_feer"] * out["gap_feer"])
                          / (w["weight_reer"] + w["weight_feer"]), np.nan)
    out["fair_inr"] = out["inr_usd"] * np.exp(-out["ect"])
    out["misalignment_pct"] = (np.exp(out["ect"]) - 1) * 100
    return out
