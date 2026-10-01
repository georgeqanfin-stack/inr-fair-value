"""Schema checks on the cached inputs in data/raw.

Every cached file is checked against a declarative rule: exact columns, parseable dates,
unique keys, numeric values and, for key series, a plausible range. A source that
changes its format (a renamed column, values in different units, a duplicated month)
then stops the monthly refresh with a clear message instead of flowing silently into
the results. ``validate`` returns a list of problems; an empty list means all files pass.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Rule:
    columns: tuple[str, ...]
    keys: tuple[str, ...]                      # unique together
    dates: tuple[str, ...] = ()                # parse as dates
    numeric: tuple[str, ...] = ()              # must be numeric where present
    ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    min_rows: int = 1


DV = Rule(("date", "value"), ("date",), ("date",), ("value",))

# Most specific pattern first; the first match applies.
RULES: list[tuple[str, Rule]] = [
    ("dbie/inr_usd.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (10, 200)}, 300)),
    ("dbie/reer.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (30, 300)}, 200)),
    ("dbie/neer.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (30, 300)}, 200)),
    ("dbie/fx_reserves_usd_mn.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (0, 3e6)}, 300)),
    ("dbie/fx_reserves_weekly.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (0, 3e6)}, 300)),
    ("dbie/fwd_premium_*.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (-20, 40)}, 100)),
    ("dbie/wacr.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (0, 40)}, 100)),
    ("dbie/cpi.*.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (1, 10000)}, 20)),
    ("dbie/rbi_intervention.csv", Rule(("date", "net_purchase", "purchase", "sale", "fwd_book", "gross_fixed"), ("date",),
                                       ("date",), ("net_purchase", "purchase", "sale", "fwd_book"),
                                       {"net_purchase": (-1e5, 1e5), "fwd_book": (-5e5, 5e5)}, 200)),
    ("dbie/bop_bpm6.csv", Rule(("date", "current_account", "merch_balance", "private_transfers", "capital_account",
                                "fdi_bop", "portfolio_bop", "reserve_change", "primary_income", "goods_credit",
                                "goods_debit", "services_credit", "services_debit"), ("date",), ("date",),
                               ("current_account", "goods_credit"), {"current_account": (-1e5, 1e5)}, 20)),
    ("dbie/cpi_2024base.csv", Rule(("date", "index", "inflation", "provisional"), ("date",), ("date",), ("index",),
                                   {"index": (50, 300)}, 12)),
    ("dbie/gdp_real_quarterly.csv", Rule(("date", "gdp_real"), ("date",), ("date",), ("gdp_real",),
                                         {"gdp_real": (1e5, 1e8)}, 80)),
    ("dbie/inr_usd_daily_avg.csv", Rule(("date", "mean", "count"), ("date",), ("date",), ("mean", "count"),
                                        {"mean": (10, 200), "count": (1, 31)}, 100)),
    ("dbie/bop.*.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (-3e5, 3e5)}, 40)),
    ("dbie/bopx.*.csv", Rule(("date", "value"), ("date",), ("date",), ("value",), {"value": (-1e7, 1e7)}, 20)),
    ("dbie/*.csv", DV),
    ("fred/*.csv", DV),
    ("worldbank_panel/*.csv", Rule(("country", "year", "value"), ("country", "year"), (), ("year", "value"), {}, 100)),
    ("ewn/ewn_nfa.csv", Rule(("country", "year", "nfa_ewn", "nfa_official"), ("country", "year"), (),
                             ("year", "nfa_ewn"), {"nfa_ewn": (-1000, 1000)}, 100)),   # Chile 1973: -516%
    ("alfred/*.csv", Rule(("date", "realtime_start", "value"), ("date", "realtime_start"), ("date", "realtime_start"),
                          ("value",), {"value": (0, 1e4)}, 100)),
    ("manual/mospi_cpi_2024base.csv", Rule(("date", "cpi_india_2024base"), ("date",), ("date",), ("cpi_india_2024base",),
                                           {"cpi_india_2024base": (50, 300)}, 12)),
    ("manual/imf_ca_norm_india.csv", Rule(("available", "assessed", "norm", "se", "source"), ("available",), ("available",),
                                          ("norm", "se"), {"norm": (-10, 10), "se": (0, 5)}, 5)),
    ("manual/imf_eba_india.csv", Rule(("analysis_year", "published", "ca_actual", "ca_cyc_adj", "ca_norm", "ca_gap",
                                       "reer_gap_index", "reer_gap_level", "elasticity", "source"), ("analysis_year",),
                                      (), ("ca_norm", "elasticity"), {"elasticity": (0.01, 1)}, 5)),
    ("manual/imf_eba_panel.csv", Rule(("country", "analysis_year", "published", "ca_actual", "ca_cyc_adj", "ca_norm",
                                       "ca_gap", "reer_gap_index", "reer_gap_level", "elasticity"),
                                      ("country", "analysis_year"), (), ("ca_norm", "elasticity"), {}, 20)),
    ("manual/rbi_policy_repo_rate.csv", Rule(("date", "repo_rate"), ("date",), ("date",), ("repo_rate",),
                                             {"repo_rate": (0, 20)}, 12)),
    ("manual/rbi_repo_rate_changes.csv", Rule(("effective_date", "repo_rate"), ("effective_date",), ("effective_date",),
                                              ("repo_rate",), {"repo_rate": (0, 20)}, 5)),
]


def rule_for(rel: str) -> Rule | None:
    for pattern, rule in RULES:
        if fnmatch.fnmatch(rel, pattern):
            return rule
    return None


def check_file(path: Path, rule: Rule) -> list[str]:
    name = path.as_posix()
    try:
        df = pd.read_csv(path)
    except Exception as e:                      # unreadable file
        return [f"{name}: cannot be read ({e.__class__.__name__})"]
    out = []
    if tuple(df.columns) != rule.columns:
        return [f"{name}: columns {list(df.columns)} differ from the expected {list(rule.columns)}"]
    if len(df) < rule.min_rows:
        out.append(f"{name}: {len(df)} rows, fewer than the {rule.min_rows} expected")
    for c in rule.dates:
        bad = pd.to_datetime(df[c], errors="coerce").isna() & df[c].notna()
        if bad.any():
            out.append(f"{name}: {int(bad.sum())} unparseable dates in '{c}' (e.g. {df.loc[bad, c].iloc[0]!r})")
    dup = df.duplicated(list(rule.keys))
    if dup.any():
        out.append(f"{name}: {int(dup.sum())} duplicated keys on {list(rule.keys)}")
    for c in rule.numeric:
        x = pd.to_numeric(df[c], errors="coerce")
        bad = x.isna() & df[c].notna()
        if bad.any():
            out.append(f"{name}: {int(bad.sum())} non-numeric values in '{c}' (e.g. {df.loc[bad, c].iloc[0]!r})")
        if x.notna().sum() == 0:
            out.append(f"{name}: '{c}' has no values")
    for c, (lo, hi) in rule.ranges.items():
        x = pd.to_numeric(df[c], errors="coerce").dropna()
        off = x[(x < lo) | (x > hi)]
        if len(off):
            out.append(f"{name}: {len(off)} values of '{c}' outside [{lo:g}, {hi:g}] (e.g. {off.iloc[0]:g})")
    return out


def validate(raw: Path) -> list[str]:
    """Problems in every cached CSV under ``raw`` that a rule covers (legacy top-level files
    only need to be non-empty)."""
    problems = []
    for path in sorted(raw.rglob("*.csv")):
        rel = path.relative_to(raw).as_posix()
        if "/" not in rel:
            if path.stat().st_size == 0:
                problems.append(f"{path.as_posix()}: empty file")
            continue
        rule = rule_for(rel)
        if rule is not None:
            problems += check_file(path, rule)
    return problems
