"""Markdown report, console dashboard and charts for a pipeline run."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _f(x, fmt="{:+.1f}", na="n/a"):
    try:
        return na if x is None or (isinstance(x, float) and np.isnan(x)) else fmt.format(x)
    except (TypeError, ValueError):
        return na


def _last(s: pd.Series):
    s = s.dropna()
    return (s.iloc[-1], s.index[-1].strftime("%b %Y")) if len(s) else (np.nan, "n/a")


def build_report(r: dict) -> str:
    ds, comp = r["dataset"], r["composite"]
    L = []
    asof = ds.asof
    spot = ds.pit.loc[asof, "inr_usd"]
    L.append("# INR/USD fair value: run report\n")
    L.append(f"Run `{r['run_id']}` · as of **{asof:%b %Y}** (latest month with RBI INR/USD) · "
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
        (f"FEER, {fp['central_norm'].upper()} norm (central)", fm["misalignment_pct"], fm["fair_inr"],
         f"{qlabel}; {min(fp['band_percentiles'])}–{max(fp['band_percentiles'])}th pct {_f(_last(fm[lo_c])[0])}% to {_f(_last(fm[hi_c])[0])}%"),
        ("FEER, NIIP-stabilising norm", fm.get("misalignment_pct_niip", pd.Series(dtype=float)), None, "alternative norm"),
        ("FEER, legacy −2.5% norm", fm.get("misalignment_pct_static", pd.Series(dtype=float)), None, "v0.2 assumption, for comparison"),
        ("FEER conditional (experimental)", fm["misalignment_pct_conditional"], None, "ad hoc norm, not in composite"),
        ("BEER (expanding window)", r["beer"]["misalignment_pct"], r["beer"]["fair_inr"],
         "cointegrated" if r["beer_diag"]["engle_granger"]["cointegrated_5pct"] else "**not cointegrated**: descriptive only"),
        ("Composite (REER+FEER)", comp["misalignment_pct"], comp["fair_inr"], "drives the ECM"),
    ]
    for name, mis, fair, note in rows:
        v, d = _last(mis)
        fv = _f(_last(fair)[0], "{:.2f}") if fair is not None else "n/a"
        L.append(f"| {name} | {d} | {_f(v)}% | {fv} | {note} |")
    L.append("")
    if "fair_inr_strong" in comp:
        s_, w_ = _last(comp["fair_inr_strong"])[0], _last(comp["fair_inr_weak"])[0]
        L.append(f"**Fair-value corridor ({min(fp['band_percentiles'])}th–{max(fp['band_percentiles'])}th percentile "
                 f"of FEER norm and elasticity uncertainty): {_f(s_, '{:.2f}')} – {_f(w_, '{:.2f}')}** "
                 f"(central {_f(_last(comp['fair_inr'])[0], '{:.2f}')}, spot {spot:.2f}).\n")

    # FEER decomposition for the latest quarter, and a cross-check against the IMF.
    x = fq.dropna(subset=["misalignment_pct"]).iloc[-1]
    L.append("### FEER, latest quarter\n")
    L.append(f"Quarter from {x.name:%b %Y}, public {x['available']:%b %Y}: 4-quarter CA {x['ca_pct_4q']:+.2f}% of GDP; "
             f"oil adjustment {x['oil_adjustment']:+.2f}pp (net oil imports {_f(x['net_oil_pct_gdp'], '{:.2f}')}% of GDP, "
             f"Brent paid ${x['brent_paid']:.0f} vs 5-year norm ${x['brent_norm']:.0f}); underlying CA "
             f"{x['cad_underlying']:+.2f}%. Norms: IMF {x['norm_imf']:+.1f}%, NIIP-stabilising "
             f"{_f(x['norm_niip'], '{:+.2f}')}%, legacy {x['norm_static']:+.1f}%. Semi-elasticity "
             f"{x['semi_elasticity']:.3f} pp/1% ({x['semi_source']}; X {_f(x['exports_pct_gdp'], '{:.1f}')}%, "
             f"M {_f(x['imports_pct_gdp'], '{:.1f}')}% of GDP).\n")
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
             "passed the panel check, so treat the cointegration result as suggestive.\n")

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

    L.append("## Diagnostics\n")
    eg = r["beer_diag"]["engle_granger"]
    L.append(f"- BEER Engle-Granger ({eg['n_vars']} vars, n={eg['nobs']}): stat {eg['stat']:.2f}, "
             f"5% critical {eg['crit_5pct']:.2f}, p = {eg['pvalue']:.3f}.")
    for name, j in r["johansen"].items():
        L.append(f"- Johansen {name}: rank {j['rank']} of {j['n_vars']} (sequential trace, 5%, k_ar_diff={j['k_ar_diff']}, n={j['nobs']}).")
    m = ds.meta
    L.append(f"- DXY splice: ratio {m['dxy_splice_ratio']:.4f}; log change at seam {m['dxy_seam']['month']}: {m['dxy_seam']['log_change_pct']:+.2f}%.")
    s = m["cpi_india_splice"]
    L.append(f"- India CPI splice: ratio {s['ratio']:.4f} (sd {s['ratio_std']:.5f}) over {', '.join(s['overlap'])}.")
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
                           label="Fair-value corridor (FEER uncertainty)")
    ax[0].plot(comp.index, r["beer"]["fair_inr"], label="BEER (expanding)", ls=":", alpha=0.8)
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
