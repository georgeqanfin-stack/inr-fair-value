"""Monthly note: a one-page plain-language summary of a run.

The text is assembled from the run's numbers with fixed rules, so every figure in
the note traces back to results.json and the same inputs always give the same note.
``build_note(r)`` works for any run; the refresh passes ``change`` (the headline
move since the last published report), ``diffs`` (new and revised data) and
``gate_warnings`` so the note can say what changed this month.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

GROUPS = {  # cached-file prefix -> what a reader calls it
    "dbie/inr_usd": "RBI reference rate", "dbie/reer": "RBI REER", "dbie/neer": "RBI NEER",
    "dbie/fx_reserves": "FX reserves", "dbie/exports": "trade", "dbie/imports": "trade",
    "dbie/fdi": "foreign investment flows", "dbie/fpi": "foreign investment flows",
    "dbie/bop.": "balance of payments", "dbie/bopx.": "balance of payments", "dbie/cpi.": "India CPI",
    "dbie/oil_": "oil trade", "dbie/wacr": "call money rate",
    "fred/RB": "BIS panel REERs", "fred/": "US and market data (FRED)",
    "worldbank_panel/": "World Bank panel", "wb_": "World Bank annual data",
}


def _last(s):
    s = s.dropna() if s is not None else pd.Series(dtype=float)
    return (float(s.iloc[-1]), s.index[-1]) if len(s) else (np.nan, None)


def _signed(v, nd=1, unit="%"):
    return "n/a" if v is None or np.isnan(v) else f"{v:+.{nd}f}{unit}"


def _month(ym: str) -> str:
    try:
        return pd.Timestamp(ym + "-01").strftime("%b %Y")
    except ValueError:
        return ym


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def size_word(m: float) -> str:
    a = abs(m)
    if a < 2:
        return "close to"
    if a < 5:
        return "modestly"
    if a < 10:
        return "moderately"
    return "substantially"


def verdict_sentence(spot, fair, mis, lo, hi) -> str:
    if abs(mis) < 2:
        core = f"At {spot:.2f} per dollar, the rupee is close to its composite fair value of {fair:.2f} ({mis:+.1f}%)."
    else:
        side = "weaker" if mis > 0 else "stronger"
        label = "undervalued" if mis > 0 else "overvalued"
        core = (f"At {spot:.2f} per dollar, the rupee is {size_word(mis)} {label}: "
                f"{abs(mis):.1f}% {side} than its composite fair value of {fair:.2f}.")
    if np.isnan(lo) or np.isnan(hi):
        return core
    where = "above the whole range" if spot > hi else "below the whole range" if spot < lo else "inside that range"
    return core + f" Allowing for model uncertainty, fair value lies between {lo:.2f} and {hi:.2f}, and the spot rate is {where}."


def data_lines(diffs: dict) -> list[str]:
    seen: dict[str, dict] = {}
    for name, d in (diffs or {}).items():
        label = next((v for k, v in GROUPS.items() if name.startswith(k)), name)
        g = seen.setdefault(label, {"new": 0, "revised": 0, "to": None, "big": None})
        g["new"] += d.get("new", 0)
        g["revised"] += d.get("revised", 0)
        if "new_range" in d and d["new_range"][1][:2] in ("19", "20"):
            g["to"] = max(g["to"] or "", d["new_range"][1])
        mr = d.get("max_revision")
        if mr and (g["big"] is None or mr["pct"] > g["big"]["pct"]):
            g["big"] = mr
    out = []
    for label, g in sorted(seen.items(), key=lambda kv: -kv[1]["new"]):
        if not g["new"] and not g["revised"]:
            continue
        bits = []
        if g["new"]:
            bits.append(f"{g['new']} new observation{'s' if g['new'] != 1 else ''}" + (f", now to {_month(g['to'])}" if g["to"] else ""))
        if g["revised"]:
            r = g["big"]
            bits.append(f"{g['revised']} revised" + (f" (largest {r['pct']:.1f}% at {_month(r['at']) if r['at'][:2] in ('19', '20') else r['at']})" if r and r["pct"] >= 1 else ""))
        out.append(f"- **{label}**: " + "; ".join(bits) + ".")
    return out


def flow_paragraph(fd: dict) -> list[str]:
    """What moved the spot rate over the shortest attribution window, in words."""
    w = fd["windows"][min(fd["windows"], key=int)]
    span = f"{_month(w['start'])} to {_month(w['end'])}"
    move = "weakened" if w["actual"] > 0 else "strengthened"
    parts = {"portfolio flows": w["fpi"], "direct investment": w["fdi"], "the dollar": w["dxy"],
             "oil": w["brent"], "trend depreciation": w["drift"]}
    big = sorted(((k, v) for k, v in parts.items() if abs(v) >= 0.25), key=lambda kv: -abs(kv[1]))
    lead = ", ".join(f"{k} {v:+.1f}" for k, v in big) if big else "no single driver above 0.25 points"
    fpi_sig = fd["p"]["fpi"] < 0.05
    two_way = fd["direction"]["reading"].startswith("two-way")
    L = ["## What moved the rupee\n",
         f"From {span} the rupee {move} {abs(w['actual']):.1f}%. Split by a monthly regression on flows and "
         f"global drivers (points of the move, positive = weaker): {lead}; unexplained {w['residual']:+.1f}."
         + (f" Each US$1bn of net portfolio outflow goes with about {abs(fd['coef']['fpi']):.2f}% rupee weakness."
            if fpi_sig else " Portfolio flows are not a significant driver over the sample.")
         + (" Flows and the rupee feed each other (foreign investors also sell a falling currency), so read "
            "these as associations, not causes." if two_way else "") + "\n"]
    iv = fd.get("rbi")
    if iv:
        r = iv["windows"][min(iv["windows"], key=int)]
        act = "sold" if r["net_sold_bn"] > 0 else "bought"
        s = (f"Over the same months the RBI {act} a net US${abs(r['net_sold_bn']):.1f} bn, counting forwards. "
             f"Valued at the market's price of a dollar, that held the rupee about {abs(r['absorbed']):.1f} points "
             f"{'stronger' if r['absorbed'] > 0 else 'weaker'}")
        if r["absorbed_share"] is not None:
            s += (f": without it the rupee would have weakened about {r['pressure']:.1f}% instead of "
                  f"{r['actual']:.1f}%, so the RBI absorbed roughly {r['absorbed_share']:.0%} of the pressure (a lower bound)")
        s += "."
        if iv["fwd_book_pct_reserves"] is not None:
            s += (f" Its net forward sales outstanding stand at US${abs(iv['fwd_book_bn']):.0f} bn, "
                  f"{abs(iv['fwd_book_pct_reserves']):.0f}% of reserves ({_month(iv['fwd_book_month'])}).")
        L.append(s + "\n")
    return L


def build_note(r: dict, change: dict | None = None, diffs: dict | None = None,
               gate_warnings: list[str] | None = None, links: dict | None = None) -> str:
    comp, ds, cfg = r["composite"], r["dataset"], r["config"]
    spot, asof = _last(comp["inr_usd"])
    fair, _ = _last(comp["fair_inr"])
    mis, _ = _last(comp["misalignment_pct"])
    lo, _ = _last(comp.get("fair_inr_strong", pd.Series(dtype=float)))
    hi, _ = _last(comp.get("fair_inr_weak", pd.Series(dtype=float)))
    month = asof.strftime("%B %Y") if asof is not None else "n/a"
    L = [f"# INR/USD fair value note, {month}\n",
         f"Data to {month} · run `{r['run_id']}` · written {date.today():%d %b %Y}\n"]

    L.append("## The reading\n")
    L.append(verdict_sentence(spot, fair, mis, lo, hi) + "\n")
    fm, pnl = r["feer_m"], r["panel"]
    feer_v, _ = _last(fm["misalignment_pct"])
    reer_key = cfg["composite"].get("reer_component", "hp")
    reer_v, _ = _last({"panel": pnl, "anchor": r["anchor"], "hp": r["reer"]}[reer_key]["misalignment_pct"])
    reer_name = {"panel": "productivity-based REER anchor", "anchor": "India-only REER anchor",
                 "hp": "REER trend gap"}[reer_key]
    agree = np.sign(feer_v) == np.sign(reer_v)
    L.append(f"The two components {'agree' if agree else 'disagree'}: the {reer_name} puts the rupee "
             f"{_signed(reer_v)} from fair value, and the external-balance model (FEER) {_signed(feer_v)}. "
             "Positive means weaker than fair.\n")

    L.append("## Since the last note\n")
    if change:
        m0, m1 = change["misalignment_pct"]
        s0, s1 = change["spot"]
        f0, f1 = change["fair"]
        c = change["contribution_pp"]
        if change["previous_asof"] == change["asof"] and abs(m1 - m0) < 0.05:
            L.append(f"No new month of exchange-rate data since the last note ({_month(change['previous_asof'])}); "
                     f"the reading is unchanged at {m1:+.1f}%.\n")
        else:
            move = "weakened" if s1 > s0 else "strengthened" if s1 < s0 else "was unchanged"
            L.append(f"From {_month(change['previous_asof'])} to {_month(change['asof'])} the rupee {move} from {s0:.2f} to {s1:.2f} "
                     f"per dollar, and composite fair value moved from {f0:.2f} to {f1:.2f}. Misalignment went from "
                     f"{m0:+.1f}% to {m1:+.1f}%: the REER component contributed {c['REER component']:+.1f} points "
                     f"and the FEER {c['FEER']:+.1f}.\n")
    elif diffs is None:
        L.append("Month-on-month changes are added when the note is produced by the monthly refresh "
                 "(`python -m inrfv.refresh`).\n")
    else:
        L.append("There is no earlier published reading to compare with yet.\n")
    dl = data_lines(diffs)
    if diffs is not None:
        L.append("New and revised data this month:\n" if dl else "No source published new or revised data since the last refresh.\n")
        L += dl
        if dl:
            L.append("")

    L.append("## Risk regime\n")
    g = r["regime_summary"]
    state = "stress" if g["p_stress_now"] > 0.5 else "calm"
    L.append(f"The regime model reads **{state}**: the probability of the high-volatility stress state is "
             f"{g['p_stress_now'] * 100:.0f}% ({_month(g['p_stress_now_date'])}), against a long-run average of "
             f"{g['p_stress_steady_state'] * 100:.0f}%. Twelve months ahead it puts the odds at "
             f"{g['p_stress_forecast'].get(12, g['p_stress_forecast'].get('12', np.nan)) * 100:.0f}%. "
             f"In stress months the rupee's monthly moves are about {g['stress']['sd_pct'] / g['calm']['sd_pct']:.0f} "
             f"times as large as in calm ones ({g['stress']['sd_pct']:.1f}% vs {g['calm']['sd_pct']:.1f}% standard deviation).\n")
    tv = g.get("tvtp")
    if tv:
        worse = all(v["diff_vs_constant"] <= 0 for k, v in tv["oos"].items() if k != "constant")
        L.append("Letting oil, the VIX, portfolio flows or RBI intervention drive the switching odds "
                 + ("did not predict the next month better than the regimes' own persistence, so the odds stay constant."
                    if worse and tv["choice"] == "constant" else
                    f"was tested; the model uses '{tv['choice']}'.") + "\n")
    mk = r.get("market")
    if mk:
        f6, s, st = mk["forwards"]["6m"], mk["spread"], mk["spread_test"]
        L.append(f"The forward market prices the rupee at {f6['forward']:.2f} in six months (premium {f6['premium']:.1f}% a year, "
                 f"{_month(f6['month'])}). The premium is {s['value']:+.1f} points over the policy-rate gap, higher than "
                 f"{s['percentile']:.0f}% of months since 2000: "
                 + ("a sign of hedging demand and expected depreciation beyond carry" if s["value"] > 0
                    else "dollars for later delivery are cheap relative to the rate gap")
                 + (". Historically the spread has not predicted the next month's move." if st["p"] >= 0.05 else
                    f". Historically a wider spread has preceded a {'weaker' if st['coef'] > 0 else 'stronger'} rupee the next month.")
                 + "\n")

    if "flows_diag" in r:
        L += flow_paragraph(r["flows_diag"])

    L.append("## How far to trust it\n")
    o = r["backtest"].get(r["headline_h"], {}).get("oos", {})
    if "rmse_ecm" in o:
        ratio, p = o["rmse_ratio_ecm_vs_drift"], o["clark_west"]["pvalue_one_sided"]
        if ratio < 1 and p < 0.05:
            verdict, sig = "beats a random walk with drift", "and the gain is statistically significant"
        elif ratio < 1:
            verdict = "has a slightly lower forecast error than a random walk with drift"
            sig = "but the difference is not statistically significant"
        else:
            verdict, sig = "does not beat a random walk with drift", "so it adds no forecasting value at this horizon"
        L.append(f"Out of sample ({_month(o['oos_window'][0])} to {_month(o['oos_window'][1])}), the misalignment signal {verdict} "
                 f"at a {r['headline_h']}-month horizon (forecast error ratio {ratio:.3f}, Clark-West p = {p:.2f}), {sig}. "
                 "Read the misalignment as a valuation gauge, not a timing signal.\n")
    caveats = []
    if not r["beer_diag"]["engle_granger"]["cointegrated_5pct"]:
        b, _ = _last(r["beer"]["misalignment_pct"])
        caveats.append(f"the market-based BEER ({_signed(b)}) fails its long-run test, so it is shown for context only")
    if not r["anchor_diag"]["engle_granger"]["cointegrated_5pct"]:
        caveats.append("the India-only REER model fails its long-run test")
    pdg = r.get("panel_diag", {})
    fc = pdg.get("specs", {}).get(pdg.get("central_spec"), {}).get("formal")
    if fc and fc.get("testable") and fc["p"]["group_adf"] < 0.05 <= fc["p_holm"]:
        caveats.append(f"the productivity anchor passes its long-run test (p {fc['p']['group_adf']:.3f}) but not once the "
                       f"{pdg['formal_family']['n_testable']} specifications tried are allowed for (p {fc['p_holm']:.2f}), "
                       "so its equilibrium is suggestive")
    if caveats:
        L.append("Also: " + "; ".join(caveats) + ".\n")
    nl = r.get("nonlinear")
    if nl:
        h = nl["horizon"]
        others = {k: v["by_horizon"][h]["rmse_ratio"] for k, v in nl["variants"].items() if k not in ("linear", "rolling")}
        lin = nl["variants"]["linear"]["by_horizon"][h]["rmse_ratio"]
        if others and all(v > lin for v in others.values()):
            s = ("Letting large gaps revert faster, or letting the adjustment drift, did not forecast better out of sample")
        else:
            s = "Nonlinear and time-varying versions of the forecast were also tested"
        s += (f"; a rolling 10-year estimate did ({nl['variants']['rolling']['by_horizon'][h]['rmse_ratio']:.3f}), "
              "but not robustly across window lengths, so the linear version stays."
              if nl["adopted"] == "linear" and nl["choice"] == "rolling" else ".")
        L.append(s + "\n")
    un = r.get("uncertainty")
    if un and un["latest"].get("p_undervalued") is not None:
        cb = un["coverage"].get("bootstrap", {})
        s = (f"Drawing all the uncertainties together (model parameters, the IMF norm, elasticities, data errors and "
             f"model weights), {un['latest']['p_undervalued']:.0%} of {un['draws']:,} draws say the rupee is undervalued.")
        if cb.get("coverage") is not None:
            s += (f" Looking back, this 80% range contained the later re-estimated fair value in {cb['coverage']:.0%} of "
                  "months" + ("; when it missed, the real-time reading had overstated the undervaluation"
                              if cb["below"] > 0 and cb["above"] == 0 else
                              "; when it missed, the real-time reading had understated the undervaluation"
                              if cb["above"] > 0 and cb["below"] == 0 else "") + ".")
        L.append(s + "\n")
    wt = r.get("weights")
    if wt:
        sc = wt["schemes"]
        h = wt["horizon"]
        L.append(f"The equal weighting of the two components was tested against weights learned from each one's track "
                 f"record and from their uncertainty bands; "
                 + ("none did clearly better, so the weights stay equal" if wt["rule_choice"] == "equal"
                    else f"the rule picks '{sc[wt['rule_choice']]['label']}'")
                 + (f". On their own, neither component beats a random walk at {h} months "
                    f"(ratios {sc['reer_only']['by_horizon'][h]['rmse_ratio']:.2f} and "
                    f"{sc['feer_only']['by_horizon'][h]['rmse_ratio']:.2f}); combined they do "
                    f"({sc['equal']['by_horizon'][h]['rmse_ratio']:.3f})"
                    if sc["reer_only"]["by_horizon"][h]["rmse_ratio"] > 1 and sc["feer_only"]["by_horizon"][h]["rmse_ratio"] > 1
                    and sc["equal"]["by_horizon"][h]["rmse_ratio"] < 1 else "")
                 + ". The headline ranges from "
                 f"{wt['headline_range'][0]:+.1f}% to {wt['headline_range'][1]:+.1f}% across weighting schemes.\n")
    pe = r.get("peers")
    if pe and pe.get("focus_rank"):
        im = (pe.get("imf") or {}).get("stats", {}).get("imf_reer_index")
        which = "the most" if pe["focus_rank"] == 1 else f"the {_ordinal(pe['focus_rank'])} most"
        s = (f"Among {pe['n']} emerging-market currencies on the same model, the rupee is {which} "
             f"undervalued ({_month(pe['month'])}).")
        if im:
            s += (f" Across countries the model ranks currencies much as the IMF's REER assessments do "
                  f"(average rank correlation {im['mean_rank_corr']:.2f}).")
        L.append(s + "\n")
    bm = r.get("benchmark")
    if bm:
        s = bm["stats"].get("composite_at_pub~imf_ca", {})
        lb = bm["latest"]
        if "same_sign" in s:
            L.append(f"Against the IMF's own assessments ({bm['first_year']}–{lb['analysis_year']}, its current-account "
                     f"model), this model pointed the same way in {s['same_sign'] * s['n']:.0f} of {s['n']} years and was "
                     f"{abs(s['mean_diff_pp']):.1f} points {'more' if s['mean_diff_pp'] > 0 else 'less'} undervalued on "
                     f"average when the IMF published. The IMF's latest ({lb['analysis_year']}) implies "
                     f"{lb['imf_ca']:+.1f}%.\n")
    rv = r.get("revisions")
    if rv:
        verdict = "matter little" if rv["max_abs_pp"] < 1 else "matter"
        L.append(f"Data revisions {verdict}: re-run on the earlier vintage of RBI data, the reading changes by at most "
                 f"{rv['max_abs_pp']:.1f} points in any month ({_month(rv['max_month'])}).\n")

    todo = [w for w in (gate_warnings or []) if "MOSPI" in w or "IMF CA norm" in w]
    stale = [w for w in r["warnings"] if w.startswith("Latest BoP quarter") or w.startswith("RBI INR/USD ends")]
    if todo or stale:
        L.append("## To do\n")
        L += [f"- {w}" for w in todo + stale]
        L.append("")

    if links:
        L.append("---\n")
        L.append(" · ".join(f"[{k}]({v})" for k, v in links.items()) + "\n")
    return "\n".join(L)
