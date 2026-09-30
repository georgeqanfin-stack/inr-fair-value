"""REER structural anchor.

The trend is a *one-sided* (recursive) HP filter: the value at month t is the
end-point of an HP filter run on REER data public at t. The legacy notebooks used
a two-sided filter over the full sample, which lets future REER values shape
historical fair values.

Note: an HP trend misalignment is mean-reverting by construction and cannot flag
a persistent over- or undervaluation. It is a cyclical gauge, not a structural
equilibrium; Phase 2 replaces it with a fundamentals-based anchor.

Sign convention (all models): positive misalignment = INR undervalued (weaker than fair).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.filters.hp_filter import hpfilter


def one_sided_hp(s: pd.Series, lamb: float, min_obs: int) -> pd.Series:
    vals = s.dropna()
    out = pd.Series(np.nan, index=s.index, name="trend")
    for i in range(min_obs - 1, len(vals)):
        _, trend = hpfilter(vals.iloc[: i + 1].to_numpy(), lamb=lamb)
        out[vals.index[i]] = trend[-1]
    return out


def two_sided_hp(s: pd.Series, lamb: float) -> pd.Series:
    vals = s.dropna()
    _, trend = hpfilter(vals.to_numpy(), lamb=lamb)
    return pd.Series(trend, index=vals.index).reindex(s.index)


def run(pit: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    p = cfg["models"]["structural"]
    reer = pit["reer"]
    trend = one_sided_hp(reer, p["hp_lambda"], p["min_obs"])
    out = pd.DataFrame(index=pit.index)
    out["reer"] = reer
    out["reer_trend"] = trend
    out["gap_log"] = np.log(trend) - np.log(reer)            # >0: REER below trend -> INR undervalued
    out["misalignment_pct"] = (trend / reer - 1) * 100
    out["fair_inr"] = pit["inr_usd"] * np.exp(-out["gap_log"])
    out["reer_trend_expost"] = two_sided_hp(reer, p["hp_lambda"])   # reference only, never used downstream
    return out
