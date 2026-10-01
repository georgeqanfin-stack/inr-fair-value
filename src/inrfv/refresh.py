"""Monthly data refresh.

    python -m inrfv.refresh            # fetch, check, pin, run, summarise
    python -m inrfv.refresh --commit   # ...and commit data/raw and reports/ to git

Stages:
1. Back up data/raw, then re-download every automatic source (FRED, World Bank,
   RBIH Data API for RBI/MOSPI, BIS panel REER).
2. Quality gates on the new data. Hard failures restore the backup and exit 1:
   history lost from a cached series, or an implausible monthly jump in a core market
   series. Warnings do not stop the run: manual inputs that look out of date, RBI
   source disagreements, stale series.
3. Re-pin data/raw/MANIFEST.sha256 and run the pipeline on the fresh cache.
4. Write refresh_summary.md (new observations, revisions, what moved the headline
   since the previous run) next to the run's report, and copy the report to
   reports/latest/ and reports/<as-of month>/.

Exit codes: 0 success, 1 a quality gate failed (data restored), 2 an error (data restored).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from . import report
from .config import load_config, path
from .data import panel as panel_data
from .data import schemas
from .data.build import build_dataset
from .io import new_run_dir, write_manifest, write_raw_manifest
from .note import build_note
from .run import NOTE_LINKS, run_pipeline, save

CORE_SERIES = {"inr_usd": 0.15, "reer": 0.15, "dxy": 0.10}   # max plausible |monthly log change| in new data


# --------------------------------------------------------------------------- snapshots and diffs

def read_cached(f: Path) -> pd.Series | None:
    """Any cached raw CSV as a Series keyed by date (or (country, year) for panels)."""
    try:
        df = pd.read_csv(f)
    except (pd.errors.ParserError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return None
    cols = list(df.columns)
    if {"country", "year", "value"} <= set(cols):
        return df.set_index(["country", "year"])["value"].astype(float)
    if len(cols) == 2:
        key = pd.to_datetime(df.iloc[:, 0], format="mixed", dayfirst=not str(df.iloc[0, 0])[:4].isdigit(),
                             errors="coerce")
        s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy(), index=key)
        return s[s.index.notna()]
    return None


def snapshot(raw: Path) -> dict[str, pd.Series]:
    out = {}
    for f in sorted(raw.rglob("*.csv")):
        rel = f.relative_to(raw).as_posix()
        if rel.startswith("manual/"):
            continue
        s = read_cached(f)
        if s is not None:
            out[rel] = s.dropna()
    return out


def _key(k) -> str:
    return k.strftime("%Y-%m") if isinstance(k, pd.Timestamp) else str(k)


def diff_snapshots(before: dict, after: dict, rel_tol: float = 1e-6) -> dict[str, dict]:
    out: dict[str, dict[str, Any]] = {}
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name), after.get(name)
        if a is None:
            if b is not None:
                out[name] = {"status": "new file", "rows": len(b)}
            continue
        if b is None:
            out[name] = {"status": "removed file", "rows_before": len(a)}
            continue
        new_keys = b.index.difference(a.index)
        lost = a.index.difference(b.index)
        both = a.index.intersection(b.index)
        rel = ((b[both] - a[both]).abs() / a[both].abs().where(a[both].abs() > 1e-12)).fillna(0)
        revised = rel[rel > rel_tol]
        d: dict[str, Any] = {"rows_before": len(a), "rows_after": len(b), "new": len(new_keys), "lost": len(lost),
             "revised": len(revised)}
        if len(new_keys):
            d["new_range"] = [_key(min(new_keys)), _key(max(new_keys))]
        if len(lost):
            d["lost_examples"] = [_key(k) for k in list(lost)[:3]]
        if len(revised):
            k = revised.idxmax()
            d["max_revision"] = {"at": _key(k), "before": float(a[k]), "after": float(b[k]),
                                 "pct": float(revised.max() * 100)}
        if d["new"] or d["lost"] or d["revised"]:
            out[name] = d
    return out


# --------------------------------------------------------------------------- gates

def expected_mospi_month(today: date) -> pd.Timestamp:
    """MOSPI releases month m around the 12th of m+1."""
    t = pd.Timestamp(today)
    back = 1 if t.day >= 13 else 2
    return (t.to_period("M") - back).to_timestamp()


def quality_gates(cfg: dict, diffs: dict, ds, today: date) -> tuple[list[str], list[str]]:
    failures, warnings = [], []
    # Cached inputs must match their schemas (data/schemas.py): a changed source format fails here.
    failures += [f"schema: {p}" for p in schemas.validate(path(cfg, "raw"))]
    for name, d in diffs.items():
        if d.get("status") == "removed file" or d.get("lost", 0) > 0:
            failures.append(f"{name}: {d.get('lost', d.get('rows_before'))} cached observations disappeared "
                            f"(e.g. {d.get('lost_examples', [])}).")
    # Implausible jumps in newly added months of core market series.
    new_since = {}
    for name, d in diffs.items():
        if "new_range" in d and d["new_range"][0][:2] in ("19", "20"):
            new_since[name] = pd.Timestamp(d["new_range"][0] + "-01")
    first_new = min(new_since.values()) if new_since else None
    for col, limit in CORE_SERIES.items():
        s = np.log(ds.panel[col].dropna())
        ch = s.diff()
        if first_new is not None:
            ch = ch[ch.index >= first_new]
        bad = ch[ch.abs() > limit]
        for d_, v in bad.items():
            failures.append(f"{col}: monthly change of {v * 100:+.1f}% in {d_:%b %Y} exceeds the {limit:.0%} "
                            "plausibility limit; check the source before accepting.")
    # Manual inputs.
    manual = path(cfg, "manual")
    # CPI 2024=100 arrives automatically from the RBI Bulletin table; the manual MOSPI file is
    # only a fallback, so warn only when neither has the month that should be out.
    mospi = pd.read_csv(manual / "mospi_cpi_2024base.csv", parse_dates=["date"])["date"].max()
    api_cpi = path(cfg, "dbie_cache") / "cpi_2024base.csv"
    if api_cpi.exists():
        mospi = max(mospi, pd.read_csv(api_cpi, parse_dates=["date"])["date"].max())
    exp = expected_mospi_month(today)
    if mospi < exp:
        warnings.append(f"MOSPI CPI ends {mospi:%b %Y} in both the RBI API and data/raw/manual/mospi_cpi_2024base.csv; "
                        f"{exp:%b %Y} should be out. If the API lags, add it from "
                        "https://www.mospi.gov.in/themes/product/9-consumer-price-index-cpi (Annexure IV).")
    norms = pd.read_csv(manual / cfg["models"]["feer"]["norm_path_file"])
    last_norm = pd.Timestamp(norms["available"].max() + "-01")
    t = pd.Timestamp(today)
    esr_due = pd.Timestamp(t.year if t.month >= 8 else t.year - 1, 7, 1)    # ESR each July
    if last_norm < esr_due:
        warnings.append(f"Latest IMF CA norm for India is from {last_norm:%b %Y}; the {esr_due.year} External Sector "
                        "Report (July) should have a newer one (India table, 'EBA Norm'). Add a row to "
                        "data/raw/manual/imf_ca_norm_india.csv.")
    for k, v in ds.meta.get("rbi_reconciliation", {}).items():
        if v.get("n_unexpected"):
            warnings.append(f"RBI sources disagree on {k} outside the revision window ({v['n_unexpected']} periods).")
    return failures, warnings


# --------------------------------------------------------------------------- headline comparison

def previous_run(cfg: dict) -> Path | None:
    """The last published report (reports/latest, committed, so it exists in CI too),
    else the last local run in outputs/runs."""
    published = Path(cfg["_root"]) / "reports" / "latest"
    if (published / "composite_ect.csv").exists():
        return published
    latest = path(cfg, "runs").parent / "latest.txt"
    if not latest.exists():
        return None
    d = path(cfg, "runs") / latest.read_text(encoding="utf-8").strip()
    return d if (d / "composite_ect.csv").exists() else None


def headline_change(prev_dir: Path | None, comp: pd.DataFrame, cfg: dict) -> dict | None:
    if prev_dir is None:
        return None
    old = pd.read_csv(prev_dir / "composite_ect.csv", index_col=0, parse_dates=True).dropna(subset=["ect"])
    new = comp.dropna(subset=["ect"])
    if old.empty or new.empty:
        return None
    o, n = old.iloc[-1], new.iloc[-1]
    w = cfg["composite"]
    wr, wf = w["weight_reer"] / (w["weight_reer"] + w["weight_feer"]), w["weight_feer"] / (w["weight_reer"] + w["weight_feer"])
    return {
        "previous_run": (json.loads((prev_dir / "manifest.json").read_text(encoding="utf-8")).get("run_id", prev_dir.name)
                         if (prev_dir / "manifest.json").exists() else prev_dir.name),
        "previous_asof": old.index[-1].strftime("%Y-%m"),
        "asof": new.index[-1].strftime("%Y-%m"),
        "spot": [float(o["inr_usd"]), float(n["inr_usd"])],
        "fair": [float(o["fair_inr"]), float(n["fair_inr"])],
        "misalignment_pct": [float(o["misalignment_pct"]), float(n["misalignment_pct"])],
        "contribution_pp": {"REER component": float((n["gap_reer"] - o["gap_reer"]) * wr * 100),
                            "FEER": float((n["gap_feer"] - o["gap_feer"]) * wf * 100)},
    }


def summary_md(diffs: dict, failures: list[str], warnings: list[str], change: dict | None,
               run_id: str | None, asof: str | None) -> str:
    L = [f"# Data refresh {date.today():%d %b %Y}\n"]
    L.append(f"Run `{run_id}` · as of **{asof}**\n" if run_id else "**Refresh failed: data restored.**\n")
    if change:
        m0, m1 = change["misalignment_pct"]
        L.append("## Headline\n")
        L.append(f"Composite misalignment {m0:+.1f}% → **{m1:+.1f}%** "
                 f"({change['previous_asof']} → {change['asof']}); fair value {change['fair'][0]:.2f} → "
                 f"**{change['fair'][1]:.2f}**; spot {change['spot'][0]:.2f} → {change['spot'][1]:.2f}. "
                 "Change in the ECT by component: "
                 + ", ".join(f"{k} {v:+.1f}pp" for k, v in change["contribution_pp"].items()) + ".\n")
    L.append("## Gates\n")
    L += [f"- **FAIL** {f}" for f in failures] or ["- All hard gates passed."]
    L += [f"- warning: {w}" for w in warnings]
    L.append("\n## Data changes\n")
    if not diffs:
        L.append("No cached series changed.\n")
    else:
        L.append("| File | New obs | New range | Revised | Largest revision | Lost |")
        L.append("|---|---|---|---|---|---|")
        for name, d in diffs.items():
            if "status" in d:
                L.append(f"| {name} | {d['status']} | | | | |")
                continue
            mr = d.get("max_revision")
            mrs = f"{mr['at']}: {mr['before']:.4g} → {mr['after']:.4g} ({mr['pct']:.2f}%)" if mr else ""
            nr = "–".join(d["new_range"]) if "new_range" in d else ""
            L.append(f"| {name} | {d['new']} | {nr} | {d['revised']} | {mrs} | {d['lost']} |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- main

def publish_reports(run_dir: Path, root: Path, asof: str) -> list[Path]:
    targets = [root / "reports" / "latest", root / "reports" / asof]
    for t in targets:
        if t.exists():
            shutil.rmtree(t)
        t.mkdir(parents=True)
        for f in ["report.md", "refresh_summary.md", "results.json", "manifest.json", "composite_ect.csv", "dashboard.html", "note.md"] + \
                 [p.name for p in run_dir.glob("*.png")]:
            if (run_dir / f).exists():
                shutil.copy2(run_dir / f, t / f)
    return targets


def git_commit(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "data/raw", "reports"], cwd=root, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root)
    if staged.returncode == 0:
        return "nothing to commit"
    subprocess.run(["git", "-c", "core.autocrlf=false", "commit", "-q", "-m", message], cwd=root, check=True)
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                          text=True).stdout.strip()


def refresh(cfg: dict, commit: bool = False, today: date | None = None) -> int:
    today = today or date.today()
    raw = path(cfg, "raw")
    root = Path(cfg["_root"])
    prev = previous_run(cfg)
    prev_copy = None
    if prev is not None:                       # reports/latest is overwritten later in this run
        prev_copy = Path(tempfile.mkdtemp(prefix="inrfv_prev_"))
        for f in ["composite_ect.csv", "manifest.json"]:
            if (prev / f).exists():
                shutil.copy2(prev / f, prev_copy / f)
    before = snapshot(raw)
    backup = Path(tempfile.mkdtemp(prefix="inrfv_raw_"))
    shutil.copytree(raw, backup / "raw")

    def restore():
        shutil.rmtree(raw)
        shutil.copytree(backup / "raw", raw)

    try:
        print("Fetching sources...")
        ds = build_dataset(cfg, refresh=True)
        panel_data.load(cfg, refresh=True)
        diffs = diff_snapshots(before, snapshot(raw))
        failures, warnings = quality_gates(cfg, diffs, ds, today)
        if failures:
            restore()
            md = summary_md(diffs, failures, warnings, None, None, None)
            out = root / "outputs" / f"refresh_failed_{today:%Y%m%d}.md"
            out.parent.mkdir(exist_ok=True)
            out.write_text(md, encoding="utf-8")
            print(md)
            print(f"Quality gates failed; data/raw restored. Summary: {out}")
            return 1

        write_raw_manifest(raw)
        run_dir = new_run_dir(cfg)
        r = run_pipeline(cfg, refresh=False, run_dir=run_dir)
        save(r, run_dir)
        asof = r["dataset"].meta["asof"]
        change = headline_change(prev_copy, r["composite"], cfg)
        md = summary_md(diffs, failures, warnings + r["warnings"], change, run_dir.name, asof)
        (run_dir / "refresh_summary.md").write_text(md, encoding="utf-8")
        links = {**NOTE_LINKS, "What changed": "refresh_summary.md"}
        (run_dir / "note.md").write_text(build_note(r, change=change, diffs=diffs, gate_warnings=warnings,
                                                    links=links), encoding="utf-8")
        write_manifest(run_dir, cfg, {"asof": asof, "warnings": r["warnings"],
                                      "refresh": {"data_changes": diffs, "gate_warnings": warnings}})
        targets = publish_reports(run_dir, root, asof)
        print(report.console_summary(r))
        if change:
            print(f"  Since {change['previous_run']}: misalignment {change['misalignment_pct'][0]:+.1f}% → "
                  f"{change['misalignment_pct'][1]:+.1f}%")
        print(f"  {sum(d.get('new', 0) for d in diffs.values())} new observations, "
              f"{sum(d.get('revised', 0) for d in diffs.values())} revised, in {len(diffs)} files")
        print(f"\nOutputs: {run_dir}\nReports: {', '.join(str(t) for t in targets)}")
        if commit:
            print(f"Committed: {git_commit(root, f'Data refresh: as of {asof} (run {run_dir.name})')}")
        return 0
    except Exception:
        traceback.print_exc()
        restore()
        print("Refresh failed; data/raw restored from backup.")
        return 2
    finally:
        shutil.rmtree(backup, ignore_errors=True)
        if prev_copy is not None:
            shutil.rmtree(prev_copy, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m inrfv.refresh", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="path to a TOML config (default config/default.toml)")
    ap.add_argument("--commit", action="store_true", help="commit data/raw and reports/ to git afterwards")
    args = ap.parse_args(argv)
    load_dotenv()
    return refresh(load_config(args.config), commit=args.commit)


if __name__ == "__main__":
    sys.exit(main())
