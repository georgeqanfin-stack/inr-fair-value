"""HTTP downloads with retries, and a record of sources that fell back to their cache.

Public data APIs (World Bank, FRED, RBIH, Brookings) time out or return 5xx now and then.
``get`` retries those with exponential backoff before giving up. Slow-moving sources
(annual World Bank and EWN data) then fall back to their cached copy instead of failing
the whole monthly refresh; each fallback is recorded in ``FALLBACKS`` so the refresh can
report it as a warning.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

RETRIES = 4            # attempts after the first
BACKOFF = 5.0          # seconds; waits of about 5, 10, 20, 40
RETRY_STATUS = (429, 500, 502, 503, 504)

FALLBACKS: list[str] = []


def session(retries: int = RETRIES, backoff: float = BACKOFF) -> requests.Session:
    """A session that retries timeouts, connection errors and 429/5xx responses."""
    s = requests.Session()
    retry = Retry(total=retries, connect=retries, read=retries, status=retries, backoff_factor=backoff,
                  status_forcelist=RETRY_STATUS, allowed_methods=frozenset({"GET"}), raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


_SESSION: requests.Session | None = None


def get(url: str, **kwargs) -> requests.Response:
    """``requests.get`` with retries (shared session)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = session()
    return _SESSION.get(url, **kwargs)


def fallback(source: str, error: Exception) -> None:
    FALLBACKS.append(f"{source}: download failed after {RETRIES + 1} attempts ({error.__class__.__name__}); "
                     "the cached copy was used.")


def reset() -> None:
    FALLBACKS.clear()

