"""Self-contained HTML dashboard for a pipeline run.

``build_page(r)`` returns the page body (title, styles, markup, data and script, no
external dependencies except Google Fonts); ``write(r, run_dir)`` saves it as a full
HTML document, ``dashboard.html``, next to the run's report. Charts are inline SVG
drawn from the embedded data, so the file works offline and as a shared page.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

from . import __version__
from .models.flows import LABELS as FLOW_LABELS


def _num(x, nd=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def _last(s: pd.Series):
    s = s.dropna() if s is not None else pd.Series(dtype=float)
    return (s.iloc[-1], s.index[-1].strftime("%b %Y")) if len(s) else (None, None)


def _pct(gap):
    return None if gap is None or (isinstance(gap, float) and math.isnan(gap)) else (math.exp(gap) - 1) * 100


def collect(r: dict, note_md: str | None = None) -> dict:
    """Everything the page shows, as plain JSON-able values."""
    comp, ds = r["composite"], r["dataset"]
    cfg = r["config"]
    reg = r["regimes"]["p_stress_filtered"]
    rows = comp.dropna(subset=["ect"]).copy()
    series = []
    for d, x in rows.iterrows():
        series.append([d.strftime("%Y-%m"), _num(x["inr_usd"]), _num(x["fair_inr"]),
                       _num(x.get("fair_inr_strong")), _num(x.get("fair_inr_weak")),
                       _num(_pct(x["gap_reer"]), 2), _num(_pct(x["gap_feer"]), 2),
                       _num(x["misalignment_pct"], 2), _num(reg.get(d), 3)])

    fm, fp = r["feer_m"], cfg["models"]["feer"]
    lo_c, hi_c = f"misalignment_p{min(fp['band_percentiles'])}", f"misalignment_p{max(fp['band_percentiles'])}"
    comp_component = cfg["composite"].get("reer_component", "hp")

    def model(name, mis, fair, role, status, note=""):
        v, d = _last(mis)
        return {"name": name, "misalignment": _num(v, 1), "fair": _num(_last(fair)[0]) if fair is not None else None,
                "asof": d, "role": role, "status": status, "note": note}

    eg = lambda dg: "ok" if dg["engle_granger"]["cointegrated_5pct"] else "fail"
    pdg = r["panel_diag"]
    pc = pdg["specs"][pdg["central_spec"]]["panel_cointegration"]
    used = lambda key: "composite" if comp_component == key else "reported"
    models = [
        model("Composite fair value", comp["misalignment_pct"], comp["fair_inr"], "headline", "n/a",
              "Average of the REER and FEER log gaps"),
        model("REER panel anchor (19 EMs)", r["panel"]["misalignment_pct"], r["panel"]["fair_inr"], used("panel"),
              "ok" if pc["cointegrated_5pct"] else "fail",
              f"Productivity effect pooled across emerging markets; panel cointegration p = {pc['pvalue']:.3f}"
              + (f" (formal group ADF p = {fc['p']['group_adf']:.3f}; {fc['p_holm']:.2f} after the "
                 f"{pdg['formal_family']['n_testable']}-specification search, Holm)"
                 if (fc := pdg["specs"][pdg["central_spec"]].get("formal")) and fc.get("testable") else "")),
        model("FEER, IMF norm path", fm["misalignment_pct"], fm["fair_inr"], "composite", "n/a",
              f"80% band {_num(_last(fm[lo_c])[0], 1)}% to {_num(_last(fm[hi_c])[0], 1)}%"),
        model("REER gap (one-sided HP)", r["reer"]["misalignment_pct"], r["reer"]["fair_inr"], used("hp"), "n/a",
              "Cyclical gauge, mean-reverting by construction"),
        model("FEER, NIIP-stabilising norm", fm.get("misalignment_pct_niip"), None, "reported", "n/a",
              "Alternative norm: the deficit that keeps net foreign liabilities stable"),
        model("BEER, current", r["beer"]["misalignment_pct"], r["beer"]["fair_inr"], "reported", eg(r["beer_diag"]),
              "Real USD/INR on the dollar index and relative productivity"),
        model("REER anchor (India only)", r["anchor"]["misalignment_pct"], r["anchor"]["fair_inr"], used("anchor"),
              eg(r["anchor_diag"]), "Single-country fundamentals; too short a sample"),
    ]
    bm = r.get("benchmark")
    if bm:
        lb = bm["latest"]
        models.append({"name": f"IMF EBA current-account model ({lb['analysis_year']})",
                       "misalignment": _num(lb["imf_ca"], 1), "fair": None, "asof": lb["published"],
                       "role": "benchmark", "status": "n/a",
                       "note": f"External check: CA gap {lb['ca_gap']:+.1f}% of GDP vs norm {lb['ca_norm']:.1f}%, "
                               f"elasticity {lb['elasticity']:.2f}; our composite averaged {lb['composite_year']:+.1f}% "
                               f"that year"})

    bt = []
    for h, res in r["backtest"].items():
        o = res["oos"]
        if "rmse_ecm" not in o:
            continue
        bt.append({"h": h, "window": o["oos_window"], "n": o["n_oos"], "rmse": _num(o["rmse_ratio_ecm_vs_drift"], 3),
                   "cw": _num(o["clark_west"]["pvalue_one_sided"], 3), "hit": _num(o["hit_rate_ecm_sign"] * 100, 0),
                   "naive": _num(o["hit_rate_naive_depreciation"] * 100, 0),
                   "alpha": [_num(o["alpha_min"]), _num(o["alpha_max"])]})

    g = r["regime_summary"]
    m = ds.meta
    ends = m.get("series_end", {})
    fresh_keys = [("inr_usd", "USD/INR"), ("reer", "REER (RBI)"), ("cpi_india", "India CPI"), ("cpi_us", "US CPI"),
                  ("exports_usd_mn", "Trade"), ("fpi_usd_mn", "Portfolio flows"), ("dxy", "Dollar index"),
                  ("brent", "Brent")]
    freshness = [{"series": lbl, "end": ends.get(k)} for k, lbl in fresh_keys if ends.get(k)]
    bop_end = r["dataset"].bop["current_account"].last_valid_index()
    if bop_end is not None:
        freshness.append({"series": "Balance of payments", "end": f"{bop_end:%Y-%m} (quarter start)"})
    spot, asof = _last(comp["inr_usd"])
    v, _ = _last(comp["misalignment_pct"])
    return {
        "run_id": r["run_id"], "version": __version__, "generated": date.today().isoformat(), "asof": ds.asof.strftime("%Y-%m"),
        "spot": _num(spot), "fair": _num(_last(comp["fair_inr"])[0]), "misalignment": _num(v, 1),
        "corridor": [_num(_last(comp.get("fair_inr_strong", pd.Series(dtype=float)))[0]),
                     _num(_last(comp.get("fair_inr_weak", pd.Series(dtype=float)))[0])],
        "reer_component": comp_component,
        "stress": {"now": _num(g["p_stress_now"], 2), "date": g["p_stress_now_date"],
                   "steady": _num(g["p_stress_steady_state"], 2),
                   "h12": _num(g["p_stress_forecast"].get(12, g["p_stress_forecast"].get("12")), 2)},
        "series": series, "models": models, "backtest": bt,
        "freshness": freshness, "warnings": r["warnings"],
        "norm": {"value": _num(fm.get("misalignment_pct_imf_path", pd.Series(dtype=float)).dropna().iloc[-1]
                               if "misalignment_pct_imf_path" in fm else None, 1)},
        "flows": flows_block(r.get("flows_diag")),
        "market": market_block(r.get("market")),
        "peers": peers_block(r.get("peers"), r["config"]),
        "scenario": scenario_block(r),
        "note": note_md,
    }


def scenario_block(r: dict) -> dict | None:
    """Inputs for the in-page what-if: the latest FEER quarter and the REER component gap.

    The page recomputes the FEER gap as log(1 - (CA - norm) / semi / 100), with
    semi = -(eta_x X + eta_m M) / 100 - share * income / 100 (feer.semi), and the
    composite as w * REER gap + (1 - w) * FEER gap, so the defaults reproduce the headline.
    """
    q, comp, fp = r.get("feer_q"), r["composite"], r["config"]["models"]["feer"]
    if q is None or "cad_underlying" not in q:
        return None
    q = q.dropna(subset=["misalignment_pct", "cad_underlying", "norm_central"])
    last = comp.dropna(subset=["gap_reer", "inr_usd"])
    if q.empty or last.empty:
        return None
    row, c = q.iloc[-1], last.iloc[-1]

    def g(k):
        return _num(row.get(k), 6)

    return {"quarter": q.index[-1].strftime("%Y-%m"), "ca": g("cad_underlying"), "ca_reported": g("ca_pct_4q"),
            "norm": g("norm_central"), "norm_niip": g("norm_niip"), "norm_static": g("norm_static"),
            "x": g("exports_pct_gdp"), "m": g("imports_pct_gdp"), "inc": g("income_pct_gdp"),
            "semi_fixed": g("semi_elasticity"), "eta_x": fp["eta_exports"], "eta_m": fp["eta_imports"],
            "eta_unc": fp.get("eta_uncertainty", 0.5),
            "share": fp.get("income_fc_share", 0.5) if fp.get("income_term", False) else 0.0,
            "income_term": bool(fp.get("income_term", False)),
            "gap_reer": _num(c["gap_reer"], 6), "spot": _num(c["inr_usd"], 4), "month": last.index[-1].strftime("%Y-%m"),
            "feer_mis": _num(row["misalignment_pct"], 2)}


def flows_block(fd: dict | None) -> dict | None:
    if not fd:
        return None
    parts = [(k, FLOW_LABELS.get(k, k)) for k in fd["regressors"]] + [("drift", "Trend depreciation"),
                                                                      ("residual", "Unexplained")]
    wins = [{"months": w["months"], "start": w["start"], "end": w["end"], "actual": _num(w["actual"], 9),
             "parts": [{"key": k, "label": lbl, "v": _num(w[k], 9)} for k, lbl in parts],
             "fpi_out_of_window": _num(w["out_of_window"]["fpi"], 9)} for w in fd["windows"].values()]
    return {"windows": wins, "coef_fpi": _num(fd["coef"]["fpi"], 3), "t_fpi": _num(fd["t"]["fpi"], 1),
            "sample": fd["sample"], "r2": _num(fd["r2"], 2), "two_way": fd["direction"]["reading"].startswith("two-way"),
            "rbi": rbi_block(fd.get("rbi")),
            "iv_beta": _num(fd["identification"]["iv"]["beta"], 3) if fd.get("identification") else None}


PEER_NAMES = {"IND": "India", "CHN": "China", "BRA": "Brazil", "MEX": "Mexico", "IDN": "Indonesia", "TUR": "Turkey",
              "ZAF": "South Africa", "KOR": "Korea", "THA": "Thailand", "MYS": "Malaysia", "PHL": "Philippines",
              "CHL": "Chile", "COL": "Colombia", "PER": "Peru", "POL": "Poland", "HUN": "Hungary", "CZE": "Czechia",
              "ISR": "Israel", "ROU": "Romania"}


def peers_block(pe: dict | None, cfg: dict) -> dict | None:
    if not pe:
        return None
    im = (pe.get("imf") or {}).get("stats", {}).get("imf_reer_index")
    eps = pe.get("episodes", [])
    return {"month": pe["month"], "rank": pe["focus_rank"], "n": pe["n"], "focus": pe["focus"],
            "rows": [{"c": c, "name": PEER_NAMES.get(c, c), "v": _num(v, 1)} for c, v in pe["latest"].items()],
            "imf_rank_corr": _num(im["mean_rank_corr"], 2) if im else None,
            "imf_n_countries": len(pe["imf"]["countries"]) if pe.get("imf") else None,
            "episodes_ok": sum(e["pass"] for e in eps), "episodes_n": len(eps)}


def market_block(mk: dict | None) -> dict | None:
    if not mk:
        return None
    f6 = mk["forwards"]["6m"]
    return {"fwd6": _num(f6["forward"]), "prem6": _num(f6["premium"]), "month": f6["month"],
            "spread": _num(mk["spread"]["value"]), "pct": _num(mk["spread"]["percentile"], 0)}


def rbi_block(iv: dict | None) -> dict | None:
    if not iv:
        return None
    return {"price": _num(iv["price_pct_per_bn"], 3), "fwd_bn": _num(iv["fwd_book_bn"], 1),
            "fwd_pct": _num(iv["fwd_book_pct_reserves"], 1) if iv["fwd_book_pct_reserves"] is not None else None,
            "fwd_month": iv["fwd_book_month"], "latest_month": iv["latest_month"], "latest_bn": _num(iv["latest_bn"], 1),
            "windows": {k: {"start": w["start"], "end": w["end"], "sold": _num(w["net_sold_bn"], 1), "absorbed": _num(w["absorbed"], 9),
                            "pressure": _num(w["pressure"], 9), "actual": _num(w["actual"], 9),
                            "share": _num(w["absorbed_share"], 9) if w["absorbed_share"] is not None else None}
                        for k, w in iv["windows"].items()}}


def build_page(r: dict, note_md: str | None = None) -> str:
    data = json.dumps(collect(r, note_md), separators=(",", ":"), allow_nan=False)
    return TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))


def write(r: dict, run_dir: Path, note_md: str | None = None) -> Path:
    """``note_md``: the monthly note (Markdown, without its links line), shown on the page."""
    page = build_page(r, note_md)
    doc = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
           "</head>\n<body>\n" + page + "\n</body>\n</html>\n")
    out = Path(run_dir) / "dashboard.html"
    out.write_text(doc, encoding="utf-8")
    return out


TEMPLATE = r"""<title>Rupee Fair Value Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a desk monitor - verdict first, then history, components, regime, credibility, data. */
:root {
  --bg: #f4f6f8; --surface: #ffffff; --ink: #141a22; --ink-2: #4a5462; --ink-3: #6f7987;
  --rule: #dce1e7; --grid: #edf0f3; --accent: #b4600f; --accent-soft: #f6e7d6;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --band: rgba(42,120,214,.16);
  --good: #0ca30c; --warn: #fab219; --serious: #ec835a; --critical: #d03b3b;
  --good-ink: #0a6e0a; --bad-ink: #a32929;
  --f-display: "Instrument Serif", "Iowan Old Style", Georgia, serif;
  --f-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0e1116; --surface: #161b22; --ink: #eef1f5; --ink-2: #b3bcc8; --ink-3: #8c95a2;
  --rule: #2a313b; --grid: #1f252d; --accent: #e7953f; --accent-soft: #3a2a18;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --band: rgba(57,135,229,.22);
  --good-ink: #5fd35f; --bad-ink: #f08a8a; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0e1116; --surface: #161b22; --ink: #eef1f5; --ink-2: #b3bcc8; --ink-3: #8c95a2;
  --rule: #2a313b; --grid: #1f252d; --accent: #e7953f; --accent-soft: #3a2a18;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --band: rgba(57,135,229,.22);
  --good-ink: #5fd35f; --bad-ink: #f08a8a; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 15px/1.5 var(--f-body); margin: 0; }
.wrap { max-width: 1120px; margin: 0 auto; padding-inline: 16px; padding-block: 28px 48px; display: grid; gap: 20px; }
@media (min-width: 720px) { .wrap { padding-inline: 28px; } }
header.top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 24px; }
h1 { font: 400 2rem/1.1 var(--f-display); margin: 0; letter-spacing: .005em; text-wrap: balance; }
.meta { color: var(--ink-3); font: 12.5px/1.4 var(--f-mono); }
.eyebrow { text-transform: uppercase; letter-spacing: .08em; font-size: 11.5px; color: var(--ink-3); font-weight: 600; }
.panel { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 18px 20px; min-width: 0; }
.verdict { display: grid; gap: 18px 32px; grid-template-columns: 1fr; }
@media (min-width: 820px) { .verdict { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); } }
.big { font: 400 clamp(2.6rem, 6vw, 3.6rem)/1 var(--f-display); margin: 6px 0 8px; }
.big .unit { font-size: .45em; color: var(--ink-2); margin-left: 4px; }
.lede { color: var(--ink-2); max-width: 60ch; margin: 0; }
.lede strong { color: var(--ink); font-weight: 600; }
.corridor { margin-top: 16px; }
.corridor svg { display: block; width: 100%; height: 54px; overflow: visible; }
.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 20px; align-content: start; }
.fact .v { font: 500 1.35rem/1.2 var(--f-mono); font-variant-numeric: tabular-nums; }
.fact .s { color: var(--ink-3); font-size: 12.5px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--rule); color: var(--ink-2); white-space: nowrap; }
.pill .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.pill.under { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.pill.ok { color: var(--good-ink); } .pill.fail { color: var(--bad-ink); }
.pill.calm { color: var(--good-ink); } .pill.stress { color: var(--bad-ink); }
.bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.bar h2 { font: 600 1rem/1.3 var(--f-body); margin: 0; }
.seg { display: inline-flex; border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }
.seg button { font: 500 12.5px var(--f-mono); padding: 5px 11px; border: 0; background: transparent; color: var(--ink-2); cursor: pointer; }
.seg button + button { border-left: 1px solid var(--rule); }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--surface); }
.seg button:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12.5px; color: var(--ink-2); margin: 10px 0 2px; }
.legend i { display: inline-block; width: 16px; height: 0; border-top: 2px solid; vertical-align: middle; margin-right: 6px; }
.legend i.area { height: 10px; border: 0; background: var(--band); }
.chart { position: relative; min-width: 0; }
.chart svg { display: block; width: 100%; height: auto; }
.chart text { fill: var(--ink-3); font: 11px var(--f-mono); }
.chart .lbl { font-weight: 500; }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--rule); border-radius: 6px;
  padding: 8px 10px; font: 12px/1.45 var(--f-mono); color: var(--ink); box-shadow: 0 4px 14px rgba(0,0,0,.12); min-width: 150px; z-index: 2; }
