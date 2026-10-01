"""Joint uncertainty: one bootstrap corridor for the composite, and how well it covers.

The headline corridor in models/composite.py joins the panel anchor's and the FEER's
10th-90th percentile bands end to end. This module draws all sources together instead,
month by month and point in time:

* REER component (panel anchor): country-block bootstrap of the pooled slope and India's
  country effect (panel_anchor.bootstrap_fit), re-run at every re-estimation;
* FEER: the IMF norm (normal, its published standard error), the trade elasticities
  (uniform, +/- eta_uncertainty) and current-account measurement error (normal,
  ca_measurement_sd, % of GDP);
* model weights: each draw takes the REER weight of one of the tested combination
  schemes for that month (equal, performance, inverse variance; models/weights.py).

Draws are combined one to one into composite log gaps; the corridor is their 10th-90th
percentiles.

Coverage. A corridor is useful if the fair value as later re-estimated falls inside it.
For each month of the years the IMF has assessed, an ex-post fair value is built with
information that arrived later: the panel coefficients and India's effect as finally
estimated, and the FEER with the IMF's own norm for that year (EBA table published the
year after) applied to the current account of the quarter containing the month. The
share of months whose ex-post gap lies inside each real-time corridor is compared with
the nominal 80%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import path


def feer_draws(q: pd.DataFrame, p: dict, u: dict, n: int, rng) -> np.ndarray:
    """Quarter x draws matrix of FEER log gaps."""
    norm = q["norm_central"].to_numpy()[:, None] + q["norm_central_se"].to_numpy(dtype=float)[:, None] * rng.normal(0, 1, n)
    unc = p["eta_uncertainty"]
    ex, im = q["exports_pct_gdp"].to_numpy()[:, None], q["imports_pct_gdp"].to_numpy()[:, None]
    semi = -(p["eta_exports"] * rng.uniform(1 - unc, 1 + unc, n) * ex
             + p["eta_imports"] * rng.uniform(1 - unc, 1 + unc, n) * im) / 100
    fallback = q["semi_elasticity"].to_numpy()[:, None] * rng.uniform(1 - unc, 1 + unc, n)
    semi = np.where(np.isnan(semi), fallback, semi)
    cad = q["cad_underlying"].to_numpy()[:, None] + u["ca_measurement_sd"] * rng.normal(0, 1, n)
    return np.log1p(-(cad - norm) / semi / 100)


def monthly_rows(q: pd.DataFrame, months: pd.DatetimeIndex) -> pd.Series:
    """Row number in ``q`` of the latest quarter public at each month (as feer.run)."""
    rel = q.reset_index()[["available"]].assign(row=np.arange(len(q)))
    rel = rel[q["misalignment_pct"].notna().to_numpy()].set_index("available").sort_index()
    rel = rel[~rel.index.duplicated(keep="last")]
    return rel["row"].reindex(months, method="ffill")


def corridor(comp: pd.DataFrame, gap_draws: pd.DataFrame, q: pd.DataFrame, weights: dict[str, pd.Series],
             cfg: dict) -> tuple[pd.DataFrame, np.ndarray]:
    u = cfg["uncertainty"]
    rng = np.random.default_rng(u["seed"])
    n = u["draws"]
    fd = feer_draws(q, cfg["models"]["feer"], u, n, rng)
    rows = monthly_rows(q, comp.index)
    schemes = [s for s in u["weight_schemes"] if s in weights]
    out = pd.DataFrame(index=comp.index, columns=["lo", "mid", "hi"], dtype=float)
    pick_panel = rng.integers(0, gap_draws.shape[1], n)
    pick_w = rng.integers(0, len(schemes), n)
    last = None
    for t in comp.index:
        if t not in gap_draws.index or pd.isna(rows.get(t)) or pd.isna(comp.at[t, "ect"]):
            continue
        g_r = gap_draws.loc[t].to_numpy()[pick_panel]
        g_f = fd[int(rows[t])]
        w = np.array([weights[s].get(t, 0.5) for s in schemes])
        w = np.where(np.isnan(w), 0.5, w)[pick_w]
        g = w * g_r + (1 - w) * g_f
        out.loc[t] = np.nanpercentile(g, [10, 50, 90])
        last = g
    return out, last


def expost_gap(r: dict, cfg: dict, final_fit: dict, x_final: pd.DataFrame) -> pd.DataFrame:
    """Ex-post composite log gap for months of the IMF-assessed years (see module notes)."""
    imf = pd.read_csv(path(cfg, "manual") / "imf_eba_india.csv")
    norms = dict(zip(imf["analysis_year"], imf["ca_norm"]))
    q = r["feer_q"]
    pit = r["dataset"].pit
    reer = r["panel"]["reer_bis"]
    rows = []
    for t in pit.index:
        y = t.year
        if y not in norms or pd.isna(reer.get(t)):
            continue
        qt = pd.Timestamp(y, 3 * ((t.month - 1) // 3) + 1, 1)          # quarter containing the month
        if qt not in q.index or pd.isna(q.at[qt, "cad_underlying"]):
            continue
        g_f = np.log1p(-(q.at[qt, "cad_underlying"] - norms[y]) / q.at[qt, "semi_elasticity"] / 100)
        xr = x_final.loc[:y].dropna()
        if xr.empty:
            continue
        star = final_fit["alpha"]["IND"] + float(xr.iloc[-1] @ final_fit["b"])
        g_r = star - np.log(reer[t])
        rows.append({"date": t, "gap_reer_ex": g_r, "gap_feer_ex": g_f, "ect_ex": 0.5 * g_r + 0.5 * g_f})
    return pd.DataFrame(rows).set_index("date")


def coverage(ex: pd.DataFrame, bands: dict[str, tuple[pd.Series, pd.Series]]) -> dict:
    out = {}
    for name, (lo, hi) in bands.items():
        d = pd.concat([ex["ect_ex"], lo, hi], axis=1, keys=["x", "lo", "hi"]).dropna()
        inside = (d["x"] >= d["lo"]) & (d["x"] <= d["hi"])
        out[name] = {"n": int(len(d)), "coverage": float(inside.mean()) if len(d) else None,
                     "below": float((d["x"] < d["lo"]).mean()) if len(d) else None,
                     "above": float((d["x"] > d["hi"]).mean()) if len(d) else None,
                     "median_width_pct": float(((np.exp(d["hi"]) - np.exp(d["lo"])) * 100).median()) if len(d) else None}
    return out


def apply_corridor(comp: pd.DataFrame, series: pd.DataFrame) -> None:
    """Make the bootstrap corridor the headline one (in place); the end-to-end band is kept
    as *_e2e columns. Months without bootstrap draws keep the end-to-end band."""
    for c in ("ect_lo", "ect_hi", "fair_inr_strong", "fair_inr_weak"):
        comp[f"{c}_e2e"] = comp[c]
    comp["ect_lo"] = series["lo"].combine_first(comp["ect_lo"])
    comp["ect_hi"] = series["hi"].combine_first(comp["ect_hi"])
    comp["fair_inr_strong"] = comp["inr_usd"] * np.exp(-comp["ect_hi"])
    comp["fair_inr_weak"] = comp["inr_usd"] * np.exp(-comp["ect_lo"])
    comp.attrs["corridor"] = "joint bootstrap"


def run(r: dict, pdata, cfg: dict, gap_draws: pd.DataFrame) -> dict | None:
    from . import panel_anchor
    if gap_draws is None or gap_draws.empty or r.get("weights") is None:
        return None
    comp = r["composite"]
    bands, last = corridor(comp, gap_draws, r["feer_q"], r["weights"]["weights"], cfg)
    spot = comp["inr_usd"]
    p = cfg["models"]["panel_anchor"]
    info = r["dataset"].pit.index[-1]
    panel = panel_anchor.annual_panel(pdata, p, info)
    regs = p["specs"][p["central_spec"]]
    final_fit = panel_anchor.estimate(panel, regs, p["dols_k"])
    x_final = panel.loc["IND", regs].sort_index()
    ex = expost_gap(r, cfg, final_fit, x_final)
    e2e = ("ect_lo_e2e", "ect_hi_e2e") if "ect_lo_e2e" in comp else ("ect_lo", "ect_hi")
    cov = coverage(ex, {"bootstrap": (bands["lo"], bands["hi"]), "end_to_end": (comp[e2e[0]], comp[e2e[1]])})
    t_last = bands["mid"].last_valid_index()
    return {
        "series": bands.assign(fair_strong=spot * np.exp(-bands["hi"]), fair_weak=spot * np.exp(-bands["lo"]),
                               fair_mid=spot * np.exp(-bands["mid"])),
        "expost": ex,
        "latest": {"month": t_last.strftime("%Y-%m"),
                   "fair_strong": float(spot[t_last] * np.exp(-bands.at[t_last, "hi"])),
                   "fair_mid": float(spot[t_last] * np.exp(-bands.at[t_last, "mid"])),
                   "fair_weak": float(spot[t_last] * np.exp(-bands.at[t_last, "lo"])),
                   "mis_lo": float((np.exp(bands.at[t_last, "lo"]) - 1) * 100),
                   "mis_hi": float((np.exp(bands.at[t_last, "hi"]) - 1) * 100),
                   "p_undervalued": float((last > 0).mean()) if last is not None else None,
                   "old_strong": float(comp["fair_inr_strong"].iloc[-1]), "old_weak": float(comp["fair_inr_weak"].iloc[-1])},
        "headline": cfg["uncertainty"].get("headline_corridor", "end_to_end"),
        "coverage": cov, "draws": int(cfg["uncertainty"]["draws"]),
        "panel_boot_draws": int(gap_draws.shape[1]),
        "expost_window": [ex.index.min().strftime("%Y-%m"), ex.index.max().strftime("%Y-%m")] if len(ex) else None,
    }
