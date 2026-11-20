"""Latest USD/INR rate for the live monitor (shown on the site only; never enters the model).

The model runs on monthly averages, so its spot is last month's average. The site also
shows the latest daily rate against the (slow-moving) fair value, as an indicative
reading. Sources, tried in order; all free and keyless:

1. Frankfurter (api.frankfurter.app): the ECB's euro reference rates, crossed to USD/INR;
   published each TARGET business day around 16:00 CET.
2. The ECB's own data API, same rates, crossed here.
3. FRED DEXINUS: the Federal Reserve's noon New York buying rate (lags about a week).

A rate is accepted only if it is within ``MAX_JUMP`` of the model's last monthly average,
so a bad print never reaches the page.
"""

from __future__ import annotations

import io
from datetime import date

import requests

from . import net

MAX_JUMP = 0.10
FRANKFURTER = "https://api.frankfurter.app/latest?from=USD&to=INR"
ECB = "https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A?lastNObservations=1&format=csvdata"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXINUS"


def _frankfurter(s: requests.Session) -> tuple[float, str]:
    j = s.get(FRANKFURTER, timeout=30).json()
    return float(j["rates"]["INR"]), str(j["date"])


def _ecb_obs(s: requests.Session, cur: str) -> tuple[float, str]:
    import csv
    rows = list(csv.DictReader(io.StringIO(s.get(ECB.format(cur=cur), timeout=30).text)))
    return float(rows[-1]["OBS_VALUE"]), rows[-1]["TIME_PERIOD"]


def _ecb(s: requests.Session) -> tuple[float, str]:
    inr, d1 = _ecb_obs(s, "INR")
    usd, d2 = _ecb_obs(s, "USD")
    if d1 != d2:
        raise ValueError(f"ECB dates differ ({d1}, {d2})")
    return inr / usd, d1


def _fred(s: requests.Session) -> tuple[float, str]:
    last = [ln.split(",") for ln in s.get(FRED, timeout=60).text.strip().splitlines()[1:] if not ln.endswith(",.")]
    return float(last[-1][1]), last[-1][0]


SOURCES = [("ECB reference rate (Frankfurter)", _frankfurter), ("ECB reference rate", _ecb),
           ("Federal Reserve H.10 (FRED)", _fred)]


def fetch(reference: float | None = None, session: requests.Session | None = None) -> dict | None:
    """``{"rate", "date", "source"}`` from the first source that answers sensibly, else None."""
    s = session or net.session(retries=2, backoff=2)
    for name, fn in SOURCES:
        try:
            rate, day = fn(s)
            date.fromisoformat(day)
        except Exception:                      # any failure: try the next source
            continue
        if not 10 < rate < 500 or (reference and abs(rate / reference - 1) > MAX_JUMP):
            continue
        return {"rate": round(rate, 4), "date": day, "source": name}
    return None
