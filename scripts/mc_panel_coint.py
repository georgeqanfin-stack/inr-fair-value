"""Monte Carlo size and power of the bootstrap panel cointegration tests (stats/panel_coint.py).

Simulates panels shaped like the real one (19 countries, 32 years, a common random-walk
factor so countries are correlated) with and without cointegration, runs every test with
its bootstrap p-value, and prints the share of panels rejected at 5%. A correctly sized
test rejects about 5% of non-cointegrated panels.

Result (40 panels each, 99 bootstrap draws; 1 Oct 2026):
    no cointegration: group ADF 5.0%, panel ADF 7.5%, Westerlund Gt 17.5%, Pt 15.0%
    cointegrated:     group ADF 97.5%, panel ADF 97.5%, Gt 100%, Pt 100%
so the group ADF is the primary statistic; the Westerlund bootstrap over-rejects here.

Run:  python scripts/mc_panel_coint.py [replications]   (about 2.5 minutes for 40)
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from inrfv.stats import panel_coint as pc


def simulate(rng, coint: bool, n: int = 19, T: int = 32, rho: float = 0.5) -> pd.DataFrame:
    rows = []
    common = np.cumsum(rng.normal(0, 0.05, T))
    for i in range(n):
        x = np.cumsum(rng.normal(0.02, 0.03, T))
        if coint:
            u = np.zeros(T)
            for t in range(1, T):
                u[t] = rho * u[t - 1] + rng.normal(0, 0.05)
            y = 0.3 * x + u + 0.3 * common
        else:
            y = np.cumsum(rng.normal(0, 0.05, T)) + 0.3 * common
        rows += [{"country": f"C{i}", "year": 1994 + t, "log_reer": y[t], "rel_prod": x[t]} for t in range(T)]
    return pd.DataFrame(rows).set_index(["country", "year"])


def main(reps: int = 40, boot: int = 99) -> None:
    for coint in (False, True):
        rej = {k: 0 for k in ("group_adf", "panel_adf", "Gt", "Pt")}
        for r in range(reps):
            out = pc.test(simulate(np.random.default_rng(100 + r), coint), ["rel_prod"], boot, r)
            for k in rej:
                rej[k] += out["p"][k] < 0.05
        label = "cointegrated" if coint else "no cointegration"
        print(f"{label:17s}", "  ".join(f"{k} {v / reps:.1%}" for k, v in rej.items()))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
