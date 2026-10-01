"""Panel REER anchor: India's equilibrium REER from a pooled cross-country model.

A single country's 20-year sample cannot pin down long-run REER elasticities
(see models/reer_anchor.py). Following the IMF EBA REER approach, the coefficients
are estimated on a panel of emerging markets, and India's equilibrium is its own
country effect plus the pooled coefficients times its fundamentals:

    log REER_ct = a_c + b' X_ct + e_ct         (annual, BIS broad real REER)

X: relative productivity = log(GDP per capita PPP / world), and optionally log terms of
trade, government consumption (% GDP) and trade openness (% GDP), all World Bank WDI,
and net foreign assets (% GDP, External Wealth of Nations).
Estimated by panel dynamic OLS (Kao & Chiang 2000; Mark & Sul 2003: country fixed
effects, levels plus leads and lags of the differenced regressors) with standard errors
clustered by country. Re-estimated whenever a new year becomes public; annual data enter
only after their publication lag.

Cointegration is checked per country on the pooled model's residuals (ADF with
Engle-Granger critical values) and combined with Fisher's method (Maddala & Wu 1999),
an approximation to formal panel cointegration tests.

Because a_c is the country's mean residual, India's gap averages zero over its sample:
the anchor measures deviations from India's own fundamentals-adjusted norm, not an
absolute over- or undervaluation. NFA is available as a regressor but is not in the
central specification: in this panel it is insignificant with the wrong sign, and adding
it breaks the panel cointegration check (see config). EWN is used as a single vintage,
so past NFA values include later revisions (the only non-point-in-time input here).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.adfvalues import mackinnonp
from statsmodels.tsa.stattools import adfuller

MS = pd.offsets.MonthBegin
EXPECTED_SIGN = {"rel_prod": "+", "log_tot": "+", "gov_cons": "+", "openness": "-", "nfa": "+"}
FOCUS = "IND"


# --------------------------------------------------------------------------- data

def annual_panel(pdata, p: dict, info: pd.Timestamp) -> pd.DataFrame:
    """Long annual panel (country, year) with only values public at month-end ``info``."""
    pub = lambda y, lag: pd.Timestamp(f"{y}-12-01") + MS(lag) <= info
    reer = pdata.reer[pdata.reer.index + MS(p["reer_lag"]) <= info]
    ann = reer.groupby(reer.index.year).agg(["mean", "count"])
    lr = np.log(ann.xs("mean", axis=1, level=1).where(ann.xs("count", axis=1, level=1) == 12))

    w = pdata.wdi
    def published(df, lag):
        return df.loc[[y for y in df.index if pub(y, lag)]]
    gdp = published(w["gdp_pc_ppp"], p["release_lag"])
    parts = {
        "log_reer": lr,
        "rel_prod": np.log(gdp[pdata.countries].div(gdp["WLD"], axis=0)),
        "log_tot": np.log(published(w["tot"], p["tot_release_lag"])[pdata.countries]),
        "gov_cons": published(w["gov_cons"], p["release_lag"])[pdata.countries],
        "openness": published(w["openness"], p["release_lag"])[pdata.countries],
    }
    if pdata.nfa is not None:
        parts["nfa"] = published(pdata.nfa, p["nfa_release_lag"])[pdata.countries]
    long = pd.concat({k: v.stack() for k, v in parts.items()}, axis=1)
    long.index.names = ["year", "country"]
    return long.swaplevel().sort_index()


# --------------------------------------------------------------------------- estimation

def estimate(panel: pd.DataFrame, regs: list[str], k: int) -> dict:
    df = panel[["log_reer"] + regs].dropna().copy()
    g = df.groupby(level="country")
    dcols = []
    for c in regs:
        d = g[c].diff()
        for j in range(-k, k + 1):
            name = f"d_{c}_{j:+d}"
            df[name] = d.groupby(level="country").shift(-j)
            dcols.append(name)
    df = df.dropna()
    df = df[df.groupby(level="country")["log_reer"].transform("size") >= 2 * k + 3]
    cols = regs + dcols
    means = df.groupby(level="country")[["log_reer"] + cols].transform("mean")
    dm = df[["log_reer"] + cols] - means
    groups = df.index.get_level_values("country")
    res = sm.OLS(dm["log_reer"], dm[cols]).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(groups)[0]})
    b = res.params[regs]
    V = res.cov_params().loc[regs, regs]
    # Country effect: mean of log REER net of the long-run part (difference terms average ~0).
    lev = df["log_reer"] - df[regs] @ b
    alpha = lev.groupby(level="country").mean()
    resid = lev - alpha.reindex(groups).to_numpy()
    return {"b": b, "V": V, "alpha": alpha, "resid": resid, "nobs": int(res.nobs),
            "n_countries": int(len(alpha)), "years": [int(df.index.get_level_values("year").min()),
                                                      int(df.index.get_level_values("year").max())],
            "t": (b / np.sqrt(np.diag(V))).to_dict()}


def bootstrap_fit(panel: pd.DataFrame, regs: list[str], k: int, draws: int, rng, focus: str = FOCUS,
                  block: int = 3) -> tuple[np.ndarray, np.ndarray] | None:
    """Country-block bootstrap of the pooled DOLS slope, and the focus country's effect.

    Countries are drawn with replacement (each keeps its whole time series, so serial and
    within-country correlation are preserved) and the slope is re-estimated by OLS on the
    within-country demeaned DOLS regressors. The focus country's effect is recomputed from
    each slope, plus a moving-block bootstrap of the mean of its own residuals. Returns
    (slope draws: draws x len(regs), focus effect draws: draws), or None.
    """
    df = panel[["log_reer"] + regs].dropna().copy()
    g = df.groupby(level="country")
    dcols = []
    for c in regs:
        d = g[c].diff()
        for j in range(-k, k + 1):
            name = f"d_{c}_{j:+d}"
            df[name] = d.groupby(level="country").shift(-j)
            dcols.append(name)
    df = df.dropna()
    df = df[df.groupby(level="country")["log_reer"].transform("size") >= 2 * k + 3]
    if focus not in df.index.get_level_values("country"):
        return None
    cols = regs + dcols
    dm = df[["log_reer"] + cols] - df.groupby(level="country")[["log_reer"] + cols].transform("mean")
    blocks = {c: (b[cols].to_numpy(), b["log_reer"].to_numpy()) for c, b in dm.groupby(level="country")}
    names = list(blocks)
    f_lev_y = df.xs(focus, level="country")["log_reer"].to_numpy()
    f_lev_x = df.xs(focus, level="country")[regs].to_numpy()
    n_f = len(f_lev_y)
    b_out, a_out = np.empty((draws, len(regs))), np.empty(draws)
    for i in range(draws):
        pick = rng.choice(len(names), len(names), replace=True)
        X = np.vstack([blocks[names[j]][0] for j in pick])
        y = np.concatenate([blocks[names[j]][1] for j in pick])
        beta = np.linalg.lstsq(X, y, rcond=None)[0][:len(regs)]
        lev = f_lev_y - f_lev_x @ beta
        res = lev - lev.mean()
        starts = rng.integers(0, max(n_f - block + 1, 1), int(np.ceil(n_f / block)))
        boot = np.concatenate([res[s:s + block] for s in starts])[:n_f]
        b_out[i], a_out[i] = beta, lev.mean() + boot.mean()
    return b_out, a_out


def panel_cointegration(resid: pd.Series, n_regs: int) -> dict:
    """Per-country ADF on pooled residuals, Engle-Granger p-values, Fisher combination."""
    pvals = {}
    for c, e in resid.groupby(level="country"):
        e = e.droplevel("country").sort_index()
        if len(e) < 10:
            continue
        stat = adfuller(e.to_numpy(), maxlag=1, autolag=None, regression="n")[0]
        pvals[c] = float(mackinnonp(stat, regression="c", N=n_regs + 1))
    p = np.clip(np.array(list(pvals.values())), 1e-12, 1)
    fisher = float(-2 * np.log(p).sum())
    return {"fisher_stat": fisher, "df": 2 * len(p), "pvalue": float(stats.chi2.sf(fisher, 2 * len(p))),
            "per_country_p": pvals, "share_rejecting_5pct": float((p < 0.05).mean()),
            "cointegrated_5pct": bool(stats.chi2.sf(fisher, 2 * len(p)) < 0.05)}


def latest_x(panel: pd.DataFrame, regs: list[str], country: str = FOCUS) -> pd.Series:
    """Most recent published value of each regressor (years may differ by variable)."""
    d = panel.loc[country, regs].sort_index()
    return pd.Series({c: d[c].dropna().iloc[-1] if d[c].notna().any() else np.nan for c in regs})


# --------------------------------------------------------------------------- run

def run(ds, pdata, cfg: dict, boot_draws: int = 0) -> tuple[pd.DataFrame, dict]:
    """``boot_draws`` > 0 also returns, in diag["gap_draws"], bootstrap draws of India's
    log gap for every month (rows months, columns draws; see bootstrap_fit)."""
    p = cfg["models"]["panel_anchor"]
    regs = p["specs"][p["central_spec"]]
    rng = np.random.default_rng(p["seed"])
    lo_p, hi_p = min(p["band_percentiles"]), max(p["band_percentiles"])
    reer_in = pdata.reer[FOCUS]

    out = pd.DataFrame(index=ds.pit.index, dtype=float,
                       columns=["reer_bis", "reer_star", "gap_log", "gap_log_lo", "gap_log_hi"])
    fit, signature, history = None, None, []
    peers = {}                                        # month -> {country: misalignment %}
    boot, gap_draws = None, {}
    brng = np.random.default_rng(p["seed"] + 1)
    for t in ds.pit.index:
        known = reer_in[reer_in.index + MS(p["reer_lag"]) <= t].dropna()
        if known.empty:
            continue
        panel = annual_panel(pdata, p, t)
        usable = panel[["log_reer"] + regs].dropna()
        sig = (len(usable), usable.index.get_level_values("year").max() if len(usable) else None)
        if sig != signature:
            signature = sig
            years = usable.index.get_level_values("year").nunique() if len(usable) else 0
            if years >= p["min_years"]:
                fit = estimate(panel, regs, p["dols_k"])
                if boot_draws:
                    boot = bootstrap_fit(panel, regs, p["dols_k"], boot_draws, brng)
                history.append({"date": t.strftime("%Y-%m"), **fit["b"].to_dict(), "nobs": fit["nobs"]})
        if fit is not None:
            peers[t] = peer_gaps(pdata, panel, fit, regs, t, p["reer_lag"])
        if fit is None or FOCUS not in fit["alpha"].index:
            continue
        x = latest_x(panel, regs)
        if x.isna().any():
            continue
        a_in = fit["alpha"][FOCUS]
        r_in = fit["resid"].xs(FOCUS, level="country")
        a_se = r_in.std(ddof=1) / np.sqrt(len(r_in))
        star = a_in + float(x @ fit["b"])
        draws = (rng.normal(a_in, a_se, p["band_draws"])
                 + rng.multivariate_normal(fit["b"].to_numpy(), fit["V"].to_numpy(), p["band_draws"],
                                           check_valid="ignore") @ x.to_numpy())
        lr = np.log(known.iloc[-1])
        out.loc[t] = [known.iloc[-1], np.exp(star), star - lr,
                      np.percentile(draws, lo_p) - lr, np.percentile(draws, hi_p) - lr]
        if boot is not None:
            gap_draws[t] = boot[1] + boot[0] @ x.to_numpy() - lr
    out["misalignment_pct"] = (np.exp(out["gap_log"]) - 1) * 100
    out["fair_inr"] = ds.pit["inr_usd"] * np.exp(-out["gap_log"])
    diag = diagnostics(pdata, cfg, ds.pit.index[-1], history)
    diag["peer_gaps"] = pd.DataFrame.from_dict(peers, orient="index").sort_index()
    if boot_draws:
        diag["gap_draws"] = pd.DataFrame.from_dict(gap_draws, orient="index").sort_index()
    return out, diag


def peer_gaps(pdata, panel: pd.DataFrame, fit: dict, regs: list[str], t: pd.Timestamp, reer_lag: int) -> dict:
    """Every panel currency's REER misalignment (%, + = undervalued) from the current pooled fit:
    its own country effect plus the pooled coefficients times its latest published fundamentals,
    against its latest published monthly REER. Each gap averages zero over the country's sample."""
    out = {}
    for c in fit["alpha"].index:
        known = pdata.reer[c][pdata.reer.index + MS(reer_lag) <= t].dropna()
        if known.empty:
            continue
        x = latest_x(panel, regs, c)
        if x.isna().any():
            continue
        star = fit["alpha"][c] + float(x @ fit["b"])
        out[c] = float((np.exp(star - np.log(known.iloc[-1])) - 1) * 100)
    return out


