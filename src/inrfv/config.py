"""Configuration loading."""

from __future__ import annotations

import copy
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "default.toml"


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> dict:
    """Load a TOML config and resolve [paths] relative to the project root."""
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    if overrides:
        cfg = _deep_merge(cfg, overrides)
    cfg["_source"] = str(path)
    cfg["_root"] = str(PROJECT_ROOT)
    return cfg


def path(cfg: dict, key: str) -> Path:
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else Path(cfg["_root"]) / p


def config_hash(cfg: dict) -> str:
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    blob = json.dumps(clean, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
