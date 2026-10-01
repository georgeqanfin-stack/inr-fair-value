"""FEER: the real exchange rate consistent with a sustainable current account.

For each quarter, using only data public when that quarter's BoP was released:

1. Current account  - trailing 4-quarter sum as % of GDP (removes seasonality).
2. Oil adjustment   - mechanical: net oil imports x (1 - Brent norm / Brent paid), i.e. the
                      part of the oil bill due to prices above their trailing 5-year mean,
                      volumes held fixed. Positive when oil is expensive.
                      Underlying CA = CA + oil adjustment.
3. Elasticity       - IMF EBA semi-elasticity of the CA to the REER:
                      semi = -(eta_x * exports/GDP + eta_m * imports/GDP) / 100
                      (pp of GDP per 1% REER appreciation), with gross goods and services
                      flows from the BoP and eta from IMF EBA-Lite 3.0.
4. Norms            - "imf_path" (central): the IMF EBA CA norms for India as published
                      2013-2025 (from -4.2% to -2.0% of GDP), each from its publication month;
                      "imf": a single IMF norm (-2.0% of GDP, s.e. 0.7);
                      "niip": the CA that keeps the net IIP/GDP ratio constant,
                      n * g / (1 + g) with n = NIIP/GDP and g = trailing nominal US$ growth;
                      "static": the legacy -2.5% assumption, for comparison.
5. Misalignment     - -(underlying CA - norm) / semi. Positive = INR undervalued.
6. Band             - Monte Carlo over the norm (normal, IMF s.e.) and the two trade
                      elasticities (uniform +/- eta_uncertainty), percentiles per quarter.

The legacy version fixed the elasticity at -0.267 (about 1.7x the EBA value for India),
used a single-quarter CA, and removed oil with a full-sample regression.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MS = pd.offsets.MonthBegin


def _roll(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).sum()


def load_norm_path(cfg: dict) -> pd.DataFrame:
    """IMF CA norms for India as published: columns available (month start), norm, se, assessed, source."""
    from ..config import path
    f = path(cfg, "manual") / cfg["models"]["feer"]["norm_path_file"]
    df = pd.read_csv(f)
    df["available"] = pd.to_datetime(df["available"] + "-01")
    return df.sort_values("available").reset_index(drop=True)


def norm_from_path(available: pd.Series, path_df: pd.DataFrame) -> pd.DataFrame:
    """The latest published norm at each date; before the first publication, the first norm (labelled)."""
    rows = []
    for d in available:
        pub = path_df[path_df["available"] <= d]
        if len(pub):
            r = pub.iloc[-1]
            rows.append((r["norm"], r["se"], f"{r['source']} [{r['assessed']}]"))
        else:
            r = path_df.iloc[0]
            rows.append((r["norm"], r["se"], f"backcast: earliest IMF norm ({r['assessed']})"))
    return pd.DataFrame(rows, index=available.index, columns=["norm", "se", "source"])


def build_quarters(bop: pd.DataFrame, pit: pd.DataFrame, p: dict, norm_path: pd.DataFrame | None = None) -> pd.DataFrame:
    q = bop.copy().sort_index()
    q.index.name = "quarter"
    w = p["window_quarters"]
    gdp4 = q["gdp_usd_mn"].rolling(w, min_periods=w).mean()          # annual-rate GDP, averaged
    q["gdp_4q"] = gdp4
    q["ca_pct_4q"] = _roll(q["current_account"], w) / gdp4 * 100

    # Trade shares (goods + services, gross) and the semi-elasticity.
    have_gross = {"goods_credit", "goods_debit", "services_credit", "services_debit"} <= set(q.columns)
    if have_gross:
        q["exports_pct_gdp"] = _roll(q["goods_credit"] + q["services_credit"], w) / gdp4 * 100
        q["imports_pct_gdp"] = _roll(q["goods_debit"] + q["services_debit"], w) / gdp4 * 100
    else:
        q["exports_pct_gdp"] = q["imports_pct_gdp"] = np.nan
    # Trade shares move slowly: when the latest quarter's gross flows are not out yet,
    # carry the previous quarter's shares for up to ``carry_quarters`` quarters.
    measured = q["exports_pct_gdp"].notna()
    for c in ["exports_pct_gdp", "imports_pct_gdp"]:
        q[c] = q[c].ffill(limit=p["carry_quarters"])
    q["semi_elasticity"] = -(p["eta_exports"] * q["exports_pct_gdp"] + p["eta_imports"] * q["imports_pct_gdp"]) / 100
    q["semi_source"] = np.where(measured, "EBA shares",
                                np.where(q["semi_elasticity"].notna(), "EBA shares, carried", "fallback"))
    q["semi_elasticity"] = q["semi_elasticity"].fillna(p["fallback_semi_elasticity"])

    # Mechanical oil adjustment.
    brent = pit["brent"]
    last_month = q.index + MS(2)
    b_paid, b_norm = [], []
    for end in last_month:
        hist = brent[brent.index <= end].dropna()
        b_paid.append(hist.tail(3 * w).mean() if len(hist) >= 3 * w else np.nan)
        b_norm.append(hist.tail(p["oil_norm_months"]).mean() if len(hist) >= p["oil_norm_months"] else np.nan)
    q["brent_paid"] = b_paid
    q["brent_norm"] = b_norm
    if "net_oil_imports" in q.columns:
        q["net_oil_pct_gdp"] = _roll(q["net_oil_imports"], w) / gdp4 * 100
        q["oil_adjustment"] = q["net_oil_pct_gdp"] * (1 - q["brent_norm"] / q["brent_paid"])
    else:
        q["net_oil_pct_gdp"] = np.nan
        q["oil_adjustment"] = 0.0
    q["cad_underlying"] = q["ca_pct_4q"] + q["oil_adjustment"].fillna(0)

    # Norms.
    q["norm_imf"] = p["imf_norm"]
    q["norm_static"] = p["static_norm"]
    if "niip" in q.columns:
        n = (q["niip"] / q["gdp_usd_mn"]).ffill(limit=p["carry_quarters"])
        k = 4 * p["niip_growth_years"]
        g = (gdp4 / gdp4.shift(k)) ** (1 / p["niip_growth_years"]) - 1
        q["niip_pct_gdp"] = n * 100
        q["nominal_usd_growth"] = g * 100
        q["norm_niip"] = n * g / (1 + g) * 100
    else:
        q["niip_pct_gdp"] = q["nominal_usd_growth"] = q["norm_niip"] = np.nan

    names = ["imf", "niip", "static"]
    if norm_path is not None:
        np_ = norm_from_path(q["available"], norm_path)
        q["norm_imf_path"], q["norm_imf_path_se"], q["norm_imf_path_source"] = np_["norm"], np_["se"], np_["source"]
        names.insert(0, "imf_path")
    elif p["central_norm"] == "imf_path":
        raise ValueError("central_norm = 'imf_path' needs the IMF norm path file")
    for name in names:
        q[f"misalignment_pct_{name}"] = -(q["cad_underlying"] - q[f"norm_{name}"]) / q["semi_elasticity"]
    q["norm_central"] = q[f"norm_{p['central_norm']}"]
    q["norm_central_se"] = q["norm_imf_path_se"] if p["central_norm"] == "imf_path" else p["imf_norm_se"]
    q["misalignment_pct"] = q[f"misalignment_pct_{p['central_norm']}"]
    q["fair_inr_q"] = q["inr_q"] / (1 + q["misalignment_pct"] / 100)

    # Experimental financing-adjusted norm (kept from v0.2, reported only).
    if {"fdi_bop", "loans"} <= set(q.columns):
        stable = _roll(q["fdi_bop"] + q["loans"], w) / gdp4 * 100
        q["stable_financing_pct_gdp"] = stable
        # Missing financing data (e.g. loans not yet published) leave the norm missing, not zero.
        q["cad_norm_conditional"] = np.where(stable.isna(), np.nan, np.where(stable > 0, -stable, 0.0))
        q["misalignment_pct_conditional"] = -(q["cad_underlying"] - q["cad_norm_conditional"]) / q["semi_elasticity"]
    return q


def band(q: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Monte Carlo percentiles of the misalignment over norm and elasticity uncertainty."""
    rng = np.random.default_rng(p["seed"])
    d, u = p["band_draws"], p["eta_uncertainty"]
    norm_sd = q["norm_central_se"].to_numpy(dtype=float)[:, None]
    norm = q["norm_central"].to_numpy()[:, None] + norm_sd * rng.normal(0, 1, d)[None, :]
    ex, im = q["exports_pct_gdp"].to_numpy()[:, None], q["imports_pct_gdp"].to_numpy()[:, None]
    ex_d = p["eta_exports"] * rng.uniform(1 - u, 1 + u, d)[None, :]
    im_d = p["eta_imports"] * rng.uniform(1 - u, 1 + u, d)[None, :]
    semi = -(ex_d * ex + im_d * im) / 100
    fallback = q["semi_elasticity"].to_numpy()[:, None] * rng.uniform(1 - u, 1 + u, d)[None, :]
    semi = np.where(np.isnan(semi), fallback, semi)
    mis = -(q["cad_underlying"].to_numpy()[:, None] - norm) / semi
    out = pd.DataFrame(index=q.index)
    ok = ~np.isnan(q["cad_underlying"].to_numpy())
    for pc in p["band_percentiles"]:
        col = np.full(len(q), np.nan)
        col[ok] = np.percentile(mis[ok], pc, axis=1)
        out[f"misalignment_p{pc}"] = col
    return out


