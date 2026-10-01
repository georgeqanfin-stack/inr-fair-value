"""Run directories, raw-data checksums and run manifests."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import config_hash, path

MANIFEST_NAME = "MANIFEST.sha256"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def raw_checksums(raw_dir: Path) -> dict[str, str]:
    files = sorted(p for p in raw_dir.rglob("*") if p.is_file() and p.name != MANIFEST_NAME)
    return {p.relative_to(raw_dir).as_posix(): sha256_file(p) for p in files}


def write_raw_manifest(raw_dir: Path) -> Path:
    sums = raw_checksums(raw_dir)
    out = raw_dir / MANIFEST_NAME
    out.write_text("".join(f"{h}  {name}\n" for name, h in sums.items()), encoding="utf-8")
    return out


def verify_raw_manifest(raw_dir: Path) -> dict[str, list[str]]:
    """Compare data/raw against its committed manifest."""
    manifest = raw_dir / MANIFEST_NAME
    if not manifest.exists():
        return {"missing_manifest": [str(manifest)], "changed": [], "added": [], "removed": []}
    recorded = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            h, name = line.split("  ", 1)
            recorded[name] = h
    current = raw_checksums(raw_dir)
    return {
        "missing_manifest": [],
        "changed": sorted(n for n in recorded.keys() & current.keys() if recorded[n] != current[n]),
        "added": sorted(current.keys() - recorded.keys()),
        "removed": sorted(recorded.keys() - current.keys()),
    }


def git_revision(root: Path) -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                               capture_output=True, text=True, timeout=10)
        if rev.returncode != 0:
            return "uncommitted"
        return rev.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def new_run_dir(cfg: dict, suffix: str = "") -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{suffix}" if suffix else "")
    d = path(cfg, "runs") / run_id
    d.mkdir(parents=True, exist_ok=False)
    return d


def write_manifest(run_dir: Path, cfg: dict, extra: dict) -> Path:
    raw_dir = path(cfg, "raw")
    manifest = {
        "run_id": run_dir.name,
        "created": datetime.now().isoformat(timespec="seconds"),
        "inrfv_version": __version__,
        "git_revision": git_revision(Path(cfg["_root"])),
        "config_source": cfg["_source"],
        "config_hash": config_hash(cfg),
        "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "raw_checksums": raw_checksums(raw_dir),
        "raw_manifest_check": verify_raw_manifest(raw_dir),
        **extra,
    }
    out = run_dir / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    latest = path(cfg, "runs").parent / "latest.txt"
    latest.write_text(run_dir.name + "\n", encoding="utf-8")
    return out
