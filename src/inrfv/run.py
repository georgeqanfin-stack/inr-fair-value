"""Run the full pipeline.

    python -m inrfv.run                  # use cached data, write outputs/runs/<id>/
    python -m inrfv.run --refresh        # re-download FRED and World Bank series first
    python -m inrfv.run --write-raw-manifest   # record checksums of data/raw
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from . import backtest, dashboard, note, report, vintages
from .config import load_config, path
from .data import panel as panel_data
from .data import schemas
from .data.build import build_dataset
from .io import new_run_dir, verify_raw_manifest, write_manifest, write_raw_manifest
from .models import (
    beer,
    benchmark,
    composite,
    feer,
    flow_id,
    flows,
    market,
    nonlinear,
    panel_anchor,
    peers,
    reer_anchor,
    regimes,
    regimes_tvtp,
    structural,
    uncertainty,
    weights,
)
from .stats.cointegration import johansen_rank


def run_pipeline(cfg: dict, refresh: bool = False, run_dir=None) -> dict:
    ds = build_dataset(cfg, refresh=refresh)
    warnings = list(ds.warnings)

    warnings += [f"Schema check: {p}" for p in schemas.validate(path(cfg, "raw"))]
    raw_check = verify_raw_manifest(path(cfg, "raw"))
    if raw_check["missing_manifest"]:
        warnings.append("data/raw has no MANIFEST.sha256; run with --write-raw-manifest to pin the inputs.")
    elif raw_check["changed"] or raw_check["removed"]:
        warnings.append(f"data/raw differs from MANIFEST.sha256: changed={raw_check['changed']} "
                        f"removed={raw_check['removed']}")

    lag_months = (pd.Timestamp.today().to_period("M") - ds.asof.to_period("M")).n
    if lag_months > 2:
        warnings.append(f"RBI USD/INR ends {ds.asof:%b %Y}, {lag_months} months ago: download fresh DBIE files "
                        "to move the as-of date forward.")

    reer = structural.run(ds.pit, cfg)
    feer_q, feer_m = feer.run(ds.bop, ds.pit, cfg)
    beer_out, beer_diag = beer.run(ds, cfg)
    reg_out, reg_summary = regimes.run(ds.pit, cfg)
    reg_summary["tvtp"] = regimes_tvtp.run(ds.pit, cfg) if cfg["models"].get("regimes_tvtp") else None
    anchor, anchor_diag = reer_anchor.run(ds, cfg)
    pdata = panel_data.load(cfg, refresh=refresh)
    ucfg = cfg.get("uncertainty", {})
    panel_out, panel_diag = panel_anchor.run(ds, pdata, cfg, boot_draws=ucfg.get("panel_boot_draws", 0))
    peer_gaps = panel_diag.pop("peer_gaps")
    gap_draws = panel_diag.pop("gap_draws", None)
    reer_component = {"hp": reer, "anchor": anchor, "panel": panel_out}[cfg["composite"].get("reer_component", "hp")]
    comp = composite.run(ds.pit, reer_component, feer_m, cfg)
    bt, fcs = backtest.run(comp, reg_out, cfg)
    h = cfg["backtest"]["headline_horizon"]
    cur = backtest.current_forecast(comp, h, cfg["backtest"].get("window_months"))

    flow_out, flow_diag = flows.run(ds.panel, cfg)
    if cfg["models"].get("flow_id"):
        flow_diag["identification"] = flow_id.run(ds.panel, cfg, flow_diag["coef"]["fpi"])
    market_diag = market.run(ds.pit, ds.panel, cfg)

    panel = ds.panel
    johansen = {
        "PPP [log INR, log CPI India, log CPI US]": johansen_rank(
            pd.DataFrame({"log_inr": np.log(panel["inr_usd"]), "log_cpi_in": np.log(panel["cpi_india"]),
                          "log_cpi_us": np.log(panel["cpi_us"])}).dropna()),
    }

    if not anchor_diag["engle_granger"]["cointegrated_5pct"]:
        warnings.append(f"REER anchor fundamentals are not cointegrated with the REER (Engle-Granger p="
                        f"{anchor_diag['engle_granger']['pvalue']:.2f}); the anchor is reported, not relied on.")
    pc = panel_diag["specs"][panel_diag["central_spec"]]["panel_cointegration"]
    if not pc["cointegrated_5pct"]:
        warnings.append(f"Panel anchor residuals fail the panel cointegration check (Fisher p={pc['pvalue']:.2f}).")
    if not beer_diag["engle_granger"]["cointegrated_5pct"]:
        warnings.append(f"BEER residuals are not cointegrated (Engle-Granger p="
                        f"{beer_diag['engle_granger']['pvalue']:.2f}); treat the BEER fair value as descriptive.")

    r = {"dataset": ds, "reer": reer, "feer_q": feer_q, "feer_m": feer_m, "beer": beer_out,
            "beer_diag": beer_diag, "anchor": anchor, "anchor_diag": anchor_diag,
            "panel": panel_out, "panel_diag": panel_diag, "regimes": reg_out, "regime_summary": reg_summary,
            "flows": flow_out, "flows_diag": flow_diag, "market": market_diag,
            "composite": comp, "backtest": bt, "forecasts": fcs, "current_forecast": cur,
            "johansen": johansen, "warnings": warnings, "headline_h": h, "config": cfg,
            "run_id": run_dir.name if run_dir else "adhoc"}
    r["revisions"] = vintages.revision_effect(r, cfg) if cfg.get("vintages", {}).get("revision_check") else None
    r["benchmark"] = benchmark.run(r, cfg)
    r["peer_gaps"] = peer_gaps
    r["peers"] = peers.run(peer_gaps, cfg)
    r["weights"] = weights.run(comp, reer_component, feer_m, cfg)
    r["uncertainty"] = uncertainty.run(r, pdata, cfg, gap_draws) if ucfg else None
    r["nonlinear"] = (nonlinear.run(comp, {"composite": comp["misalignment_pct"],
                                           "REER component": reer_component["misalignment_pct"],
                                           "FEER": feer_m["misalignment_pct"]}, cfg)
                      if cfg["models"].get("nonlinear", {}).get("enabled", True) else None)
    if r["uncertainty"] and ucfg.get("headline_corridor") == "bootstrap":
        uncertainty.apply_corridor(comp, r["uncertainty"]["series"])
    return r


NOTE_LINKS = {"Dashboard": "dashboard.html", "Full report": "report.md"}


def save(r: dict, run_dir) -> None:
    ds = r["dataset"]
    ds.panel.to_csv(run_dir / "panel_reference_month.csv")
    ds.pit.to_csv(run_dir / "panel_point_in_time.csv")
    ds.bop.to_csv(run_dir / "bop_quarterly.csv")
    r["reer"].to_csv(run_dir / "model_reer.csv")
    r["anchor"].to_csv(run_dir / "model_reer_anchor.csv")
    r["panel"].to_csv(run_dir / "model_panel_anchor.csv")
    r["feer_q"].to_csv(run_dir / "model_feer_quarterly.csv")
    r["feer_m"].to_csv(run_dir / "model_feer_monthly.csv")
    r["beer"].to_csv(run_dir / "model_beer.csv")
    r["regimes"].to_csv(run_dir / "model_regimes.csv")
    r["flows"].to_csv(run_dir / "model_flows.csv")
    nl = r.get("nonlinear")
    if nl and nl.get("threshold_path") is not None:
        nl["threshold_path"].assign(tvp_slope=nl["tvp_slope"]).to_csv(run_dir / "ecm_nonlinear_params.csv")
    if r.get("uncertainty"):
        r["uncertainty"]["series"].join(r["uncertainty"]["expost"], how="left").to_csv(run_dir / "composite_bootstrap.csv")
    if r.get("weights"):
        r["weights"]["weights"].to_csv(run_dir / "composite_weight_schemes.csv")
    if r.get("peer_gaps") is not None:
        r["peer_gaps"].to_csv(run_dir / "model_peers.csv")
    rev = r.get("revisions")
    if rev:
        rev["series"].rename("composite_diff_pp").to_csv(run_dir / "revision_effect.csv")
    r["composite"].to_csv(run_dir / "composite_ect.csv")
    for h, fc in r["forecasts"].items():
        fc.to_csv(run_dir / f"oos_forecasts_{h}m.csv")
    results = {"backtest": r["backtest"], "current_forecast": r["current_forecast"],
               "regimes": r["regime_summary"], "beer": r["beer_diag"], "reer_anchor": r["anchor_diag"],
               "panel_anchor": r["panel_diag"], "flows": r["flows_diag"], "market": r["market"],
               "benchmark": r.get("benchmark"), "peers": r.get("peers"),
               "nonlinear": {k: v for k, v in (r.get("nonlinear") or {}).items() if k not in ("tvp_slope", "threshold_path")} or None,
               "uncertainty": {k: v for k, v in (r.get("uncertainty") or {}).items() if k not in ("series", "expost")} or None,
               "weights": {k: v for k, v in (r.get("weights") or {}).items() if k != "weights"} or None,
               "revisions": {k: v for k, v in (r.get("revisions") or {}).items() if k != "series"} or None,
               "johansen": r["johansen"],
               "data_meta": ds.meta, "warnings": r["warnings"]}
    (run_dir / "results.json").write_text(json.dumps(results, indent=2, default=_json), encoding="utf-8")
    charts = report.charts(r, run_dir)
    md = report.build_report(r)
    if charts:
        md += "\n## Charts\n\n" + "\n".join(f"![{c}]({c})" for c in charts) + "\n"
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    dashboard.write(r, run_dir, note_md=note.build_note(r))
    (run_dir / "note.md").write_text(note.build_note(r, links=NOTE_LINKS), encoding="utf-8")


def _json(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    return str(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m inrfv.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="path to a TOML config (default config/default.toml)")
    ap.add_argument("--refresh", action="store_true", help="re-download FRED and World Bank data")
    ap.add_argument("--write-raw-manifest", action="store_true", help="record data/raw checksums and exit")
    args = ap.parse_args(argv)

    load_dotenv()
    cfg = load_config(args.config)
    if args.write_raw_manifest:
        print(f"wrote {write_raw_manifest(path(cfg, 'raw'))}")
        return 0

    run_dir = new_run_dir(cfg)
    r = run_pipeline(cfg, refresh=args.refresh, run_dir=run_dir)
    save(r, run_dir)
    write_manifest(run_dir, cfg, {"asof": r["dataset"].meta["asof"], "warnings": r["warnings"]})
    print(report.console_summary(r))
    print(f"\nOutputs: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