def run(bop: pd.DataFrame, pit: pd.DataFrame, cfg: dict,
        norm_path: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = cfg["models"]["feer"]
    if norm_path is None and p["central_norm"] == "imf_path":
        norm_path = load_norm_path(cfg)
    q = build_quarters(bop, pit, p, norm_path)
    q = q.join(band(q, p))
    lo, hi = f"misalignment_p{min(p['band_percentiles'])}", f"misalignment_p{max(p['band_percentiles'])}"

    # Monthly view: the latest quarter public at each month-end.
    keep = ["misalignment_pct", "misalignment_pct_conditional", lo, hi,
            "misalignment_pct_imf_path", "misalignment_pct_imf", "misalignment_pct_niip", "misalignment_pct_static"]
    keep = [c for c in keep if c in q.columns]
    rel = q.dropna(subset=["misalignment_pct"]).reset_index().set_index("available").sort_index()
    rel = rel[~rel.index.duplicated(keep="last")]
    monthly = rel[["quarter"] + keep].reindex(pit.index, method="ffill")
    monthly["gap_log"] = np.log1p(monthly["misalignment_pct"] / 100)
    monthly["fair_inr"] = pit["inr_usd"] * np.exp(-monthly["gap_log"])
    # Higher misalignment -> lower (stronger) fair INR/USD.
    monthly["gap_log_lo"] = np.log1p(monthly[lo] / 100)
    monthly["gap_log_hi"] = np.log1p(monthly[hi] / 100)
    monthly["fair_inr_strong"] = pit["inr_usd"] * np.exp(-monthly["gap_log_hi"])
    monthly["fair_inr_weak"] = pit["inr_usd"] * np.exp(-monthly["gap_log_lo"])
    return q, monthly
