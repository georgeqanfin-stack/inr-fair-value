"""External benchmark: this model against the IMF's own India assessments.

The IMF's External Balance Assessment (EBA), published each year with the External
Sector Report, assesses India's current account (CA) and real exchange rate for the
previous year (data/raw/manual/imf_eba_india.csv, from scripts/extract_imf_eba.py):

* CA model: the CA gap (cyclically adjusted CA minus the norm, % of GDP). The IMF
  converts it into a REER gap with its CA/REER semi-elasticity: REER gap = -CA gap /
  elasticity. IMF staff assessments rest mainly on this model.
* REER-index and REER-level models: direct regression-based REER gaps.

All three are put on this project's sign convention (positive = rupee undervalued) and
compared with this model's readings two ways:

* same period: the average of this model's point-in-time monthly readings over the
  calendar year the IMF assessed;
* same date: this model's reading in the month the IMF assessment was published.

Pairings: our FEER vs the IMF CA model (same framework; not independent, since our
FEER uses the IMF's published norms, though with its own CA data, oil adjustment and
elasticity); our REER component vs the IMF REER models; our composite vs each.
With nine annual assessments, correlations are descriptive, not tests.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

IMF = {"imf_ca": "IMF CA model (CA gap / elasticity)", "imf_reer_index": "IMF REER-index model",
       "imf_reer_level": "IMF REER-level model"}
OURS = {"composite": "Composite", "feer": "FEER", "reer": "REER component"}
PAIRS = [("feer", "imf_ca"), ("reer", "imf_reer_level"), ("reer", "imf_reer_index"),
         ("composite", "imf_ca"), ("composite", "imf_reer_level")]


def load(file: Path) -> pd.DataFrame:
    d = pd.read_csv(file)
    d["published"] = pd.to_datetime(d["published"] + "-01")
    d["imf_ca"] = d["ca_gap"] / d["elasticity"]               # + = undervalued
    d["imf_reer_index"] = -d["reer_gap_index"]
    d["imf_reer_level"] = -d["reer_gap_level"]
    return d


def ours_table(d: pd.DataFrame, series: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for _, r in d.iterrows():
        y, pub = int(r["analysis_year"]), r["published"]
        rec = {"analysis_year": y, "published": pub.strftime("%Y-%m")}
        for k, s in series.items():
            s = s.dropna()
            yr = s[(s.index.year == y)]
            rec[f"{k}_year"] = float(yr.mean()) if len(yr) else np.nan
            rec[f"{k}_at_pub"] = float(s.loc[:pub].iloc[-1]) if len(s.loc[:pub]) and s.index.min() <= pub else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def agreement(x: pd.Series, y: pd.Series) -> dict:
    m = pd.concat([x, y], axis=1).dropna()
    if len(m) < 3:
        return {"n": int(len(m))}
    a, b = m.iloc[:, 0], m.iloc[:, 1]
    return {"n": int(len(m)), "corr": float(a.corr(b)), "same_sign": float((np.sign(a) == np.sign(b)).mean()),
            "mean_diff_pp": float((a - b).mean()), "mean_abs_diff_pp": float((a - b).abs().mean())}


def run(r: dict, cfg: dict) -> dict | None:
    from ..config import path
    file = path(cfg, "manual") / "imf_eba_india.csv"
    if not file.exists():
        return None
    d = load(file)
    key = cfg["composite"].get("reer_component", "hp")
    reer = {"panel": r["panel"], "anchor": r["anchor"], "hp": r["reer"]}[key]["misalignment_pct"]
    o = ours_table(d, {"composite": r["composite"]["misalignment_pct"], "feer": r["feer_m"]["misalignment_pct"],
                       "reer": reer})
    t = d.merge(o, on=["analysis_year"], suffixes=("", "_o")).drop(columns=["published_o"])
    stats = {}
    for ours, imf in PAIRS:
        for when in ("year", "at_pub"):
            stats[f"{ours}_{when}~{imf}"] = {"ours": OURS[ours], "imf": IMF[imf], "when": when,
                                             **agreement(t[f"{ours}_{when}"], t[imf])}
    last = t.iloc[-1]
    return {"table": t.assign(published=t["published"].dt.strftime("%Y-%m")).to_dict(orient="records"),
            "stats": stats, "latest": {"analysis_year": int(last["analysis_year"]),
                                       "published": last["published"].strftime("%Y-%m"),
                                       "imf_ca": float(last["imf_ca"]), "ca_gap": float(last["ca_gap"]),
                                       "ca_norm": float(last["ca_norm"]), "elasticity": float(last["elasticity"]),
                                       "imf_reer_level": float(last["imf_reer_level"]),
                                       "imf_reer_index": float(last["imf_reer_index"]),
                                       "feer_year": float(last["feer_year"]), "composite_year": float(last["composite_year"]),
                                       "reer_year": float(last["reer_year"])},
            "first_year": int(t["analysis_year"].min()), "n_years": int(len(t)), "reer_component": key}
