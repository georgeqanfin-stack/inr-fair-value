"""Peer currencies: the panel REER anchor applied to every currency in the panel.

panel_anchor.run produces, month by month and point in time, each panel currency's REER
misalignment (+ = undervalued) from the same pooled fit (its own country effect plus the
pooled coefficients times its latest published fundamentals). Three uses:

* Cross-section: where India stands among its peers now.
* Episodes: known currency crises, listed in the config before looking at the results
  ([peers] episodes). A sensible model should register a move towards undervaluation
  after a sell-off (and the reverse after a sustained rally).
* IMF cross-check: the IMF's EBA assesses 11 of the 19 currencies each year
  (data/raw/manual/imf_eba_panel.csv). Our year-average gaps are compared with the IMF's
  REER-index, REER-level and CA-model gaps, pooled, within each year (rank correlation:
  does the model order currencies like the IMF?) and within each country over time.

Gaps are relative to each currency's own history (the country effect is its mean
residual), so levels are not comparable to absolute assessments; rankings and
movements are.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

IMF_MEASURES = {"imf_reer_index": "IMF REER-index model", "imf_reer_level": "IMF REER-level model",
                "imf_ca": "IMF CA model (CA gap / elasticity)"}


def episodes(gaps: pd.DataFrame, spec: list[dict]) -> list[dict]:
    out = []
    for e in spec:
        s = gaps.get(e["country"])
        if s is None:
            continue
        b = s.loc[e["before"][0]:e["before"][1]].mean()
        a = s.loc[e["after"][0]:e["after"][1]].mean()
        change = a - b
        want = 1 if e.get("expect", "weaker") == "weaker" else -1
        out.append({**e, "before_mean": float(b), "after_mean": float(a), "change": float(change),
                    "pass": bool(np.sign(change) == want)})
    return out


def imf_check(gaps: pd.DataFrame, file: Path) -> dict | None:
    if not file.exists():
        return None
    imf = pd.read_csv(file)
    imf["imf_ca"] = imf["ca_gap"] / imf["elasticity"]
    imf["imf_reer_index"] = -imf["reer_gap_index"]
    imf["imf_reer_level"] = -imf["reer_gap_level"]
    ours = gaps.groupby(gaps.index.year).mean().stack().rename("ours").reset_index()
    ours.columns = ["analysis_year", "country", "ours"]
    m = imf.merge(ours, on=["analysis_year", "country"])
    stats = {}
    for k, label in IMF_MEASURES.items():
        rank = m.groupby("analysis_year").apply(lambda g: g["ours"].corr(g[k], method="spearman"),
                                                include_groups=False)
        dm_o = m["ours"] - m.groupby("country")["ours"].transform("mean")
        dm_i = m[k] - m.groupby("country")[k].transform("mean")
        stats[k] = {"label": label, "n": int(len(m)), "pooled_corr": float(m["ours"].corr(m[k])),
                    "same_sign": float((np.sign(m["ours"]) == np.sign(m[k])).mean()),
                    "mean_rank_corr": float(rank.mean()), "min_rank_corr": float(rank.min()),
                    "within_country_corr": float(dm_o.corr(dm_i))}
    years = sorted(m["analysis_year"].unique())
    return {"countries": sorted(m["country"].unique()), "years": [int(years[0]), int(years[-1])], "stats": stats,
            "latest": m[m["analysis_year"] == years[-1]][["country", "ours", "imf_reer_index", "imf_reer_level",
                                                          "imf_ca"]].to_dict(orient="records")}


def run(gaps: pd.DataFrame, cfg: dict, focus: str = "IND") -> dict | None:
    from ..config import path
    if gaps is None or gaps.empty:
        return None
    last = gaps.dropna(how="all").iloc[-1].dropna().sort_values(ascending=False)
    rank = int(list(last.index).index(focus)) + 1 if focus in last.index else None
    p = cfg.get("peers", {})
    return {"month": gaps.dropna(how="all").index[-1].strftime("%Y-%m"),
            "latest": {c: float(v) for c, v in last.items()}, "focus": focus, "focus_rank": rank,
            "n": int(len(last)), "median": float(last.median()),
            "episodes": episodes(gaps, p.get("episodes", [])),
            "imf": imf_check(gaps, path(cfg, "manual") / "imf_eba_panel.csv")}