.tip b { font-weight: 600; display: block; margin-bottom: 2px; font-family: var(--f-body); }
.tip .k { color: var(--ink-3); }
.grid2 { display: grid; gap: 20px; grid-template-columns: 1fr; }
@media (min-width: 900px) { .grid2 { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
.sub { color: var(--ink-3); font-size: 12.5px; margin: 4px 0 0; max-width: 70ch; }
.tablewrap { overflow-x: auto; margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th { text-align: left; font-weight: 600; color: var(--ink-3); font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--rule); white-space: nowrap; }
td { padding: 9px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
td.n, th.n { text-align: right; font-family: var(--f-mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.head td { font-weight: 600; }
td .note { display: block; color: var(--ink-3); font-size: 12px; margin-top: 2px; }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--ink-2); font-size: 13px; }
ul.warn { margin: 8px 0 0; padding-left: 18px; color: var(--ink-2); font-size: 13px; display: grid; gap: 4px; }
.flows { display: grid; gap: 6px; margin-top: 14px; }
.flows .row { display: grid; grid-template-columns: minmax(0, 11rem) minmax(0, 1fr); gap: 12px; align-items: center; font-size: 13px; }
.flows .row.total { font-weight: 600; border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-bottom: 2px; }
.flows .k { color: var(--ink-2); overflow-wrap: anywhere; }
.flows .row.focus { font-weight: 600; } .flows .row.focus .k { color: var(--ink); }
.flows svg { display: block; width: 100%; height: 22px; overflow: visible; }
.flows .cell { position: relative; min-width: 0; }
.flows .val { position: absolute; top: 50%; transform: translateY(-50%); font: 500 11.5px var(--f-mono); color: var(--ink); font-variant-numeric: tabular-nums; }
@media (max-width: 520px) { .flows .row { grid-template-columns: minmax(0, 8rem) minmax(0, 1fr); } }
footer { color: var(--ink-3); font-size: 12.5px; max-width: 80ch; }
.notebody { max-width: 72ch; color: var(--ink-2); }
.notebody h3 { font: 600 .95rem/1.3 var(--f-body); color: var(--ink); margin: 20px 0 6px; }
.notebody h3:first-child { margin-top: 8px; }
.notebody p { margin: 0 0 10px; } .notebody strong { color: var(--ink); font-weight: 600; }
.notebody ul { margin: 0 0 10px; padding-left: 20px; display: grid; gap: 3px; }
.notebody code { font: 12px var(--f-mono); background: var(--grid); padding: 1px 4px; border-radius: 3px; }
.notebody details > summary { margin: 6px 0 4px; color: var(--accent); font-weight: 600; }
.scen { display: grid; gap: 22px 36px; grid-template-columns: 1fr; margin-top: 14px; }
@media (min-width: 820px) { .scen { grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); } }
.ctl { display: grid; gap: 4px; margin-bottom: 16px; }
.ctl label { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; color: var(--ink-2); }
.ctl output { font: 500 13px var(--f-mono); color: var(--ink); font-variant-numeric: tabular-nums; }
.ctl input[type=range] { width: 100%; accent-color: var(--accent); }
.ctl .hint { color: var(--ink-3); font-size: 11.5px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.chips button { font: 500 11.5px var(--f-mono); padding: 3px 9px; border: 1px solid var(--rule); border-radius: 999px; background: transparent; color: var(--ink-2); cursor: pointer; }
.chips button:hover, .chips button:focus-visible { border-color: var(--accent); color: var(--accent); outline: none; }
.res .big { margin-top: 2px; } .res .delta { font: 500 13px var(--f-mono); color: var(--ink-3); }
.res table { margin-top: 12px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
  <header class="top">
    <div>
      <div class="eyebrow">INR per US dollar · point-in-time fair value</div>
      <h1>Rupee Fair Value Monitor</h1>
    </div>
    <div class="meta" id="meta"></div>
  </header>

  <section class="panel verdict" aria-label="Current reading">
    <div>
      <div class="eyebrow">Composite misalignment</div>
      <div class="big" id="bigMis"></div>
      <p class="lede" id="lede"></p>
      <div class="corridor" id="corridor" aria-label="Spot rate against the fair-value range"></div>
    </div>
    <div class="facts" id="facts"></div>
  </section>

  <section class="panel" id="notePanel" aria-labelledby="noteTitle">
    <div class="bar"><h2 id="noteTitle">This month's note</h2><span class="meta" id="noteMeta"></span></div>
    <div class="notebody" id="noteBody"></div>
  </section>

  <section class="panel">
    <div class="bar">
      <h2>USD/INR and composite fair value</h2>
      <div class="seg" role="group" aria-label="Time range" id="range">
        <button type="button" data-r="5">5Y</button><button type="button" data-r="10">10Y</button><button type="button" data-r="all">All</button>
      </div>
    </div>
    <div class="legend"><span><i style="border-color:var(--ink)"></i>USD/INR spot</span><span><i style="border-color:var(--s1)"></i>Composite fair value</span><span><i class="area"></i>Fair-value range (10th–90th pct)</span></div>
    <div class="chart" id="chMain"></div>
    <details>
      <summary>Monthly values, last 24 months</summary>
      <div class="tablewrap"><table id="tblMonths"></table></div>
    </details>
  </section>

  <div class="grid2">
    <section class="panel">
      <h2 style="font:600 1rem/1.3 var(--f-body);margin:0">Misalignment by component</h2>
      <p class="sub">Percent; above zero means the rupee is weaker than that model's fair value.</p>
      <div class="legend"><span><i style="border-color:var(--s1)"></i>Composite</span><span><i style="border-color:var(--s2)"></i>REER component</span><span><i style="border-color:var(--s3)"></i>FEER</span></div>
      <div class="chart" id="chComp"></div>
    </section>
    <section class="panel">
      <h2 style="font:600 1rem/1.3 var(--f-body);margin:0">Probability of a stress regime</h2>
      <p class="sub">Markov-switching model of monthly USD/INR moves, filtered with data available at each month.</p>
      <div class="chart" id="chStress"></div>
    </section>
  </div>

  <section class="panel">
    <h2 style="font:600 1rem/1.3 var(--f-body);margin:0">Models</h2>
    <p class="sub">The composite averages the REER component and the FEER. The others are reported for context; a failed long-run test means the model describes where fundamentals point, not a level the rupee returns to.</p>
    <div class="tablewrap"><table id="tblModels"></table></div>
  </section>

  <section class="panel" id="scenPanel" aria-labelledby="scenTitle">
    <div class="bar"><h2 id="scenTitle">What if? Test the assumptions</h2><div class="chips"><button type="button" id="scenReset">Reset to the model's values</button></div></div>
    <p class="sub" id="scenSub"></p>
    <div class="scen">
      <div id="scenCtl"></div>
      <div class="res" aria-live="polite">
        <div class="eyebrow">Composite misalignment under these assumptions</div>
        <div class="big" id="scenBig"></div>
        <div class="delta" id="scenDelta"></div>
        <div class="corridor" id="scenBar"></div>
        <div class="tablewrap"><table id="scenTbl"></table></div>
        <p class="sub" id="scenNote" style="margin-top:12px"></p>
      </div>
    </div>
  </section>

  <section class="panel" id="peerPanel">
    <h2 style="font:600 1rem/1.3 var(--f-body);margin:0">Rupee among emerging-market peers</h2>
    <p class="sub" id="peerSub"></p>
    <div class="flows" id="peerBars" role="img"></div>
    <p class="sub" id="peerNote" style="margin-top:14px"></p>
  </section>

  <section class="panel" id="flowPanel">
    <div class="bar">
      <h2>What moved the rupee</h2>
      <div class="seg" role="group" aria-label="Attribution window" id="flowWin"></div>
    </div>
    <p class="sub" id="flowSub"></p>
    <div class="legend"><span><i style="border-color:var(--accent);border-top-width:8px"></i>Pushed the rupee weaker</span><span><i style="border-color:var(--s1);border-top-width:8px"></i>Pushed it stronger</span><span><i style="border-color:var(--ink-3);border-top-width:8px"></i>Unexplained</span></div>
    <div class="flows" id="flowBars" role="img"></div>
    <p class="sub" id="flowRbi" style="margin-top:14px;color:var(--ink-2)"></p>
    <p class="sub" id="flowNote" style="margin-top:10px"></p>
  </section>

  <div class="grid2">
    <section class="panel">
      <h2 style="font:600 1rem/1.3 var(--f-body);margin:0">Does misalignment predict the rupee?</h2>
      <p class="sub">Out-of-sample forecasts from the composite against a random walk with drift. An RMSE ratio below 1 beats drift; a Clark-West p below 0.05 makes it significant.</p>
      <div class="tablewrap"><table id="tblBt"></table></div>
    </section>
    <section class="panel">
      <h2 style="font:600 1rem/1.3 var(--f-body);margin:0">Data</h2>
      <p class="sub">Latest month for each input in this run.</p>
      <div class="tablewrap"><table id="tblFresh"></table></div>
      <details><summary id="warnSum"></summary><ul class="warn" id="warnList"></ul></details>
    </section>
  </div>

  <footer id="foot"></footer>
</div>

<script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const fmt = (v, d = 2) => (v === null || v === undefined) ? "n/a" : Number(v).toFixed(d);
const sgn = (v, d = 1) => (v === null || v === undefined) ? "n/a" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
const monthName = (ym) => { const [y, m] = ym.split("-").map(Number); return new Date(y, m - 1, 1).toLocaleString("en-GB", { month: "short", year: "numeric" }); };
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

// ---------- header, verdict, facts
const under = D.misalignment > 0;
$("meta").textContent = `Data to ${monthName(D.asof)} · inrfv ${D.version} · run ${D.run_id} · built ${D.generated}`;
$("bigMis").innerHTML = `${sgn(D.misalignment)}<span class="unit">%</span>`;
$("lede").innerHTML = `At <strong>${fmt(D.spot)}</strong> per dollar, the rupee is <strong>${Math.abs(D.misalignment).toFixed(1)}% ${under ? "weaker" : "stronger"}</strong> than its composite fair value of <strong>${fmt(D.fair)}</strong>. `
  + `The fair-value range from model uncertainty is <strong>${fmt(D.corridor[0])}–${fmt(D.corridor[1])}</strong>; the spot rate is ${D.spot > D.corridor[1] ? "above the whole range" : D.spot < D.corridor[0] ? "below the whole range" : "inside it"}.`;
const stressLbl = D.stress.now > 0.5 ? "stress" : "calm";
const facts = [
  ["Verdict", `<span class="pill ${under ? "under" : ""}"><span class="dot"></span>${under ? "Undervalued" : "Overvalued"}</span>`, "Composite, REER + FEER"],
  ["Regime", `<span class="pill ${stressLbl}"><span class="dot"></span>${stressLbl === "stress" ? "Stress" : "Calm"} · ${fmt(D.stress.now * 100, 0)}%</span>`, `Stress odds in 12 months: ${fmt(D.stress.h12 * 100, 0)}%`],
  ["Spot", fmt(D.spot), `INR per USD, ${monthName(D.asof)}`],
  ["Fair value", fmt(D.fair), `Range ${fmt(D.corridor[0])}–${fmt(D.corridor[1])}`],
];
if (D.market) {
  facts.push(["6-month forward", fmt(D.market.fwd6), `Premium ${fmt(D.market.prem6)}% a year (${monthName(D.market.month)})`]);
  facts.push(["Forward spread", `${sgn(D.market.spread, 1)} pp`, `Premium over the policy-rate gap; above ${fmt(D.market.pct, 0)}% of months since 2000`]);
}
const R = D.flows && D.flows.rbi;
if (R) {
  const k0 = Object.keys(R.windows).sort((a, b) => a - b)[0], r0 = R.windows[k0];
  facts.push(["RBI intervention", `${r0.sold >= 0 ? "Sold" : "Bought"} $${fmt(Math.abs(r0.sold), 1)}bn`, `Net incl. forwards, ${monthName(r0.start)}–${monthName(r0.end)}`]);
  if (R.fwd_pct !== null) facts.push(["Forward book", `−$${fmt(Math.abs(R.fwd_bn), 0)}bn`, `Net forward sales, ${fmt(Math.abs(R.fwd_pct), 0)}% of reserves (${monthName(R.fwd_month)})`]);
}
$("facts").innerHTML = facts.map(([k, v, s]) => `<div class="fact"><div class="eyebrow">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");

function drawCorridor() {
  const host = $("corridor"); host.innerHTML = "";
  const W = host.clientWidth || 600, H = 54;
  const lo = Math.min(D.corridor[0], D.spot), hi = Math.max(D.corridor[1], D.spot);
  const pad = (hi - lo) * 0.12 || 1, x0 = lo - pad, x1 = hi + pad;
  const x = (v) => 8 + (v - x0) / (x1 - x0) * (W - 16);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Fair value range ${D.corridor[0]} to ${D.corridor[1]}, central ${D.fair}, spot ${D.spot}` }, host);
  el("line", { x1: 8, x2: W - 8, y1: 24, y2: 24, stroke: css("--rule"), "stroke-width": 2 }, svg);
  el("rect", { x: x(D.corridor[0]), y: 16, width: Math.max(2, x(D.corridor[1]) - x(D.corridor[0])), height: 16, rx: 3, fill: css("--band") }, svg);
  el("line", { x1: x(D.fair), x2: x(D.fair), y1: 12, y2: 36, stroke: css("--s1"), "stroke-width": 2 }, svg);
  el("circle", { cx: x(D.spot), cy: 24, r: 6, fill: css("--ink"), stroke: css("--surface"), "stroke-width": 2 }, svg);
  const t = (txt, xx, y, anchor, col) => { const e = el("text", { x: xx, y, "text-anchor": anchor, fill: col, style: "font:11px var(--f-mono)" }, svg); e.textContent = txt; };
  t(`range ${fmt(D.corridor[0])}`, x(D.corridor[0]), 50, "start", css("--ink-3"));
  t(`${fmt(D.corridor[1])}`, x(D.corridor[1]), 50, "end", css("--ink-3"));
  t(`fair ${fmt(D.fair)}`, x(D.fair), 9, "middle", css("--s1"));
  t(`spot ${fmt(D.spot)}`, Math.min(x(D.spot), W - 8), 50, x(D.spot) > W - 60 ? "end" : "middle", css("--ink"));
}

// ---------- generic time-series chart
function niceTicks(min, max, n) {
  const span = max - min || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const out = []; for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function lineChart(host, rows, opts) {
  host.innerHTML = "";
  const W = Math.max(300, host.clientWidth || 700), H = opts.height || 300;
  const m = { l: 44, r: opts.labelRoom || 70, t: 12, b: 26 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const vals = []; rows.forEach(r => opts.series.forEach(s => { const v = s.get(r); if (v !== null) vals.push(v); }));
  if (opts.band) rows.forEach(r => { const b = opts.band(r); if (b && b[0] !== null) vals.push(b[0], b[1]); });
  if (opts.zero) vals.push(0);
  let yMin = opts.yMin ?? Math.min(...vals), yMax = opts.yMax ?? Math.max(...vals);
  const pad = (yMax - yMin) * 0.06; if (opts.yMin === undefined) yMin -= pad; if (opts.yMax === undefined) yMax += pad;
  const n = rows.length, x = (i) => m.l + (n <= 1 ? 0 : i / (n - 1) * iw), y = (v) => m.t + (yMax - v) / (yMax - yMin) * ih;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.aria }, host);
  niceTicks(yMin, yMax, 5).forEach(v => {
    el("line", { x1: m.l, x2: m.l + iw, y1: y(v), y2: y(v), stroke: css(v === 0 && opts.zero ? "--ink-3" : "--grid"), "stroke-width": v === 0 && opts.zero ? 1 : 1 }, svg);
    const t = el("text", { x: m.l - 6, y: y(v) + 3.5, "text-anchor": "end" }, svg); t.textContent = opts.yFmt(v);
  });
  const years = [...new Set(rows.map(r => r[0].slice(0, 4)))];
  const every = Math.max(1, Math.ceil(years.length / Math.max(2, Math.floor(iw / 70))));
  years.forEach((yr, k) => { if (k % every) return; const i = rows.findIndex(r => r[0].startsWith(yr)); const t = el("text", { x: x(i), y: H - 6, "text-anchor": "middle" }, svg); t.textContent = yr; });
  if (opts.band) {
    let d = "", back = [];
    rows.forEach((r, i) => { const b = opts.band(r); if (!b || b[0] === null) return; d += (d ? "L" : "M") + x(i).toFixed(1) + "," + y(b[1]).toFixed(1); back.push(x(i).toFixed(1) + "," + y(b[0]).toFixed(1)); });
    if (d) el("path", { d: d + "L" + back.reverse().join("L") + "Z", fill: css("--band"), stroke: "none" }, svg);
  }
  if (opts.area) {
    let d = ""; rows.forEach((r, i) => { const v = opts.area.get(r); if (v === null) return; d += (d ? "L" : `M${x(i).toFixed(1)},${y(0).toFixed(1)}L`) + x(i).toFixed(1) + "," + y(v).toFixed(1); });
    const last = rows.length - 1; d += `L${x(last).toFixed(1)},${y(0).toFixed(1)}Z`;
    el("path", { d, fill: opts.area.fill, "fill-opacity": .28, stroke: "none" }, svg);
  }
  opts.series.forEach(s => {
    let d = "", pen = false;
    rows.forEach((r, i) => { const v = s.get(r); if (v === null) { pen = false; return; } d += (pen ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1); pen = true; });
    el("path", { d, fill: "none", stroke: css(s.color), "stroke-width": s.width || 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    for (let i = rows.length - 1; i >= 0; i--) { const v = s.get(rows[i]); if (v === null) continue;
      el("circle", { cx: x(i), cy: y(v), r: 3.5, fill: css(s.color), stroke: css("--surface"), "stroke-width": 1.5 }, svg);
      if (s.label) { const t = el("text", { x: x(i) + 7, y: y(v) + 3.5 + (s.dy || 0), class: "lbl", fill: css("--ink-2") }, svg); t.textContent = s.label(v); }
      break; }
  });
  // hover layer
  const cross = el("line", { y1: m.t, y2: m.t + ih, stroke: css("--ink-3"), "stroke-dasharray": "3 3", visibility: "hidden" }, svg);
  const dots = opts.series.map(s => el("circle", { r: 4, fill: css(s.color), stroke: css("--surface"), "stroke-width": 1.5, visibility: "hidden" }, svg));
  const hit = el("rect", { x: m.l, y: m.t, width: iw, height: ih, fill: "transparent" }, svg);
  const tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; host.appendChild(tip);
  const show = (evt) => {
    const box = svg.getBoundingClientRect(), sx = (evt.clientX - box.left) * (W / box.width);
    const i = Math.max(0, Math.min(n - 1, Math.round((sx - m.l) / iw * (n - 1)))), r = rows[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    opts.series.forEach((s, k) => { const v = s.get(r); if (v === null) { dots[k].setAttribute("visibility", "hidden"); return; }
      dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); dots[k].setAttribute("visibility", "visible"); });
    tip.innerHTML = `<b>${monthName(r[0])}</b>` + opts.tip(r);
    tip.hidden = false;
    const px = x(i) / W * box.width, tw = tip.offsetWidth;
    tip.style.left = (px + 14 + tw > box.width ? px - tw - 14 : px + 14) + "px"; tip.style.top = "8px";
  };
  hit.addEventListener("pointermove", show); hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); dots.forEach(d => d.setAttribute("visibility", "hidden")); });
}

// ---------- charts with range control
const S = D.series; // [ym, inr, fair, strong, weak, reerPct, feerPct, compPct, pStress]
let range = "10";
try { range = localStorage.getItem("inrfv-range") || range; } catch (e) {}
function rowsFor(r) { if (r === "all") return S; const last = S[S.length - 1][0], y0 = +last.slice(0, 4) - +r; return S.filter(x => x[0] >= `${y0}${last.slice(4)}`); }
function render() {
  document.querySelectorAll("#range button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.r === range)));
  const rows = rowsFor(range);
  lineChart($("chMain"), rows, {
    aria: "INR per USD and composite fair value with its range", yFmt: v => v.toFixed(0), height: 320, labelRoom: 64,
    band: r => [r[3], r[4]],
    series: [{ get: r => r[1], color: "--ink", label: v => fmt(v), dy: -6 }, { get: r => r[2], color: "--s1", label: v => fmt(v), dy: 8 }],
    tip: r => `<span class="k">Spot</span> ${fmt(r[1])}<br><span class="k">Fair</span> ${fmt(r[2])}<br><span class="k">Range</span> ${fmt(r[3])}–${fmt(r[4])}<br><span class="k">Gap</span> ${sgn(r[7])}%`,
  });
  lineChart($("chComp"), rows, {
    aria: "Misalignment of the composite, REER component and FEER, percent", yFmt: v => (v > 0 ? "+" : "") + v.toFixed(0) + "%", zero: true, height: 260, labelRoom: 52,
    series: [{ get: r => r[5], color: "--s2", width: 1.6, label: v => sgn(v, 0) + "%" }, { get: r => r[6], color: "--s3", width: 1.6, label: v => sgn(v, 0) + "%" },
             { get: r => r[7], color: "--s1", width: 2.4, label: v => sgn(v, 0) + "%" }],
    tip: r => `<span class="k">Composite</span> ${sgn(r[7])}%<br><span class="k">REER</span> ${sgn(r[5])}%<br><span class="k">FEER</span> ${sgn(r[6])}%`,
  });
  lineChart($("chStress"), rows, {
    aria: "Filtered probability of a stress regime", yFmt: v => (v * 100).toFixed(0) + "%", yMin: 0, yMax: 1, height: 260, labelRoom: 44,
    area: { get: r => r[8], fill: css("--serious") },
    series: [{ get: r => r[8], color: "--serious", width: 1.4, label: v => (v * 100).toFixed(0) + "%" }],
    tip: r => `<span class="k">P(stress)</span> ${r[8] === null ? "n/a" : (r[8] * 100).toFixed(0) + "%"}`,
  });
  drawCorridor();
}
document.querySelectorAll("#range button").forEach(b => b.addEventListener("click", () => { range = b.dataset.r; try { localStorage.setItem("inrfv-range", range); } catch (e) {} render(); }));

// ---------- tables
const recent = S.slice(-24).reverse();
$("tblMonths").innerHTML = `<thead><tr><th>Month</th><th class="n">Spot</th><th class="n">Fair</th><th class="n">Range</th><th class="n">Gap</th><th class="n">P(stress)</th></tr></thead><tbody>`
  + recent.map(r => `<tr><td>${monthName(r[0])}</td><td class="n">${fmt(r[1])}</td><td class="n">${fmt(r[2])}</td><td class="n">${fmt(r[3])}–${fmt(r[4])}</td><td class="n">${sgn(r[7])}%</td><td class="n">${r[8] === null ? "n/a" : (r[8] * 100).toFixed(0) + "%"}</td></tr>`).join("") + "</tbody>";
const roleLbl = { headline: "Headline", composite: "In composite", reported: "Reported only", benchmark: "IMF check" };
const statusLbl = { ok: '<span class="pill ok"><span class="dot"></span>Passes</span>', fail: '<span class="pill fail"><span class="dot"></span>Fails</span>', "n/a": '<span class="pill">Not applicable</span>' };
$("tblModels").innerHTML = `<thead><tr><th>Model</th><th class="n">Misalignment</th><th class="n">Fair USD/INR</th><th>Use</th><th>Long-run test</th></tr></thead><tbody>`
  + D.models.map(mm => `<tr class="${mm.role === "headline" ? "head" : ""}"><td>${mm.name}<span class="note">${mm.note}${mm.asof ? ` · ${mm.asof}` : ""}</span></td><td class="n">${sgn(mm.misalignment)}%</td><td class="n">${fmt(mm.fair)}</td><td>${roleLbl[mm.role]}</td><td>${statusLbl[mm.status]}</td></tr>`).join("") + "</tbody>";
$("tblBt").innerHTML = `<thead><tr><th>Horizon</th><th class="n">RMSE ratio</th><th class="n">Clark-West p</th><th class="n">Hit rate</th><th class="n">Naive</th></tr></thead><tbody>`
  + D.backtest.map(b => `<tr><td>${b.h} month${b.h > 1 ? "s" : ""}<span class="note">${b.window[0]} to ${b.window[1]}, n=${b.n}</span></td><td class="n">${fmt(b.rmse, 3)}</td><td class="n">${fmt(b.cw, 3)}</td><td class="n">${fmt(b.hit, 0)}%</td><td class="n">${fmt(b.naive, 0)}%</td></tr>`).join("") + "</tbody>";
$("tblFresh").innerHTML = `<thead><tr><th>Input</th><th class="n">Latest</th></tr></thead><tbody>`
  + D.freshness.map(f => `<tr><td>${f.series}</td><td class="n">${f.end}</td></tr>`).join("") + "</tbody>";
$("warnSum").textContent = `${D.warnings.length} data and model notes from this run`;
$("warnList").innerHTML = D.warnings.map(w => `<li>${w.replace(/</g, "&lt;")}</li>`).join("");
// ---------- flow attribution
const F = D.flows;
let flowWin = null;
function drawFlows() {
  const w = F.windows.find(x => x.months === flowWin) || F.windows[0];
  document.querySelectorAll("#flowWin button").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.m === w.months)));
  $("flowSub").textContent = `${monthName(w.start)} to ${monthName(w.end)}: USD/INR moved ${sgn(w.actual)}%. Each bar is that driver's share of the move, in percentage points; positive means it pushed the rupee weaker.`;
  const rows = [{ label: "Actual move", v: w.actual, total: true }, ...w.parts.map(p => ({ label: p.label, v: p.v, resid: p.key === "residual" }))];
  const m = Math.max(...rows.map(r => Math.abs(r.v || 0)), 0.5);
  const host = $("flowBars"); host.innerHTML = "";
  host.setAttribute("aria-label", rows.map(r => `${r.label} ${sgn(r.v)} points`).join("; "));
  const W = 400, mid = W / 2, room = 70, scale = (mid - room) / m;
  rows.forEach(r => {
    const row = document.createElement("div"); row.className = "row" + (r.total ? " total" : "");
    const k = document.createElement("div"); k.className = "k"; k.textContent = r.label; row.appendChild(k);
    const svg = el("svg", { viewBox: `0 0 ${W} 22`, preserveAspectRatio: "none", "aria-hidden": "true" });
    el("line", { x1: mid, x2: mid, y1: 0, y2: 22, stroke: css("--rule"), "stroke-width": 1, "vector-effect": "non-scaling-stroke" }, svg);
    const v = r.v || 0, len = Math.abs(v) * scale;
    const fill = r.resid ? css("--ink-3") : r.total ? css("--ink") : v > 0 ? css("--accent") : css("--s1");
    if (len > 0.5) {
      const b = el("rect", { x: v > 0 ? mid : mid - len, y: 5, width: len, height: 12, rx: 2, fill }, svg);
      el("title", {}, b).textContent = `${r.label}: ${sgn(v)} points`;
    }
    // The value label is HTML beside the bar end, so the stretched SVG does not distort it.
    const cell = document.createElement("div"); cell.className = "cell";
    const t = document.createElement("span"); t.className = "val"; t.textContent = sgn(v);
    const off = `calc(50% + ${(len / W) * 100}% + 6px)`;
    if (v >= 0) t.style.left = off; else t.style.right = off;
    cell.append(svg, t); row.appendChild(cell);
    host.appendChild(row);
  });
  const rb = F.rbi && F.rbi.windows[String(w.months)];
  $("flowRbi").innerHTML = rb ? `<strong>RBI:</strong> ${rb.sold >= 0 ? "sold" : "bought"} a net $${fmt(Math.abs(rb.sold), 1)}bn over these months, counting forwards. At the market's price of a dollar (${fmt(F.rbi.price, 2)}% per $1bn) that held the rupee about ${fmt(Math.abs(rb.absorbed), 1)} points ${rb.absorbed > 0 ? "stronger" : "weaker"}`
    + (rb.share !== null ? `; without it the move would have been about ${sgn(rb.pressure)}%, so the RBI absorbed roughly ${fmt(rb.share * 100, 0)}% of the pressure (a lower bound).` : ".") : "";
  const oow = w.fpi_out_of_window;
  $("flowNote").textContent = `Monthly regression, ${monthName(F.sample[0])} to ${monthName(F.sample[1])} (R² ${fmt(F.r2)}): each US$1bn of net portfolio inflow goes with a ${fmt(Math.abs(F.coef_fpi))}% ${F.coef_fpi < 0 ? "stronger" : "weaker"} rupee that month (t ${sgn(F.t_fpi)}). `
    + `Fitted without these months, portfolio flows account for ${sgn(oow)} points. `
    + (F.two_way ? "Flows and the rupee feed each other (foreign investors also sell a falling currency), so these are associations, not causes. " : "")
    + (F.iv_beta !== null ? `Identification: this is the upper end; with global risk shocks as instruments the effect is about ${fmt(Math.abs(F.iv_beta), 2)}% per $1bn (not significant), so the portfolio-flow bar is an upper bound. ` : "")
    + "Ex post and by reference month; this explains spot moves and does not change the fair value.";
}
// ---------- peers
const PE = D.peers;
if (PE) {
  $("peerSub").textContent = `REER misalignment of each currency on the same pooled productivity model, ${monthName(PE.month)}. Above zero = weaker than its own fundamentals imply. India ranks ${PE.rank} of ${PE.n}.`;
  const host = $("peerBars"), W = 400, mid = W / 2, room = 70;
  const m = Math.max(...PE.rows.map(r => Math.abs(r.v)), 1), scale = (mid - room) / m;
  host.setAttribute("aria-label", PE.rows.map(r => `${r.name} ${sgn(r.v)}%`).join("; "));
  PE.rows.forEach(r => {
    const focus = r.c === PE.focus;
    const row = document.createElement("div"); row.className = "row" + (focus ? " focus" : "");
    const k = document.createElement("div"); k.className = "k"; k.textContent = r.name; row.appendChild(k);
    const svg = el("svg", { viewBox: `0 0 ${W} 22`, preserveAspectRatio: "none", "aria-hidden": "true" });
    el("line", { x1: mid, x2: mid, y1: 0, y2: 22, stroke: css("--rule"), "stroke-width": 1, "vector-effect": "non-scaling-stroke" }, svg);
    const len = Math.abs(r.v) * scale;
    if (len > 0.5) {
      const b = el("rect", { x: r.v > 0 ? mid : mid - len, y: 5, width: len, height: 12, rx: 2, fill: focus ? css("--accent") : css("--ink-3") }, svg);
      el("title", {}, b).textContent = `${r.name}: ${sgn(r.v)}%`;
    }
    const cell = document.createElement("div"); cell.className = "cell";
    const t = document.createElement("span"); t.className = "val"; t.textContent = `${sgn(r.v)}%`;
    const off = `calc(50% + ${(len / W) * 100}% + 6px)`;
    if (r.v >= 0) t.style.left = off; else t.style.right = off;
    cell.append(svg, t); row.appendChild(cell); host.appendChild(row);
  });
  $("peerNote").textContent = `Gaps are relative to each currency's own history, so the ranking matters more than the level. `
    + (PE.imf_rank_corr !== null ? `Across the ${PE.imf_n_countries} currencies the IMF also assesses, the model orders them much as the IMF's REER-index assessments do (average rank correlation ${fmt(PE.imf_rank_corr)} a year). ` : "")
    + (PE.episodes_n ? `${PE.episodes_ok} of ${PE.episodes_n} known crisis episodes, fixed in advance, move the expected way.` : "");
} else { $("peerPanel").hidden = true; }

