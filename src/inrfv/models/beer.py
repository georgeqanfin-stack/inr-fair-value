"""BEER: log(INR/USD) regressed on market fundamentals.

The fair value at month t comes from a regression estimated only on data public
at t (expanding window). The legacy version used full-sample in-sample fitted
values, so every historical fair value "knew" the future coefficients.

The full-sample regression is kept as a diagnostic, with an Engle-Granger
cointegration test using the correct critical values. If the residual is not
cointegrated, the levels regression may be spurious and the BEER should be read
as a descriptive gauge only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from ..stats.cointegration import engle_granger


def run(pit: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    p = cfg["models"]["beer"]
    regs = p["regressors"]
    d = pit[["log_inr"] + regs].dropna()

    fitted = pd.Series(np.nan, index=pit.index)
    y_all, X_all = d["log_inr"].to_numpy(), sm.add_constant(d[regs]).to_numpy()
    for i in range(p["min_obs"] - 1, len(d)):
        b = np.linalg.lstsq(X_all[: i + 1], y_all[: i + 1], rcond=None)[0]
        fitted[d.index[i]] = X_all[i] @ b

    out = pd.DataFrame(index=pit.index)
    out["fair_inr"] = np.exp(fitted)
    out["gap_log"] = pit["log_inr"] - fitted
    out["misalignment_pct"] = (pit["inr_usd"] / out["fair_inr"] - 1) * 100

    full = sm.OLS(d["log_inr"], sm.add_constant(d[regs])).fit(cov_type="HAC", cov_kwds={"maxlags": 12})
    diag = {
        "sample": [d.index[0].strftime("%Y-%m"), d.index[-1].strftime("%Y-%m")],
        "nobs": int(full.nobs),
        "r2": float(full.rsquared),
        "coef": {k: float(v) for k, v in full.params.items()},
        "pvalues_hac": {k: float(v) for k, v in full.pvalues.items()},
        "engle_granger": engle_granger(d["log_inr"], d[regs]),
    }
    return out, diag
