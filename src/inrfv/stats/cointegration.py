"""Cointegration tests with the correct critical values.

* Engle-Granger: ADF on OLS residuals must use MacKinnon (2010) critical values
  for the number of variables, not the ordinary ADF table (the legacy BEER
  reported p=0.013; the correct p-value is far larger).
* Johansen: rank is chosen sequentially - the first r whose trace test fails
  to reject - rather than by counting every rejection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.var_model import VAR
from statsmodels.tsa.vector_ar.vecm import coint_johansen


def engle_granger(y: pd.Series, X: pd.DataFrame, trend: str = "c") -> dict:
    d = pd.concat([y, X], axis=1).dropna()
    stat, p, crit = coint(d.iloc[:, 0], d.iloc[:, 1:], trend=trend, autolag="aic")
    return {"stat": float(stat), "pvalue": float(p), "n_vars": d.shape[1], "nobs": len(d),
            "crit_1pct": float(crit[0]), "crit_5pct": float(crit[1]), "crit_10pct": float(crit[2]),
            "cointegrated_5pct": bool(p < 0.05)}


def johansen_rank(data: pd.DataFrame, det_order: int = 0, maxlags: int = 12,
                  signif: int = 1) -> dict:
    """signif: column of the critical-value table (0=10%, 1=5%, 2=1%)."""
    d = data.dropna()
    sel = VAR(d.to_numpy()).select_order(maxlags=maxlags)
    k_ar_diff = max(int(sel.bic) - 1, 1) if sel.bic else 1   # VAR lags in levels -> lags in differences
    res = coint_johansen(d, det_order=det_order, k_ar_diff=k_ar_diff)
    k = d.shape[1]
    rank = k
    for i in range(k):
        if res.lr1[i] < res.cvt[i, signif]:
            rank = i
            break
    return {"rank": int(rank), "n_vars": k, "k_ar_diff": k_ar_diff, "nobs": len(d),
            "trace": [float(x) for x in res.lr1],
            "crit": [float(x) for x in res.cvt[:, signif]],
            "note": "rank == n_vars means the system is stationary in levels, not cointegrated"}
