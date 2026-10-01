"""Data vintages: how much do revisions move the reading, and what did a past vintage say?

Two tools.

* ``revision_effect``: the RBI revises recent months (BoP, FDI, trade). The DBIE Excel
  files in data/raw and the RBIH Data API are two vintages of the same series; the
  Excel files are the earlier one. The headline models (REER component, FEER,
  composite) are re-run on a dataset that prefers the earlier vintage wherever both
  exist, and every point-in-time reading is compared with the current run. The gap is
  the effect of revisions published between the two vintages: a lower bound on the
  revision effect, since the Excel files are themselves partly revised.

* Vintage runs: every refresh commits data/raw to git, so the git history is a dated
  archive of inputs. ``python -m inrfv.vintages run <git-rev>`` checks data/raw out of
  that revision into a temporary folder and runs the full pipeline on it, giving the
  reading exactly as that vintage of the data implied (with today's code).

US series: FRED's real-time archive (ALFRED) needs an API key; see data/alfred.py.
"""

from __future__ import annotations

import argparse
import copy
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config, path
from .data import panel as panel_data
from .data.build import build_dataset
from .models import composite, feer, panel_anchor, reer_anchor, structural


def headline(ds, cfg: dict, pdata=None) -> pd.DataFrame:
    """Composite and its two components only (no BEER, regimes or backtest)."""
    key = cfg["composite"].get("reer_component", "hp")
    if key == "panel":
        reer_comp, _ = panel_anchor.run(ds, pdata if pdata is not None else panel_data.load(cfg), cfg)
    elif key == "anchor":
        reer_comp, _ = reer_anchor.run(ds, cfg)
    else:
        reer_comp = structural.run(ds.pit, cfg)
    _, feer_m = feer.run(ds.bop, ds.pit, cfg)
    return composite.run(ds.pit, reer_comp, feer_m, cfg)


def compare(current: pd.DataFrame, early: pd.DataFrame, until: pd.Timestamp | None = None) -> dict:
    """Point-in-time readings of two vintages, month by month (percentage points)."""
    cols = {"composite": "misalignment_pct"}
    d = pd.DataFrame({"current": current["misalignment_pct"], "early": early["misalignment_pct"]}).dropna()
    gr = pd.DataFrame({"reer": (current["gap_reer"] - early["gap_reer"]) * 100,
                       "feer": (current["gap_feer"] - early["gap_feer"]) * 100}).reindex(d.index)
    if until is not None:
        d, gr = d.loc[:until], gr.loc[:until]
    diff = d["current"] - d["early"]
    nz = diff[diff.abs() > 1e-9]
    worst = diff.abs().idxmax() if len(diff) else None
    return {
        "months": [d.index[0].strftime("%Y-%m"), d.index[-1].strftime("%Y-%m")] if len(d) else None,
        "n_months": int(len(d)), "n_changed": int(len(nz)),
        "mean_abs_pp": float(diff.abs().mean()) if len(d) else 0.0,
        "max_abs_pp": float(diff.abs().max()) if len(d) else 0.0,
        "max_month": worst.strftime("%Y-%m") if worst is not None else None,
        "last": {"month": d.index[-1].strftime("%Y-%m"), "current": float(d["current"].iloc[-1]),
                 "early": float(d["early"].iloc[-1]), "diff": float(diff.iloc[-1])} if len(d) else None,
        "by_component_mean_abs_pp": {k: float(gr[k].abs().mean()) for k in gr},
        "series": diff,
    }


def revision_effect(r: dict, cfg: dict) -> dict | None:
    """Re-run the headline on the earlier RBI vintage and compare (see module notes)."""
    if cfg.get("dbie", {}).get("mode") != "merge":
        return None
    meta = r["dataset"].meta.get("rbi_reconciliation", {})
    ends = [pd.Timestamp(v["xlsx_range"][1] + "-01") for v in meta.values() if v.get("xlsx_range")]
    if not ends:
        return None
    early_cfg = copy.deepcopy(cfg)
    early_cfg["dbie"]["mode"] = "merge_early"
    ds_early = build_dataset(early_cfg, refresh=False)
    early = headline(ds_early, early_cfg)
    # Compare up to the month the earlier vintage's last release was public (+ BoP lag).
    until = max(ends) + pd.offsets.MonthBegin(cfg["publication_lag"]["bop_quarterly"] + 3)
    out = compare(r["composite"], early, until)
    revised = {k: v for k, v in meta.items() if v.get("max_rel_diff", 0) > cfg["dbie"].get("reconcile_rel_tol", 0.005)}
    out["older_vintage"] = {"source": "DBIE Excel files in data/raw",
                            "ends": sorted({e.strftime("%Y-%m") for e in ends}),
                            "series_revised_beyond_tolerance": sorted(revised)}
    return out


# --------------------------------------------------------------------------- past vintages

def materialize(rev: str, root: Path, dest: Path) -> Path:
    """Write data/raw as committed at ``rev`` into ``dest``; returns the raw folder."""
    blob = subprocess.run(["git", "archive", "--format=tar", rev, "data/raw"], cwd=root,
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=BytesIO(blob)) as tar:
        tar.extractall(dest, filter="data")
    return dest / "data" / "raw"


def vintage_config(cfg: dict, raw: Path) -> dict:
    """Point every input path at a materialised data/raw."""
    out = copy.deepcopy(cfg)
    rel = {k: Path(out["paths"][k]).relative_to("data/raw") for k in ("fred_cache", "dbie_cache", "manual")}
    out["paths"]["raw"] = str(raw)
    for k, v in rel.items():
        out["paths"][k] = str(raw / v)
    return out


def run_vintage(rev: str, cfg: dict | None = None) -> Path:
    from .io import new_run_dir
    from .run import run_pipeline, save
    cfg = cfg or load_config()
    root = Path(cfg["_root"])
    sha = subprocess.run(["git", "rev-parse", "--short", rev], cwd=root, capture_output=True, text=True,
                         check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        vcfg = vintage_config(cfg, materialize(sha, root, Path(tmp)))
        run_dir = new_run_dir(cfg, suffix=f"vintage-{sha}")
        r = run_pipeline(vcfg, refresh=False, run_dir=run_dir)
        save(r, run_dir)
    return run_dir


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Run the pipeline on a past vintage of data/raw.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("run", help="full pipeline on data/raw as committed at a git revision")
    v.add_argument("rev")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        print(f"Outputs: {run_vintage(args.rev)}")


if __name__ == "__main__":
    main()