if (F && F.windows.length) {
  $("flowWin").innerHTML = F.windows.map(w => `<button type="button" data-m="${w.months}">${w.months}M</button>`).join("");
  try { flowWin = +localStorage.getItem("inrfv-flowwin") || null; } catch (e) {}
  document.querySelectorAll("#flowWin button").forEach(b => b.addEventListener("click", () => { flowWin = +b.dataset.m; try { localStorage.setItem("inrfv-flowwin", flowWin); } catch (e) {} drawFlows(); }));
  drawFlows();
} else { $("flowPanel").hidden = true; }

// ---------- this month's note (Markdown subset: headings, paragraphs, bullets, bold, code, links)
function mdInline(t) {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2">$1</a>').replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
}
function mdBlocks(lines) {
  const out = []; let para = [], list = [];
  const pflush = () => { if (para.length) out.push(`<p>${mdInline(para.join(" "))}</p>`); para = []; };
  const lflush = () => { if (list.length) out.push(`<ul>${list.map(x => `<li>${mdInline(x)}</li>`).join("")}</ul>`); list = []; };
  lines.forEach(l => {
    if (/^## /.test(l)) { pflush(); lflush(); out.push(`<h3>${mdInline(l.slice(3))}</h3>`); }
    else if (/^- /.test(l)) { pflush(); list.push(l.slice(2)); }
    else if (!l.trim() || /^---+$/.test(l.trim())) { pflush(); lflush(); }
    else { lflush(); para.push(l.trim()); }
  });
  pflush(); lflush(); return out.join("");
}
if (D.note) {
  const lines = D.note.replace(/\r/g, "").split("\n").filter(l => !/^# /.test(l));
  const metaIdx = lines.findIndex(l => /^Data to /.test(l));
  if (metaIdx >= 0) { $("noteMeta").textContent = lines[metaIdx].replace(/`/g, ""); lines.splice(metaIdx, 1); }
  const heads = lines.reduce((a, l, i) => (/^## /.test(l) ? a.concat(i) : a), []);
  const cut = heads.length > 2 ? heads[2] : lines.length;          // the reading + since the last note stay open
  $("noteBody").innerHTML = mdBlocks(lines.slice(0, cut))
    + (cut < lines.length ? `<details><summary>Read the full note: ${heads.slice(2).map(i => mdInline(lines[i].slice(3))).join(" · ")}</summary>${mdBlocks(lines.slice(cut))}</details>` : "");
} else { $("notePanel").hidden = true; }

// ---------- what if: recompute the FEER and the composite in the page
const SC = D.scenario;
if (SC) {
  const base = { norm: SC.norm, ca: SC.ca, eta: 1, share: SC.share, w: 0.5 };
  const st = { ...base };
  const lo = (v, d) => Math.floor((v - d) * 10) / 10, hi = (v, d) => Math.ceil((v + d) * 10) / 10;
  const ctls = [
    { k: "norm", label: "Current-account norm, % of GDP", min: -5, max: 1, step: 0.1, f: v => sgn(v, 1),
      hint: "The deficit India can sustain. Model: the IMF's published norm.",
      chips: [["IMF", SC.norm], SC.norm_niip !== null && ["NIIP-stabilising", SC.norm_niip], SC.norm_static !== null && ["Legacy fixed", SC.norm_static]].filter(Boolean) },
    { k: "ca", label: "Underlying current account, % of GDP", min: lo(SC.ca, 3), max: hi(SC.ca, 3), step: 0.05, f: v => sgn(v, 2),
      hint: `Four quarters to the quarter starting ${monthName(SC.quarter)}, oil and cycle adjusted; as reported ${sgn(SC.ca_reported, 2)}.` },
    { k: "eta", label: "Trade elasticities, × the IMF's", min: 1 - SC.eta_unc, max: 1 + SC.eta_unc, step: 0.05, f: v => "×" + v.toFixed(2),
      hint: `How strongly trade responds to the exchange rate (EBA: exports ${SC.eta_x}, imports ${SC.eta_m}). Lower means a bigger move is needed to close a gap.` },
    SC.income_term && { k: "share", label: "Share of net income paid in foreign currency", min: 0, max: 1, step: 0.05, f: v => (v * 100).toFixed(0) + "%",
      hint: "Unknown; the model uses the midpoint." },
    { k: "w", label: "Weight on the REER component", min: 0, max: 1, step: 0.05, f: v => (v * 100).toFixed(0) + "%",
      hint: "The rest goes to the FEER. Weights learned from each component's track record settle near 50%." },
  ].filter(Boolean);
  ctls.forEach(c => { if (st[c.k] < c.min) c.min = st[c.k]; if (st[c.k] > c.max) c.max = st[c.k]; });
  $("scenCtl").innerHTML = ctls.map(c => `<div class="ctl"><label for="sc_${c.k}"><span>${c.label}</span><output id="so_${c.k}" for="sc_${c.k}"></output></label>`
    + `<input type="range" id="sc_${c.k}" min="${c.min}" max="${c.max}" step="${c.step}">`
    + (c.chips ? `<div class="chips">${c.chips.map(([t, v]) => `<button type="button" data-k="${c.k}" data-v="${v}">${t} ${sgn(v, 1)}</button>`).join("")}</div>` : "")
    + `<span class="hint">${c.hint}</span></div>`).join("");
  const feerGap = (s) => {
    const k = s.eta;
    const semi = (SC.x !== null && SC.m !== null) ? -(SC.eta_x * k * SC.x + SC.eta_m * k * SC.m) / 100 - s.share * (SC.inc || 0) / 100 : SC.semi_fixed * k;
    const a = 1 - (s.ca - s.norm) / semi / 100;
    return a > 0 ? Math.log(a) : null;
  };
  const compGap = (s) => { const f = feerGap(s); return f === null ? null : s.w * SC.gap_reer + (1 - s.w) * f; };
  const pct = (g) => g === null ? null : (Math.exp(g) - 1) * 100;
  const g0 = compGap(base), f0 = SC.spot * Math.exp(-g0);
  function drawScen() {
    ctls.forEach(c => { $("sc_" + c.k).value = st[c.k]; $("so_" + c.k).textContent = c.f(+st[c.k]); });
    const g = compGap(st), m = pct(g), fair = g === null ? null : SC.spot * Math.exp(-g);
    $("scenBig").innerHTML = m === null ? "n/a" : `${sgn(m)}<span class="unit">%</span>`;
    const dm = m === null ? null : m - pct(g0);
    $("scenDelta").textContent = dm === null ? "" : Math.abs(dm) < 0.05 ? "Same as the model's reading" : `${sgn(dm)} points against the model's ${sgn(pct(g0))}%`;
    $("scenTbl").innerHTML = `<thead><tr><th></th><th class="n">Model</th><th class="n">Your case</th></tr></thead><tbody>`
      + `<tr><td>FEER misalignment</td><td class="n">${sgn(pct(feerGap(base)))}%</td><td class="n">${sgn(pct(feerGap(st)))}%</td></tr>`
      + `<tr><td>REER component (held)</td><td class="n">${sgn(pct(SC.gap_reer))}%</td><td class="n">${sgn(pct(SC.gap_reer))}%</td></tr>`
      + `<tr class="head"><td>Composite</td><td class="n">${sgn(pct(g0))}%</td><td class="n">${sgn(m)}%</td></tr>`
      + `<tr><td>Fair value, INR per USD</td><td class="n">${fmt(f0)}</td><td class="n">${fmt(fair)}</td></tr></tbody>`;
    const host = $("scenBar"); host.innerHTML = "";
    if (fair !== null) {
      const W = host.clientWidth || 500, H = 58;
      const pts = [fair, f0, SC.spot].concat(D.corridor[0] !== null ? D.corridor : []);
      const a = Math.min(...pts), b = Math.max(...pts), pad = (b - a) * 0.12 || 1, x0 = a - pad, x1 = b + pad;
      const x = (v) => 8 + (v - x0) / (x1 - x0) * (W - 16);
      const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Your fair value ${fmt(fair)} against the model's ${fmt(f0)} and spot ${fmt(SC.spot)}` }, host);
      el("line", { x1: 8, x2: W - 8, y1: 28, y2: 28, stroke: css("--rule"), "stroke-width": 2 }, svg);
      if (D.corridor[0] !== null) el("rect", { x: x(D.corridor[0]), y: 22, width: Math.max(2, x(D.corridor[1]) - x(D.corridor[0])), height: 12, rx: 3, fill: css("--band") }, svg);
      el("line", { x1: x(f0), x2: x(f0), y1: 18, y2: 38, stroke: css("--s1"), "stroke-width": 2 }, svg);
      el("line", { x1: x(fair), x2: x(fair), y1: 14, y2: 42, stroke: css("--accent"), "stroke-width": 3 }, svg);
      el("circle", { cx: x(SC.spot), cy: 28, r: 6, fill: css("--ink"), stroke: css("--surface"), "stroke-width": 2 }, svg);
      const t = (txt, xx, y, anchor, col) => { const e = el("text", { x: xx, y, "text-anchor": anchor, fill: col, style: "font:11px var(--f-mono)" }, svg); e.textContent = txt; };
      const edge = (xx) => xx < 50 ? "start" : xx > W - 50 ? "end" : "middle";
      t(`yours ${fmt(fair)}`, x(fair), 10, edge(x(fair)), css("--accent"));
      t(`model ${fmt(f0)}`, x(f0), 54, Math.abs(x(f0) - x(fair)) < 4 ? edge(x(f0)) : (x(f0) < x(fair) ? "end" : "start"), css("--s1"));
      t(`spot ${fmt(SC.spot)}`, x(SC.spot), Math.abs(x(SC.spot) - x(fair)) < 90 ? 54 : 10, edge(x(SC.spot)), css("--ink"));
    }
  }
  ctls.forEach(c => $("sc_" + c.k).addEventListener("input", (e) => { st[c.k] = +e.target.value; drawScen(); }));
  document.querySelectorAll("#scenCtl .chips button").forEach(b => b.addEventListener("click", () => { st[b.dataset.k] = +b.dataset.v; drawScen(); }));
  $("scenReset").addEventListener("click", () => { Object.assign(st, base); drawScen(); });
  $("scenSub").textContent = `Move the assumptions behind the fair value and watch the reading change. Uses the latest balance-of-payments data and the REER component as of ${monthName(SC.month)}, `
    + "with the panel anchor held at its estimate. Recomputed in your browser with the model's own formulas, so the starting values reproduce the headline.";
  $("scenNote").textContent = "The shaded band is the model's 80% range, which already allows for uncertainty in the norm, elasticities, data and weights; here you move one assumption at a time to see which ones matter. "
    + (SC.norm_niip !== null ? `The norm matters most: the NIIP-stabilising norm (${sgn(SC.norm_niip, 1)}% of GDP) would take the FEER reading from ${sgn(pct(feerGap(base)))}% to ${sgn(pct(feerGap({ ...base, norm: SC.norm_niip })))}%.` : "");
  let srt; window.addEventListener("resize", () => { clearTimeout(srt); srt = setTimeout(drawScen, 120); });
  drawScen();
} else { $("scenPanel").hidden = true; }

$("foot").innerHTML = `Fair values use only data published by each month-end. The REER component is the <strong>${D.reer_component === "panel" ? "panel anchor" : D.reer_component}</strong>; the FEER uses the IMF's current-account norms for India as they were published. Positive misalignment means the rupee is weaker than fair value.`;

render();
let rt; new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(render, 120); }).observe(document.querySelector(".wrap"));
const mq = window.matchMedia("(prefers-color-scheme: dark)"); mq.addEventListener?.("change", render);
new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
</script>
"""