def diagnostics(pdata, cfg: dict, info: pd.Timestamp, history: list[dict]) -> dict:
    p = cfg["models"]["panel_anchor"]
    panel = annual_panel(pdata, p, info)
    specs = {}
    for name, regs in p["specs"].items():
        if not set(regs) <= set(panel.columns):   # e.g. NFA switched off in the config
            continue
        fit = estimate(panel, regs, p["dols_k"])
        coint = panel_cointegration(fit["resid"], len(regs))
        x = latest_x(panel, regs)
        in_hist = panel.loc[FOCUS, "log_reer"].dropna()
        star = fit["alpha"][FOCUS] + float(x @ fit["b"])
        specs[name] = {
            "regressors": regs, "coef": fit["b"].to_dict(), "t_cluster": fit["t"],
            "expected_sign": {r: EXPECTED_SIGN[r] for r in regs},
            "nobs": fit["nobs"], "n_countries": fit["n_countries"], "years": fit["years"],
            "panel_cointegration": coint,
            "india_cointegration_p": coint["per_country_p"].get(FOCUS),
            "india_latest_annual_gap_pct": float((np.exp(star - in_hist.iloc[-1]) - 1) * 100),
            "india_latest_reer_year": int(in_hist.index.max()),
        }
    formal = None
    cands = [c for c in p.get("coint_candidates", []) if c in panel.columns]
    if cands:
        from ..config import path as cfg_path
        from ..stats import panel_coint
        formal = panel_coint.family_tests(panel, cands, cands[0], p["coint_reps"], p["seed"], p["coint_primary"],
                                          cache_dir=cfg_path(cfg, "runs").parent / "cache")
        by_set = {frozenset(v["regressors"]): v for v in formal["specs"].values()}
        for s in specs.values():
            s["formal"] = by_set.get(frozenset(s["regressors"]))
    hist = pd.DataFrame(history)
    path = {}
    if len(hist):
        for r in p["specs"][p["central_spec"]]:
            path[r] = [float(hist[r].min()), float(hist[r].max())]
    return {"central_spec": p["central_spec"], "specs": specs, "coef_path": path, "formal_family": formal,
            "first_estimate": hist["date"].min() if len(hist) else None, "n_estimates": len(hist)}
