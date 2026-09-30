import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller

from inrfv.stats.cointegration import engle_granger, johansen_rank
from inrfv.stats.forecast_eval import clark_west, diebold_mariano, hodrick_1b, newey_west_var_of_mean, oos_r2


def test_newey_west_zero_lags_is_iid_variance(rng):
    x = rng.normal(size=500)
    assert newey_west_var_of_mean(x, 0) == pytest.approx(x.var() / 500)


def test_clark_west_detects_real_signal(rng):
    n = 400
    x = rng.normal(size=n)
    y = 0.5 * x + rng.normal(size=n)
    cw = clark_west(y, np.zeros(n), 0.5 * x, h=1)
    assert cw["pvalue_one_sided"] < 0.01
    noise = clark_west(y, np.zeros(n), 0.5 * rng.normal(size=n), h=1)
    assert noise["pvalue_one_sided"] > 0.05


def test_dm_sign_and_oos_r2(rng):
    n = 300
    y = rng.normal(size=n)
    good, bad = y + rng.normal(scale=0.1, size=n), y + rng.normal(scale=2.0, size=n)
    assert diebold_mariano(y, bad, good, h=1)["stat"] > 0
    assert oos_r2(y, bad, good) > 0.9


def test_hodrick_beta_matches_ols_and_is_unbiased_under_null(rng):
    n = 360
    p = pd.Series(np.cumsum(rng.normal(0.003, 0.02, n)))
    x = pd.Series(rng.normal(size=n)).rolling(6, min_periods=1).mean()
    res = hodrick_1b(p, x, 12)
    y = (p.shift(-12) - p).dropna()
    b = np.polyfit(x.loc[y.index], y, 1)[0]
    assert res["beta"] == pytest.approx(b)
    assert res["pvalue"] > 0.01          # no predictability by construction


def test_engle_granger_uses_multivariate_critical_values(rng):
    n = 300
    X = pd.DataFrame(np.cumsum(rng.normal(size=(n, 3)), axis=0), columns=list("abc"))
    y_coint = X @ [1.0, -0.5, 0.2] + rng.normal(scale=0.5, size=n)
    y_spur = pd.Series(np.cumsum(rng.normal(size=n)))
    assert engle_granger(pd.Series(y_coint), X)["cointegrated_5pct"]
    r = engle_granger(y_spur, X)
    assert r["crit_5pct"] < -4.0          # 4-variable EG critical value, not the ADF -2.87
    # The legacy mistake: ordinary ADF p-values on OLS residuals are far too small.
    resid = sm.OLS(y_spur, sm.add_constant(X)).fit().resid
    assert r["pvalue"] > adfuller(resid, autolag="AIC")[1]


def test_johansen_sequential_rank(rng):
    n = 400
    common = np.cumsum(rng.normal(size=n))
    d = pd.DataFrame({"a": common + rng.normal(scale=0.3, size=n),
                      "b": 0.5 * common + rng.normal(scale=0.3, size=n),
                      "c": np.cumsum(rng.normal(size=n))})
    assert johansen_rank(d)["rank"] == 1
