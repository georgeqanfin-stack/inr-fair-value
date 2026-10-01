"""Markdown report, console dashboard and charts for a pipeline run."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .models.flows import LABELS as FLOW_LABELS


def _f(x, fmt="{:+.1f}", na="n/a"):
    try:
        return na if x is None or (isinstance(x, float) and np.isnan(x)) else fmt.format(x)
    except (TypeError, ValueError):
        return na


def _mon(ym: str) -> str:
    return pd.Timestamp(ym + "-01").strftime("%b %Y")


def _last(s: pd.Series):
    s = s.dropna()
    return (s.iloc[-1], s.index[-1].strftime("%b %Y")) if len(s) else (np.nan, "n/a")


def build_report(r: dict) -> str:
    ds, comp = r["dataset"], r["composite"]
    L = []
    asof = ds.asof
    spot = ds.pit.loc[asof, "inr_usd"]
    L.append("# INR/USD fair value: run report\n")
    L.append(f"inrfv {__version__} · run `{r['run_id']}` · as of **{asof:%b %Y}** (latest month with RBI INR/USD) · "
             f"spot **{spot:.2f}**\n")
    L.append("All figures are point-in-time: each value uses only data published by that month-end. "
             "Positive misalignment = INR undervalued (weaker than fair).\n")

    L.append("## Current reading\n")
    L.append("| Model | As of | Misalignment | Fair INR/USD | Notes |")
    L.append("|---|---|---|---|---|")
    fm, fq, fp = r["feer_m"], r["feer_q"], r["config"]["models"]["feer"]
    lo_c, hi_c = f"misalignment_p{min(fp['band_percentiles'])}", f"misalignment_p{max(fp['band_percentiles'])}"
    lastq = fm["quarter"].dropna().iloc[-1] if fm["quarter"].notna().any() else None
    qlabel = f"BoP {lastq:%b}–{lastq + pd.offsets.MonthBegin(2):%b %Y}" if lastq is not None else ""
    rows = [
        ("REER gap (one-sided HP)", r["reer"]["misalignment_pct"], r["reer"]["fair_inr"], "cyclical gauge; mean-reverting by construction"),
        ("REER panel anchor (EM panel)", r["panel"]["misalignment_pct"], r["panel"]["fair_inr"],
         f"productivity-based; BIS REER; spec '{r['panel_diag']['central_spec']}'"),
        ("REER fundamentals anchor", r["anchor"]["misalignment_pct"], r["anchor"]["fair_inr"],
         ("cointegrated" if r["anchor_diag"]["engle_granger"]["cointegrated_5pct"] else "**not cointegrated**: reported only")
         + ("; used in composite" if r["config"]["composite"].get("reer_component") == "anchor" else "")),
        ({"imf_path": "FEER, IMF norm path (central)", "imf": "FEER, fixed IMF norm (central)",
          "niip": "FEER, NIIP-stabilising norm (central)", "static": "FEER, legacy norm (central)"}[fp["central_norm"]],
         fm["misalignment_pct"], fm["fair_inr"],
         f"{qlabel}; {min(fp['band_percentiles'])}–{max(fp['band_percentiles'])}th pct {_f(_last(fm[lo_c])[0])}% to {_f(_last(fm[hi_c])[0])}%"),
        ("FEER, fixed IMF −2.0% norm", fm.get("misalignment_pct_imf", pd.Series(dtype=float)), None, "for comparison"),
        ("FEER, NIIP-stabilising norm", fm.get("misalignment_pct_niip", pd.Series(dtype=float)), None, "alternative norm"),
        ("FEER, legacy −2.5% norm", fm.get("misalignment_pct_static", pd.Series(dtype=float)), None, "v0.2 assumption, for comparison"),
        ("FEER conditional (experimental)", fm["misalignment_pct_conditional"], None, "ad hoc norm, not in composite"),
        ("BEER, current (real INR/USD, DOLS)", r["beer"]["misalignment_pct"], r["beer"]["fair_inr"],
         "cointegrated" if r["beer_diag"]["engle_granger"]["cointegrated_5pct"] else "**not cointegrated**: descriptive only"),
        ("BEER, total (permanent fundamentals)", r["beer"]["misalignment_total_pct"], r["beer"]["fair_inr_total"],
         "fundamentals at one-sided HP trend"),
        ("Composite (REER+FEER)", comp["misalignment_pct"], comp["fair_inr"], "drives the ECM"),
    ]
    for name, mis, fair, note in rows:
        v, d = _last(mis)
        fv = _f(_last(fair)[0], "{:.2f}") if fair is not None else "n/a"
        L.append(f"| {name} | {d} | {_f(v)}% | {fv} | {note} |")
    L.append("")
    if "fair_inr_strong" in comp:
        s_, w_ = _last(comp["fair_inr_strong"])[0], _last(comp["fair_inr_weak"])[0]
        what = ("joint bootstrap of panel parameters, FEER norm, elasticities, CA measurement and model weights"
                if comp.attrs.get("corridor") == "joint bootstrap" else "component bands joined end to end")
        L.append(f"**Fair-value corridor (10th–90th percentile; {what}): {_f(s_, '{:.2f}')} – {_f(w_, '{:.2f}')}** "
                 f"(central {_f(_last(comp['fair_inr'])[0], '{:.2f}')}, spot {spot:.2f}).\n")

    # FEER decomposition for the latest quarter, and a cross-check against the IMF.
    x = fq.dropna(subset=["misalignment_pct"]).iloc[-1]
    L.append("### FEER, latest quarter\n")
    L.append(f"Quarter from {x.name:%b %Y}, public {x['available']:%b %Y}: 4-quarter CA {x['ca_pct_4q']:+.2f}% of GDP; "
             f"oil adjustment {x['oil_adjustment']:+.2f}pp (net oil imports {_f(x['net_oil_pct_gdp'], '{:.2f}')}% of GDP, "
             f"Brent paid ${x['brent_paid']:.0f} vs 5-year norm ${x['brent_norm']:.0f}); underlying CA "
             f"{x['cad_underlying']:+.2f}%. Norms: IMF path {_f(x.get('norm_imf_path'), '{:+.1f}')}% "
             f"({x.get('norm_imf_path_source', 'n/a')}), fixed IMF {x['norm_imf']:+.1f}%, NIIP-stabilising "
             f"{_f(x['norm_niip'], '{:+.2f}')}%, legacy {x['norm_static']:+.1f}%. Semi-elasticity "
             f"{x['semi_elasticity']:.3f} pp/1% ({x['semi_source']}; X {_f(x['exports_pct_gdp'], '{:.1f}')}%, "
             f"M {_f(x['imports_pct_gdp'], '{:.1f}')}% of GDP).\n")
    fpar = r["config"]["models"]["feer"]
    if "cyclical_contribution" in x and pd.notna(x.get("cyclical_contribution")):
        L.append(f"Cyclical adjustment ({'applied' if fpar.get('cyclical_adjustment') else 'reported only'}): India's "
                 f"output gap {_f(x.get('output_gap_india'), '{:+.2f}')}% vs partners' {_f(x.get('output_gap_partners'), '{:+.2f}')}% "
                 f"(relative {x['output_gap_relative']:+.2f}pp) x EBA coefficient {fpar['cyclical_coefficient']} = "
                 f"{x['cyclical_contribution']:+.2f}pp of GDP from the cycle; underlying CA before it "
                 f"{x['cad_underlying_precyc']:+.2f}%. Income term ({'applied' if fpar.get('income_term') else 'off'}): net "
                 f"primary income {_f(x.get('income_pct_gdp'), '{:+.2f}')}% of GDP, foreign-currency share "
                 f"{fpar.get('income_fc_share')} (uniform 0-1 in the bands); trade-only semi-elasticity "
                 f"{x['semi_elasticity_trade']:.3f}.\n")
    pdg = r["panel_diag"]
    L.append("### REER panel anchor\n")
    L.append(f"REER component used in the composite: **{r['config']['composite'].get('reer_component', 'hp')}**. "
             "Panel dynamic OLS with country fixed effects, annual BIS broad REER, "
             f"{len(r['config']['panel']['countries'])} emerging markets, standard errors clustered by country; "
             "India's equilibrium = its country effect + pooled coefficients x its latest fundamentals.\n")
    L.append("| Spec | Years | n | Coefficients (t) | Panel coint. p | Countries rejecting | India p | India gap (last full year) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, s in pdg["specs"].items():
        coefs = ", ".join(f"{k} {s['coef'][k]:+.3f} ({s['t_cluster'][k]:+.1f}, exp. {s['expected_sign'][k]})"
                          for k in s["regressors"])
        c = s["panel_cointegration"]
        star = " (central)" if name == pdg["central_spec"] else ""
        L.append(f"| {name}{star} | {s['years'][0]}–{s['years'][1]} | {s['nobs']} | {coefs} | {c['pvalue']:.3f} | "
                 f"{c['share_rejecting_5pct']:.0%} | {_f(s['india_cointegration_p'], '{:.2f}')} | "
                 f"{s['india_latest_annual_gap_pct']:+.1f}% ({s['india_latest_reer_year']}) |")
    L.append(f"\nCoefficient range across {pdg['n_estimates']} point-in-time re-estimations since "
             f"{pdg['first_estimate']}: " + ", ".join(f"{k} {v[0]:+.2f} to {v[1]:+.2f}" for k, v in pdg["coef_path"].items())
             + ". Twelve specifications were compared when this model was built; only productivity-only DOLS "
             "passed the panel check, so treat the cointegration result as suggestive. Net foreign assets "
             "(External Wealth of Nations) were tested later and are shown as `prod_nfa`: insignificant, "
             "wrong sign, and adding them breaks the panel check.\n")
    ff = pdg.get("formal_family")
    if ff:
        L.append("**Formal panel cointegration tests.** 'Panel coint. p' above is a Fisher combination of per-country "
                 "ADF tests on the pooled (common-slope) residuals. The tests below allow each country its own slope "
                 "(Pedroni-type group and panel ADF on country-by-country cointegrating regressions; Westerlund Gt and "
                 f"Pt error-correction tests), with p-values from {ff['reps']} bootstrap panels generated under no "
                 "cointegration (years resampled jointly across countries). The primary statistic is the group ADF: in a "
                 "Monte Carlo (scripts/mc_panel_coint.py) it rejected 5% of non-cointegrated panels at the 5% level, "
                 "while the Westerlund bootstrap rejected 15-18%, so Westerlund p-values here are too low.\n")
        L.append(f"Search family: every specification containing relative productivity ({ff['n_specs']} specs, "
                 f"{ff['n_testable']} with enough years). {ff['n_pass_raw']} pass at 5% before adjustment. Holm controls "
                 "the chance of any false pass; Benjamini-Hochberg (BH) the share of false passes.\n")
        L.append("| Specification | Years | Group ADF p | Holm | BH | Panel ADF p | Westerlund Gt p | Pt p | Fisher (pooled slope) |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        fisher = {frozenset(s["regressors"]): s["panel_cointegration"]["pvalue"] for s in pdg["specs"].values()}
        for name, v in ff["specs"].items():
            fz = fisher.get(frozenset(v["regressors"]))
            fz = f"{fz:.3f}" if fz is not None else "—"
            if not v.get("testable"):
                L.append(f"| {name.replace('+', ' + ')} | — | too few years | | | | | | {fz} |")
                continue
            pv = v["p"]
            L.append(f"| {name.replace('+', ' + ')} | {v['years']} | {pv['group_adf']:.3f} | {v['p_holm']:.2f} | "
                     f"{v['p_bh']:.2f} | {pv['panel_adf']:.3f} | {pv['Gt']:.3f} | {pv['Pt']:.3f} | {fz} |")
        cen = pdg["specs"][pdg["central_spec"]].get("formal")
        if cen and cen.get("testable"):
            L.append(f"\nCentral specification: group ADF p {cen['p']['group_adf']:.3f}; after the search, Holm "
                     f"{cen['p_holm']:.2f} and BH {cen['p_bh']:.2f}. Country-by-country cointegration with productivity is "
                     "broadly supported; the common slope the anchor imposes, and the central specification's p-value "
                     "after accounting for the search, are suggestive rather than conclusive.\n")

    bd = r["beer_diag"]
    L.append("### BEER (bilateral, real INR/USD)\n")
    L.append("Real INR/USD with PPP imposed, regressed by dynamic OLS on long-run fundamentals; expanding "
             f"window, first estimate {bd['first_estimate']}. Current BEER uses today's fundamentals; total BEER "
             "uses their one-sided HP trends.\n")
    L.append("| Spec | Sample | n | Coefficients (t, expected sign) | Engle-Granger p | Johansen rank |")
    L.append("|---|---|---|---|---|---|")
    for name, s in bd["specs"].items():
        coefs = ", ".join(f"{k} {s['coef'][k]:+.3f} ({s['t_hac'][k]:+.1f}, {s['expected_sign'][k]})" for k in s["regressors"])
        star = " (central)" if name == bd["central_spec"] else ""
        L.append(f"| {name}{star} | {s['sample'][0]}–{s['sample'][1]} | {s['nobs']} | {coefs} | "
                 f"{s['engle_granger']['pvalue']:.3f} | {s['johansen_rank']} |")
    L.append("\nCoefficient range across re-estimations: "
             + ", ".join(f"{k} {v[0]:+.2f} to {v[1]:+.2f}" for k, v in bd["coef_path"].items()) + ".\n")
    L.append("Does the BEER gap predict INR/USD? (same out-of-sample test as the composite)\n")
    L.append("| h | OOS window | n | RMSE ratio vs drift | Clark-West p | α range |")
    L.append("|---|---|---|---|---|---|")
    for h, o in bd["oos"].items():
        if "rmse_ecm" in o:
            L.append(f"| {h} | {o['oos_window'][0]}–{o['oos_window'][1]} | {o['n_oos']} | "
                     f"{o['rmse_ratio_ecm_vs_drift']:.3f} | {o['clark_west']['pvalue_one_sided']:.3f} | "
                     f"{o['alpha_min']:+.2f} to {o['alpha_max']:+.2f} |")
    if not bd["engle_granger"]["cointegrated_5pct"]:
        L.append("\nReading: the dollar and productivity coefficients are large, significant and correctly signed, "
                 "but the real rate is not cointegrated with them, so the BEER gap describes where fundamentals would "
                 "put the rupee, not a level it reliably returns to.\n")

    a = r["anchor_diag"]
    L.append("### REER fundamentals anchor (India only)\n")
    sig = lambda k: f"{a['coef'][k]:+.3f} (t {a['t_hac'][k]:+.1f}, expected {a['expected_sign'][k]})"
    L.append(f"Dynamic OLS, {a['sample'][0]}–{a['sample'][1]}, n={a['nobs']}: log REER on relative productivity "
             f"{sig('rel_prod')}, log terms of trade {sig('log_tot')}, NFA/GDP {sig('nfa_gdp')}. "
             f"Engle-Granger p = {a['engle_granger']['pvalue']:.2f} (5% critical {a['engle_granger']['crit_5pct']:.2f}). "
             "Range of each coefficient across the quarterly re-estimations since "
             f"{a.get('first_estimate', 'n/a')}: " + ", ".join(
                 f"{k} {v[0]:+.2f} to {v[1]:+.2f}" for k, v in a.get("coef_path", {}).items())
             + f". NFA source quarters: {a['nfa_sources']}.\n")
    if not a["engle_granger"]["cointegrated_5pct"]:
        L.append("Reading: India's productivity relative to the world has more than doubled since 2005 while the "
                 "REER stayed within a narrow range, so the fundamentals do not pin down the REER level over this "
                 "sample (consistent with a managed exchange rate). The anchor's misalignment is therefore not "
                 "used in the composite unless `[composite] reer_component = \"anchor\"`.\n")

    imf_q = pd.Timestamp("2025-01-01")          # quarter closing FY2024/25
    if imf_q in fq.index:
        y = fq.loc[imf_q]
        L.append(f"Cross-check, FY2024/25: this model's CA {y['ca_pct_4q']:+.2f}% and underlying CA "
                 f"{y['cad_underlying']:+.2f}% vs the IMF's {-0.6:+.1f}% actual and {-0.4:+.1f}% cyclically adjusted "
                 f"(2025 Article IV); misalignment {y['misalignment_pct']:+.1f}% "
                 f"(IMF: external position \"moderately stronger\" than fundamentals).\n")

    g = r["regime_summary"]
    L.append("## Regime\n")
    L.append(f"Filtered P(stress) = **{g['p_stress_now']:.2f}** ({g['p_stress_now_date']}), "
             f"steady state {g['p_stress_steady_state']:.2f}. Forward: " +
             ", ".join(f"{h}m {v:.2f}" for h, v in g["p_stress_forecast"].items()) + ".")
    L.append(f"Calm: mean {g['calm']['mean_pct']:+.2f}%/mo, sd {g['calm']['sd_pct']:.2f}%, "
             f"duration {g['calm']['expected_duration_m']:.1f}m. "
             f"Stress: mean {g['stress']['mean_pct']:+.2f}%/mo, sd {g['stress']['sd_pct']:.2f}%, "
             f"duration {g['stress']['expected_duration_m']:.1f}m.\n")
    q, qd = _last(r["regimes"]["oil_dxy_quadrant"])
    L.append(f"Oil × DXY quadrant (expanding medians): {q} ({qd}).\n")
    tv = g.get("tvtp")
    if tv:
        L.append("### Time-varying transition probabilities\n")
        L.append(f"Switching odds driven by last month's VIX change, Brent change, FPI flows and RBI intervention "
                 f"(standardised, point in time), against the constant-probability model. Full sample "
                 f"{_mon(tv['sample'][0])}–{_mon(tv['sample'][1])}; out of sample {_mon(tv['oos_window'][0])}–"
                 f"{_mon(tv['oos_window'][1])}: one-step-ahead predictive log score of the monthly return, parameters "
                 f"re-estimated yearly; t-test on the log-score difference (Newey-West); AUC of the predicted stress "
                 f"probability for months with the largest 20% of moves. Rule set beforehand: switch only if a "
                 f"specification beats the constant model out of sample with one-sided p < {tv['switch_p']}.\n")
        L.append("| Transition drivers | Log-lik. | AIC | BIC | LR p | OOS log score | vs constant | t | p | AUC big moves |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for n, f in tv["full_sample"].items():
            o = tv["oos"][n]
            drv = ", ".join(tv["specs"][n]["drivers"]) or "none (constant)"
            lrp = f"{f['lr_p']:.2f}" if "lr_p" in f else "—"
            tt = f"{o['t']:+.2f}" if o["p_one_sided"] is not None else "—"
            pp = f"{o['p_one_sided']:.2f}" if o["p_one_sided"] is not None else "—"
            L.append(f"| {drv} | {f['loglik']:.1f} | {f['aic']:.1f} | {f['bic']:.1f} | {lrp} | {o['mean_log_score']:.4f} | "
                     f"{o['diff_vs_constant']:+.4f} | {tt} | {pp} | {o['auc_big_moves']:.2f} |")
        L.append(f"\nChoice: **{tv['choice']}**.\n")

    mk = r.get("market")
    if mk:
        L.append("## Market pricing (forward premia)\n")
        f3, f6 = mk["forwards"]["3m"], mk["forwards"]["6m"]
        L.append(f"RBI inter-bank forward premia, monthly average (% a year), {_mon(f3['month'])}: 3-month "
                 f"{f3['premium']:.2f}%, 6-month {f6['premium']:.2f}%. Implied forwards on the {_mon(mk['asof'])} spot "
                 f"{mk['spot']:.2f}: 3-month {f3['forward']:.2f}, 6-month {f6['forward']:.2f}.\n")
        s = mk["spread"]
        L.append(f"Premium over the policy-rate gap (3-month premium − (India policy rate − Fed funds)): "
                 f"{s['value']:+.2f} pp in {_mon(s['month'])}, above {s['percentile']:.0f}% of months since 2000 "
                 f"(mean {s['mean']:+.2f}, sd {s['sd']:.2f}). A high spread means dollars for future delivery cost more "
                 "than the rate gap justifies: hedging demand and expected depreciation beyond carry.\n")
        st = mk["spread_test"]
        L.append(f"Does the spread predict next month's rupee move? Coefficient {st['coef']:+.3f}% per pp (t {st['t']:+.1f}); "
                 f"controlling for next month's dollar move {st['coef_given_dxy']:+.3f} (t {st['t_given_dxy']:+.1f}).\n")
        L.append("| UIP test | Sample | n | Slope (UIP = 1) | t vs 0 | t vs 1 | R² |")
        L.append("|---|---|---|---|---|---|---|")
        for k, u in mk["uip"].items():
            L.append(f"| {k} premium → {u['h']}-month depreciation | {u['sample'][0]}–{u['sample'][1]} | {u['nobs']} | "
                     f"{u['slope']:.2f} (se {u['se']:.2f}) | {u['t_vs_0']:+.1f} | {u['t_vs_1']:+.1f} | {u['r2']:.3f} |")
        L.append("")

    fd = r["flows_diag"]
    L.append("## Flow attribution (what moved the spot rate)\n")
    L.append(f"Monthly INR/USD % change regressed on net FPI and FDI flows (US$ bn), dollar-index and Brent "
             f"% changes, {fd['sample'][0]} to {fd['sample'][1]} (n = {fd['nobs']}, R² {fd['r2']:.2f}, "
             "Newey-West t). Ex post, by reference month; it explains spot moves and does not enter the fair value. "
             "Positive = rupee weaker.\n")
    L.append("| Term | Coefficient | t | Meaning |")
    L.append("|---|---|---|---|")
    meaning = {"const": "average monthly depreciation (drift)", "fpi": "% per US$1bn of net FPI inflow",
               "fdi": "% per US$1bn of net FDI inflow", "dxy": "% per 1% dollar-index rise",
               "brent": "% per 1% Brent rise"}
    for k in ["const"] + fd["regressors"]:
        L.append(f"| {k} | {fd['coef'][k]:+.3f} | {fd['t'][k]:+.1f} | {meaning.get(k, '')} |")
    labels = " | ".join(FLOW_LABELS.get(k, k) for k in fd["regressors"])
    L.append(f"\n| Window | Actual | {labels} | Drift | Residual | FPI, fitted without the window |")
    L.append("|---|---|" + "---|" * (len(fd["regressors"]) + 3))
    for w in fd["windows"].values():
        o = w["out_of_window"]
        L.append(f"| {_mon(w['start'])}–{_mon(w['end'])} | {w['actual']:+.1f}% | "
                 + " | ".join(f"{w[k]:+.1f}" for k in fd["regressors"])
                 + f" | {w['drift']:+.1f} | {w['residual']:+.1f} | {o['fpi']:+.1f} |")
    dr = fd["direction"]
    a, b = dr["fpi_predicts_next_inr"], dr["inr_predicts_next_fpi"]
    L.append(f"\nDirection: FPI this month → INR next month t {a['t']:+.1f} (p {a['p']:.3f}); INR last month → "
             f"FPI this month t {b['t']:+.1f} (p {b['p']:.3f}). Reading: {dr['reading']}. Flow data end "
             f"{_mon(fd['latest_flows_month'])}.\n")
    fi = fd.get("identification")
    if fi:
        L.append("### Identifying the flow effect\n")
        L.append(f"Monthly, {_mon(fi['sample'][0])}–{_mon(fi['sample'][1])} (n = {fi['n']}; one standard deviation of net "
                 f"FPI = US${fi['fpi_sd_bn']:.1f} bn). Per US$1 bn of net inflow, % change of INR/USD (negative = rupee "
                 "stronger). Ordering A treats the same-month co-movement as flows moving the rupee; ordering B as the "
                 "rupee moving flows (impact zero by construction). Both condition on same-month VIX, US 10-year yield and "
                 "dollar-index changes and on two lags of every variable. Local projections give the cumulative effect h "
                 "months out (Newey-West errors).\n")
        hs = [r["h"] for r in fi["ordering_a"]]
        L.append("| Method | " + " | ".join(f"h={h}" for h in hs) + " |")
        L.append("|---|" + "---|" * len(hs))
        for key, lab in (("ordering_a", "Ordering A (flows → rupee)"), ("ordering_b", "Ordering B (rupee → flows)")):
            L.append(f"| {lab} | " + " | ".join(
                "0 (by construction)" if r.get("note") else f"{r['beta']:+.3f} (t {r['t']:+.1f})" for r in fi[key]) + " |")
        ivr = fi["iv"]
        jp = f", Hansen J p {ivr['J_p']:.2f}" if ivr.get("J_p") is not None else ""
        L.append(f"\nInstrumental variables (2SLS; instruments: changes in {', '.join(fi['settings']['instruments'])}; "
                 f"controls: dollar index, Brent, FDI, lags): {ivr['beta']:+.3f} (se {ivr['se']:.3f}, t {ivr['t']:+.1f}); "
                 f"first-stage F {ivr['first_stage_F']:.1f}{jp}. Exclusion (global push shocks reach the rupee only "
                 f"through portfolio flows, given the dollar) cannot be tested and is a strong assumption.\n")
        if fi.get("ols_beta"):
            ratio = ivr["beta"] / fi["ols_beta"]
            w0 = fd["windows"][min(fd["windows"], key=int)]
            L.append(f"Reading: the same-month estimate used in the attribution ({fi['ols_beta']:+.3f}) equals ordering A's "
                     f"impact, the upper end of the identified range (0 to {fi['impact_bounds'][0]:+.3f}); the IV estimate is "
                     f"{ratio:.0%} of it. On the IV estimate, portfolio flows would account for {w0['fpi'] * ratio:+.1f} "
                     f"points of the {_mon(w0['start'])}–{_mon(w0['end'])} move instead of {w0['fpi']:+.1f}, and the RBI's "
                     f"absorbed pressure would scale down in the same proportion.\n")
    iv = fd.get("rbi")
    if iv:
        rc = iv["reaction"]
        L.append("### RBI intervention\n")
        L.append("RBI Bulletin Table 4: spot net purchases plus the change in the outstanding forward book (US$ bn; "
                 "negative = net dollar sales). Intervention is not a regressor: the RBI sells because the rupee is "
                 f"under pressure, and a direct regression finds {iv['naive_coef']:+.3f}% per US$1bn (t {iv['naive_t']:+.1f}). "
                 f"Reaction function: the RBI buys {rc['coef']['fpi']:+.2f} bn per US$1bn of net FPI inflow "
                 f"(t {rc['t']['fpi']:+.1f}) and {rc['coef']['inr']:+.2f} bn per 1% rupee depreciation "
                 f"(t {rc['t']['inr']:+.1f}); R² {rc['r2']:.2f}.\n")
        L.append(f"Absorbed pressure values each dollar the RBI sold at the market price implied by the FPI coefficient "
                 f"({iv['price_pct_per_bn']:.3f}% per US$1bn). That coefficient is net of the RBI's usual response, "
                 "so the absorbed share is a lower bound; it scales linearly with the price.\n")
        L.append("| Window | RBI net sales | Actual move | Held stronger by | Move without RBI | Share absorbed |")
        L.append("|---|---|---|---|---|---|")
        for w in iv["windows"].values():
            sh = f"{w['absorbed_share']:.0%}" if w["absorbed_share"] is not None else "n/a"
            L.append(f"| {_mon(w['start'])}–{_mon(w['end'])} | US${w['net_sold_bn']:.1f} bn | {w['actual']:+.1f}% | "
                     f"{w['absorbed']:+.1f} pts | {w['pressure']:+.1f}% | {sh} |")
        bp = f" ({iv['fwd_book_pct_reserves']:.0f}% of FX reserves)" if iv["fwd_book_pct_reserves"] is not None else ""
        L.append(f"\nOutstanding net forward position, {_mon(iv['fwd_book_month'])}: US${iv['fwd_book_bn']:.1f} bn{bp}. "
                 f"Latest month of intervention data: {_mon(iv['latest_month'])} (US${iv['latest_bn']:+.1f} bn).\n")

    L.append("## Out-of-sample backtest (ECM vs random walk with drift)\n")
    L.append("| h | OOS window | n | RMSE ratio | OOS R² | Clark-West p | DM p | hit ECM | hit naive 'depreciate' | hit vs drift | α range |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for h, res in r["backtest"].items():
        o = res["oos"]
        if "rmse_ecm" not in o:
            L.append(f"| {h} | — | {o.get('n_oos', 0)} | insufficient data | | | | | | | |")
            continue
        L.append(f"| {h} | {o['oos_window'][0]}–{o['oos_window'][1]} | {o['n_oos']} | "
                 f"{o['rmse_ratio_ecm_vs_drift']:.3f} | {o['oos_r2_vs_drift']:+.3f} | "
                 f"{o['clark_west']['pvalue_one_sided']:.3f} | {o['diebold_mariano']['pvalue_two_sided']:.3f} | "
                 f"{o['hit_rate_ecm_sign']:.0%} | {o['hit_rate_naive_depreciation']:.0%} | "
                 f"{o['hit_rate_excess_over_drift']:.0%} | {o['alpha_min']:+.2f} to {o['alpha_max']:+.2f} |")
    L.append("\nRMSE ratio < 1 and Clark-West p < 0.05 would mean the ECT beats the drift benchmark. "
             "'hit vs drift' asks whether the model gets the direction of the surprise relative to drift right.\n")

    wt = r.get("weights")
    if wt:
        hh = wt["horizon"]
        L.append("### Composite weights\n")
        L.append(f"Weighting schemes for the REER component and the FEER, all point in time, through the same backtest. "
                 f"Rule set beforehand: keep equal weights unless a scheme lowers the {hh}-month RMSE ratio by at least "
                 f"{wt['rule']['min_rmse_gain']} and has a lower Clark-West p. The rule chooses: **{wt['rule_choice']}** "
                 f"(configured: {wt['configured']}). Headline misalignment across the combination schemes: "
                 f"{wt['headline_range'][0]:+.1f}% to {wt['headline_range'][1]:+.1f}%.\n")
        hs = list(next(iter(wt["schemes"].values()))["by_horizon"])
        L.append("| Scheme | REER weight (latest, mean) | Misalignment now | "
                 + " | ".join(f"{k}m RMSE ratio (CW p)" for k in hs) + " |")
        L.append("|---|---|---|" + "---|" * len(hs))
        for v in wt["schemes"].values():
            cells = " | ".join(f"{x['rmse_ratio']:.3f} ({x['cw_p']:.2f})" if x["rmse_ratio"] is not None else "n/a"
                               for x in v["by_horizon"].values())
            L.append(f"| {v['label']} | {v['weight_reer_last']:.2f}, {v['weight_reer_mean']:.2f} | "
                     f"{v['misalignment_last']:+.1f}% | {cells} |")
        L.append("")

    nl = r.get("nonlinear")
    if nl:
        hh = nl["horizon"]
        L.append("### Nonlinear and time-varying adjustment\n")
        L.append(f"Each variant is re-estimated point in time like the headline ECM and scored the same way. Rule set "
                 f"before testing: replace the linear ECM only if a variant lowers the {hh}-month RMSE ratio by at least "
                 f"{nl['rule']['min_rmse_gain']} and has a lower Clark-West p.\n")
        hs = list(nl["variants"]["linear"]["by_horizon"])
        L.append("| Variant | " + " | ".join(f"{k}m RMSE ratio (CW p)" for k in hs) + " |")
        L.append("|---|" + "---|" * len(hs))
        for v in nl["variants"].values():
            L.append(f"| {v['label']} | " + " | ".join(
                f"{x['rmse_ratio']:.3f} ({x['cw_p']:.2f})" if x["rmse_ratio"] is not None else "n/a"
                for x in v["by_horizon"].values()) + " |")
        lp = nl["last_params"]
        th, cu = lp.get("threshold", {}), lp.get("cubic", {})
        L.append(f"\nLatest fits: threshold |gap| {th.get('c', float('nan')):.3f} log points, slope inside "
                 f"{th.get('b_in', float('nan')):+.2f} and outside {th.get('b_out', float('nan')):+.2f}; cubic term "
                 f"{cu.get('g', float('nan')):+.2f} (negative would mean faster reversion of large gaps).\n")
        rb = nl["rolling_robustness"]
        L.append(f"Rolling window, {hh}-month ratio by window length: "
                 + ", ".join(f"{w} months {v['rmse_ratio']:.3f} (p {v['cw_p']:.2f})" for w, v in rb.items())
                 + f"; median {nl['rolling_median_ratio']:.3f}. The rule's choice: **{nl['choice']}**. Adopted: "
                 f"**{nl['adopted']}**"
                 + ("" if nl["adopted"] == nl["choice"] else
                    " (the rolling window passes at its pre-set length but not at the median of nearby lengths; this "
                    "robustness requirement was added after the first results)")
                 + ". `[backtest] window_months` switches the headline ECM to a rolling window.\n")
        L.append("Structural breaks (sup-Wald, 15% trimming, block-bootstrap p; a second break is tested on the larger "
                 "segment when the first is significant):\n")
        L.append("| Series | Sample | Break | sup-F | p | Before | After |")
        L.append("|---|---|---|---|---|---|---|")
        for v in nl["breaks"].values():
            for t in v["tests"]:
                fmt_ = lambda xs: ", ".join(f"{x:+.3f}" if abs(x) < 1 else f"{x:+.1f}" for x in xs)
                L.append(f"| {v['label']} | {t['sample'][0]}–{t['sample'][1]} | {_mon(t['date'])} | {t['stat']:.1f} | "
                         f"{t['p']:.3f} | {fmt_(t['before'])} | {fmt_(t['after'])} |")
        L.append("")

    un = r.get("uncertainty")
    if un:
        lt = un["latest"]
        L.append("### Joint uncertainty (bootstrap corridor)\n")
        L.append(f"{un['draws']} joint draws a month of: the panel slope and India's effect (country-block bootstrap, "
                 f"{un['panel_boot_draws']} draws per re-estimation), the IMF norm (its standard error), the trade "
                 f"elasticities (±{r['config']['models']['feer']['eta_uncertainty']:.0%}), current-account measurement error "
                 f"(sd {r['config']['uncertainty']['ca_measurement_sd']} pp of GDP) and the weighting scheme (equal, performance "
                 f"or inverse variance). {_mon(lt['month'])}: fair value {lt['fair_strong']:.2f}–{lt['fair_weak']:.2f} "
                 f"(misalignment {lt['mis_lo']:+.1f}% to {lt['mis_hi']:+.1f}%); {lt['p_undervalued']:.0%} of draws say "
                 f"undervalued. End-to-end band: {lt['old_strong']:.2f}–{lt['old_weak']:.2f}. Headline corridor: "
                 f"**{un['headline'].replace('_', ' ')}**.\n")
        if un["expost_window"]:
            L.append(f"Coverage against the fair value as later re-estimated ({_mon(un['expost_window'][0])}–"
                     f"{_mon(un['expost_window'][1])}: final panel coefficients; the IMF's own norm for each year), "
                     "nominal 80%:\n")
            L.append("| Corridor | Months | Coverage | Ex-post below band | Ex-post above band | Median width |")
            L.append("|---|---|---|---|---|---|")
            for name, c in un["coverage"].items():
                L.append(f"| {name.replace('_', ' ')} | {c['n']} | {c['coverage']:.0%} | {c['below']:.0%} | "
                         f"{c['above']:.0%} | {c['median_width_pct']:.1f} pp |")
            L.append("\nMonths overlap heavily (about one independent observation a year), so coverage is measured "
                     "roughly. Misses below the band mean the real-time reading overstated undervaluation relative to the "
                     "later estimate. The bootstrap corridor was made the headline after this test, as the one closer to "
                     "nominal coverage.\n")

    L.append("### Full-sample predictive regressions\n")
    L.append("| h | β (Hodrick) | t (Hodrick 1B) | p | non-overlapping β median [min, max] | t median |")
    L.append("|---|---|---|---|---|---|")
    for h, res in r["backtest"].items():
        hd, no = res["in_sample"]["hodrick"], res["in_sample"]["non_overlapping"]
        L.append(f"| {h} | {hd['beta']:+.3f} | {hd['t_hodrick']:+.2f} | {hd['pvalue']:.3f} | "
                 f"{_f(no.get('beta_median'), '{:+.3f}')} [{_f(no.get('beta_min'), '{:+.2f}')}, {_f(no.get('beta_max'), '{:+.2f}')}] | "
                 f"{_f(no.get('t_median'), '{:+.2f}')} |")
    rc = r["backtest"].get(r["headline_h"], {}).get("in_sample", {}).get("regime_conditional")
    if rc:
        L.append(f"\nRegime-conditional (h={r['headline_h']}, filtered P(stress)): "
                 f"α_calm {rc['coef']['ect_calm']:+.3f} (p={rc['pvalues_nw']['ect_calm']:.3f}), "
                 f"α_stress {rc['coef']['ect_stress']:+.3f} (p={rc['pvalues_nw']['ect_stress']:.3f}).\n")

    cf = r["current_forecast"]
    L.append("## Current ECM forecast\n")
    L.append(f"h={cf['h']}m from {cf['asof']}: ECT {cf['ect']:+.3f}, α {cf['alpha']:+.3f}, const {cf['const']:+.3f} → "
             f"predicted Δlog INR {cf['forecast_log_change']*100:+.1f}% (drift alone {cf['drift_only']*100:+.1f}%). "
             "Estimated on all realised targets; only as credible as the backtest above.\n")

    bm = r.get("benchmark")
    if bm:
        L.append("## External benchmark: the IMF's assessments of India\n")
        L.append("IMF External Balance Assessment for each year (published with the following year's External Sector "
                 "Report), on this report's sign convention (positive = rupee undervalued). The IMF CA model's REER "
                 "equivalent is CA gap / semi-elasticity; IMF staff assessments rest mainly on it. Our columns: the "
                 "average of this model's point-in-time readings over the year assessed, and the reading in the month "
                 "the IMF published. Our FEER uses the IMF's published norms, so the FEER-vs-IMF-CA pairing is not "
                 "independent.\n")
        L.append("| Year | IMF published | IMF CA gap (% GDP) | IMF CA model | IMF REER index | IMF REER level | "
                 "Our FEER (year) | Our REER comp. (year) | Our composite (year) | Our composite (at publication) |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for t in bm["table"]:
            L.append(f"| {t['analysis_year']} | {_mon(t['published'])} | {t['ca_gap']:+.1f} | {t['imf_ca']:+.1f}% | "
                     f"{t['imf_reer_index']:+.1f}% | {t['imf_reer_level']:+.1f}% | {t['feer_year']:+.1f}% | "
                     f"{t['reer_year']:+.1f}% | {t['composite_year']:+.1f}% | {t['composite_at_pub']:+.1f}% |")
        L.append("\n| Ours vs IMF | When | n | Same sign | Correlation | Mean difference (ours − IMF) | Mean absolute difference |")
        L.append("|---|---|---|---|---|---|---|")
        for s in bm["stats"].values():
            if "corr" in s:
                L.append(f"| {s['ours']} vs {s['imf']} | {'year average' if s['when'] == 'year' else 'at publication'} | "
                         f"{s['n']} | {s['same_sign']:.0%} | {s['corr']:+.2f} | {s['mean_diff_pp']:+.1f} pp | "
                         f"{s['mean_abs_diff_pp']:.1f} pp |")
        L.append("")

    pe = r.get("peers")
    if pe:
        L.append("## Peer currencies (panel REER anchor)\n")
        L.append(f"Every panel currency's REER misalignment from the same pooled fit, {_mon(pe['month'])} "
                 f"(+ = undervalued; relative to each currency's own history, so rankings and movements matter "
                 f"more than levels). India ranks **{pe['focus_rank']} of {pe['n']}** (1 = most undervalued); "
                 f"median {pe['median']:+.1f}%.\n")
        L.append("| Rank | Currency | Misalignment |")
        L.append("|---|---|---|")
        for i, (c, v) in enumerate(pe["latest"].items(), 1):
            star = " **(India)**" if c == pe["focus"] else ""
            L.append(f"| {i} | {c}{star} | {v:+.1f}% |")
        if pe["episodes"]:
            ok = sum(e["pass"] for e in pe["episodes"])
            L.append(f"\nKnown episodes (fixed in the config before looking at results): {ok} of "
                     f"{len(pe['episodes'])} move the expected way.\n")
            L.append("| Currency | Episode | Before | After | Expected | Result |")
            L.append("|---|---|---|---|---|---|")
            for e in pe["episodes"]:
                L.append(f"| {e['country']} | {e['label']} | {e['before_mean']:+.1f}% ({e['before'][0]}–{e['before'][1]}) | "
                         f"{e['after_mean']:+.1f}% ({e['after'][0]}–{e['after'][1]}) | {e['expect']} | "
                         f"{'as expected' if e['pass'] else 'not as expected'} |")
        im = pe.get("imf")
        if im:
            L.append(f"\nAgainst the IMF's EBA assessments of {len(im['countries'])} panel currencies "
                     f"({im['years'][0]}–{im['years'][1]}; IMF signs flipped to + = undervalued):\n")
            L.append("| IMF measure | n | Pooled correlation | Same sign | Rank correlation within a year (mean, min) | "
                     "Correlation within a country over time |")
            L.append("|---|---|---|---|---|---|")
            for s in im["stats"].values():
                L.append(f"| {s['label']} | {s['n']} | {s['pooled_corr']:+.2f} | {s['same_sign']:.0%} | "
                         f"{s['mean_rank_corr']:+.2f}, {s['min_rank_corr']:+.2f} | {s['within_country_corr']:+.2f} |")
            L.append("\nThe panel anchor is a REER model; it agrees closely with the IMF's REER models. The IMF's CA model "
                     "and its REER models disagree with each other across countries, so no REER model matches both.\n")

    rv = r.get("revisions")
    L.append("## Data revisions\n")
    if rv:
        lv = rv["last"]
        L.append(f"The headline was re-run on the earlier RBI vintage ({rv['older_vintage']['source']}, ending "
                 f"{', '.join(_mon(e) for e in rv['older_vintage']['ends'])}), preferring it wherever both vintages "
                 f"have a value. Series revised beyond the 0.5% tolerance: "
                 f"{', '.join(rv['older_vintage']['series_revised_beyond_tolerance']) or 'none'}.\n")
        L.append(f"Point-in-time composite readings changed in {rv['n_changed']} of {rv['n_months']} months "
                 f"({_mon(rv['months'][0])}–{_mon(rv['months'][1])}): mean absolute change {rv['mean_abs_pp']:.3f} pp, "
                 f"largest {rv['max_abs_pp']:.2f} pp ({_mon(rv['max_month'])}); by component, REER "
                 f"{rv['by_component_mean_abs_pp']['reer']:.3f} pp and FEER {rv['by_component_mean_abs_pp']['feer']:.3f} pp "
                 f"on average. Latest common month {_mon(lv['month'])}: {lv['early']:+.2f}% on the earlier vintage, "
                 f"{lv['current']:+.2f}% now. This is a lower bound on the revision effect (the earlier files are "
                 "themselves partly revised); `python -m inrfv.vintages run <git-rev>` re-runs any committed vintage.\n")
    else:
        L.append("Revision check not run (needs `[dbie] mode = \"merge\"` and DBIE Excel files).\n")
    cv = ds.meta.get("cpi_us_vintage")
    if isinstance(cv, str):
        L.append(f"US CPI inflation: {cv}.\n")
    elif cv:
        L.append(f"US CPI inflation: {cv['source']} from {_mon(cv['from'])}; versus the revised series the "
                 f"mean absolute difference is {cv['mean_abs_diff_pp']:.3f} pp (largest {cv['max_abs_diff_pp']:.2f} pp).\n")

    L.append("## Diagnostics\n")
    eg = r["beer_diag"]["engle_granger"]
    L.append(f"- BEER Engle-Granger ({eg['n_vars']} vars, n={eg['nobs']}): stat {eg['stat']:.2f}, "
             f"5% critical {eg['crit_5pct']:.2f}, p = {eg['pvalue']:.3f}.")
    for name, j in r["johansen"].items():
        L.append(f"- Johansen {name}: rank {j['rank']} of {j['n_vars']} (sequential trace, 5%, k_ar_diff={j['k_ar_diff']}, n={j['nobs']}).")
    m = ds.meta
    seam = m["dxy_seam"]
    L.append(f"- DXY splice: ratio {m['dxy_splice_ratio']:.4f}; log change at seam {seam['month']}: {seam['log_change_pct']:+.2f}%.")
    s = m["cpi_india_splice"]
    if s.get("method") == "official":
        seg = "; ".join(f"{k} {v[0]}–{v[1]}" for k, v in s["segments"].items())
        v = s.get("vs_oecd_yoy", {})
        L.append(f"- India CPI: official MOSPI CPI-Combined (inflation as published at the time). Segments: {seg}. "
                 f"Linking factor 2012→2024 {s['linking_factor_2024']} (2025 overlap ratio "
                 f"{s['overlap_2025_mean_ratio']:.4f}); CPI-IW 1982→2001 factor {s['cpiiw_factor_1982_2001']}. "
                 f"Inflation vs the old OECD series: corr {v.get('corr', float('nan')):.3f}, "
                 f"mean |diff| {v.get('mean_abs_diff_pp', float('nan')):.2f}pp.")
    else:
        L.append(f"- India CPI: OECD series ratio-spliced to MOSPI 2024, ratio {s['ratio']:.4f} "
                 f"(sd {s['ratio_std']:.5f}) over {', '.join(s['overlap'])}.")
    L.append(f"- India policy rate source: {m['india_policy_rate_source']}.")
    if "call_vs_repo" in m:
        c = m["call_vs_repo"]
        L.append(f"- Call rate vs RBI repo rate ({c['overlap'][0]}–{c['overlap'][1]}): mean gap "
                 f"{c['mean_call_minus_repo_pp']:+.2f}pp, mean |gap| {c['mean_abs_gap_pp']:.2f}pp, corr {c['corr']:.3f}.")
    L.append(f"- FPI series: legacy FII before {m['fpi_seam']}, BoP net portfolio after.\n")

    if isinstance(m.get("rbi_reconciliation"), dict):
        L.append("## RBI data sources\n")
        f = m.get("dbie_fetch", {})
        L.append(f"{m['rbi_source']}. API fetched {f.get('fetched_at', 'from cache')}"
                 + (f", mirror loaded {f['api_health'].get('registry_loaded_at', '?')[:19]}" if 'api_health' in f else "") + ".\n")
        L.append("| Series | API range | Excel range | Later vintage | Overlap | Revised | Unexpected diffs |")
        L.append("|---|---|---|---|---|---|---|")
        for k, v in m["rbi_reconciliation"].items():
            rng = lambda x: f"{x[0]}–{x[1]}" if x else "—"
            L.append(f"| {k} | {rng(v['api_range'])} | {rng(v['xlsx_range'])} | {v['newer_source']} | "
                     f"{v['overlap']} | {v.get('n_revised', 0)} | {v.get('n_unexpected', 0)} |")
        p = m.get("inr_usd_patch", {})
        if p.get("filled") or p.get("extended"):
            L.append(f"\nINR/USD patched with rescaled FRED EXINUS: filled {p['filled'] or 'none'}, "
                     f"extended {p['extended'] or 'none'} (mean RBI–FRED gap {p['mean_abs_rel_diff']:.2%}).")
        L.append("")

    L.append("## Data warnings\n")
    for w in r["warnings"] or ["none"]:
        L.append(f"- {w}")
    L.append("")
    L.append("## Series end dates (reference month)\n")
    L.append(", ".join(f"{k} {v}" for k, v in m["series_end"].items()) + "\n")
    return "\n".join(L)


def console_summary(r: dict) -> str:
    comp, ds = r["composite"], r["dataset"]
    v, d = _last(comp["misalignment_pct"])
    fair, _ = _last(comp["fair_inr"])
    h = r["headline_h"]
    o = r["backtest"][h]["oos"]
    lines = [
        f"INR/USD fair value · run {r['run_id']} · as of {ds.asof:%b %Y} · spot {ds.pit.loc[ds.asof, 'inr_usd']:.2f}",
        f"  Composite fair {fair:.2f}  misalignment {v:+.1f}% ({d})",
        f"  P(stress) filtered {r['regime_summary']['p_stress_now']:.2f}",
    ]
    if "rmse_ecm" in o:
        lines.append(f"  {h}m OOS: RMSE ratio vs drift {o['rmse_ratio_ecm_vs_drift']:.3f}, "
                     f"Clark-West p {o['clark_west']['pvalue_one_sided']:.3f}, "
                     f"hit {o['hit_rate_ecm_sign']:.0%} vs naive {o['hit_rate_naive_depreciation']:.0%}")
    for w in r["warnings"]:
        lines.append(f"  ! {w}")
    return "\n".join(lines)


def charts(r: dict, out_dir: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    made = []
    comp = r["composite"]

    fig, ax = plt.subplots(3, 1, figsize=(12, 11), sharex=True)
    ax[0].plot(comp.index, comp["inr_usd"], label="INR/USD", lw=1.8)
    ax[0].plot(comp.index, comp["fair_inr"], label="Composite fair (point-in-time)", ls="--")
    if "fair_inr_strong" in comp:
        ax[0].fill_between(comp.index, comp["fair_inr_strong"], comp["fair_inr_weak"], alpha=0.2,
                           label=f"Fair-value corridor ({comp.attrs.get('corridor', 'component bands')})")
    ax[0].plot(comp.index, r["beer"]["fair_inr"], label="BEER (current)", ls=":", alpha=0.8)
    ax[0].set_ylabel("INR per USD"); ax[0].legend(); ax[0].set_title(
        f"INR/USD vs point-in-time fair values (REER component: {r['config']['composite'].get('reer_component', 'hp')})")
    ax[1].axhline(0, color="k", lw=0.8)
    ax[1].plot(comp.index, r["reer"]["misalignment_pct"], label="REER gap (HP)")
    ax[1].plot(comp.index, r["panel"]["misalignment_pct"], label="REER panel anchor", ls="-.")
    ax[1].plot(comp.index, r["feer_m"]["misalignment_pct"], label="FEER (IMF norm)")
    ax[1].plot(comp.index, comp["misalignment_pct"], label="Composite", lw=2)
    ax[1].set_ylabel("% (+ = INR undervalued)"); ax[1].legend()
    ax[2].fill_between(comp.index, r["regimes"]["p_stress_filtered"].fillna(0), color="tab:red", alpha=0.4,
                       label="P(stress), filtered")
    ax[2].set_ylim(0, 1); ax[2].legend()
    fig.tight_layout()
    p = out_dir / "fair_value.png"; fig.savefig(p, dpi=130); plt.close(fig); made.append(p.name)

    h = r["headline_h"]
    fc = r["forecasts"][h].dropna(subset=["y"])
    if len(fc):
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(fc.index, fc["y"] * 100, label=f"Realised {h}m Δlog INR", color="k")
        ax.plot(fc.index, fc["f_drift"] * 100, label="Random walk + drift")
        ax.plot(fc.index, fc["f_ecm"] * 100, label="ECM")
        ax.axhline(0, color="grey", lw=0.8); ax.set_ylabel("%"); ax.legend()
        ax.set_title(f"Out-of-sample {h}-month forecasts (origin date)")
        fig.tight_layout()
        p = out_dir / f"oos_{h}m.png"; fig.savefig(p, dpi=130); plt.close(fig); made.append(p.name)
    return made
