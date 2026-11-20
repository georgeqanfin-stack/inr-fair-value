import pandas as pd
import pytest
import requests

from inrfv.data import net, worldbank


def _timeout(*a, **k):
    raise requests.exceptions.ReadTimeout("read timed out")


def test_world_bank_timeout_falls_back_to_the_cache(tmp_path, monkeypatch):
    cache = tmp_path / "wb_x.csv"
    pd.DataFrame({"value": [1.0, 2.0]}, index=pd.Index(["2023-01-01", "2024-01-01"], name="date")).to_csv(cache)
    monkeypatch.setattr(net, "get", _timeout)
    net.reset()
    s = worldbank.fetch_annual("IND", "NY.GDP.MKTP.CD", cache, refresh=True)
    assert list(s.index) == [2023, 2024] and len(net.FALLBACKS) == 1 and "cached copy" in net.FALLBACKS[0]


def test_world_bank_panel_timeout_falls_back_and_no_cache_still_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(net, "get", _timeout)
    net.reset()
    cache = tmp_path / "p.csv"
    pd.DataFrame({"country": ["IND"], "year": [2024], "value": [1.0]}).to_csv(cache, index=False)
    assert len(worldbank.fetch_panel(["IND"], "X", cache, refresh=True)) == 1 and len(net.FALLBACKS) == 1
    with pytest.raises(requests.RequestException):
        worldbank.fetch_annual("IND", "X", tmp_path / "missing.csv", refresh=True)


def test_session_retries_timeouts_and_server_errors():
    retry = net.session().get_adapter("https://api.worldbank.org").max_retries
    assert retry.total == net.RETRIES and retry.read == net.RETRIES and 503 in retry.status_forcelist
