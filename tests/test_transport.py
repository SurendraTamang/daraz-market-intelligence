import pytest
import scrapy

from daraz import transport
from daraz.middlewares import TransportMiddleware
from daraz.transport import proxy_url


def test_proxy_url_escapes_credentials():
    assert (proxy_url("gw.example", 7383, "user-country-np", "p@ss:word")
            == "http://user-country-np:p%40ss%3Aword@gw.example:7383")


def test_mode_raises_when_proxy_unset(monkeypatch):
    monkeypatch.delenv("PROXY", raising=False)
    with pytest.raises(ValueError):
        transport.mode()


def test_mode_raises_when_proxy_bogus(monkeypatch):
    monkeypatch.setenv("PROXY", "bogus")
    with pytest.raises(ValueError):
        transport.mode()


def test_liveproxies_url_raises_when_host_empty(monkeypatch):
    monkeypatch.setenv("LIVEPROXIES_HOST", "")
    monkeypatch.setenv("LIVEPROXIES_PORT", "7383")
    monkeypatch.setenv("LIVEPROXIES_USER", "user")
    with pytest.raises(ValueError, match="LIVEPROXIES_HOST"):
        transport.liveproxies_url()


def test_liveproxies_url_builds_proxy(monkeypatch):
    monkeypatch.setenv("LIVEPROXIES_HOST", "gw")
    monkeypatch.setenv("LIVEPROXIES_PORT", "7383")
    monkeypatch.setenv("LIVEPROXIES_USER", "user")
    monkeypatch.setattr(transport, "keychain_password", lambda *a, **k: "p@ss")
    assert transport.liveproxies_url(session=7) == "http://user-7:p%40ss@gw:7383"
    monkeypatch.setattr(transport.random, "randint", lambda a, b: b)
    assert transport.liveproxies_url() == f"http://user-{transport.SESSIONS}:p%40ss@gw:7383"


def test_mrscraper_middleware_wraps_once(monkeypatch):
    monkeypatch.setenv("PROXY", "mrscraper")
    monkeypatch.setenv("MRSCRAPER_TOKEN", "tok")
    mw = TransportMiddleware()
    req = scrapy.Request("https://www.daraz.com.np/tea/?ajax=true&page=1")

    wrapped = mw.process_request(req, spider=None)

    assert wrapped.url.startswith("https://api.mrscraper.com/")
    import urllib.parse
    assert urllib.parse.quote(req.url, safe="") in wrapped.url

    again = mw.process_request(wrapped, spider=None)
    assert again is None


def test_liveproxies_middleware_sets_proxy_meta(monkeypatch):
    monkeypatch.setenv("PROXY", "liveproxies")
    monkeypatch.setenv("LIVEPROXIES_HOST", "gw")
    monkeypatch.setenv("LIVEPROXIES_PORT", "7383")
    monkeypatch.setenv("LIVEPROXIES_USER", "user")
    monkeypatch.setattr(transport, "keychain_password", lambda *a, **k: "p@ss")
    mw = TransportMiddleware()
    req = scrapy.Request("https://www.daraz.com.np/tea/?ajax=true&page=1")

    result = mw.process_request(req, spider=None)
    assert result is None
    assert req.meta["proxy"].startswith("http://user-")

    # Same category -> same sticky IP; a retry -> a different one.
    a = scrapy.Request(req.url, meta={"cookiejar": "tea"}); mw.process_request(a, spider=None)
    b = scrapy.Request(req.url.replace("page=1", "page=2"), meta={"cookiejar": "tea"}); mw.process_request(b, spider=None)
    c = scrapy.Request(req.url, meta={"cookiejar": "tea", "retry_times": 1}); mw.process_request(c, spider=None)
    assert a.meta["proxy"] == b.meta["proxy"] != c.meta["proxy"]


def test_decodo_url_maps_session_onto_port_range(monkeypatch):
    monkeypatch.setenv("DECODO_HOST", "dc.example")
    monkeypatch.setenv("DECODO_USER", "u")
    monkeypatch.setenv("DECODO_PORT_BASE", "10001")
    monkeypatch.setenv("DECODO_PORTS", "100")
    assert transport.decodo_url("p", session=1) == "http://u:p@dc.example:10001"
    assert transport.decodo_url("p", session=100) == "http://u:p@dc.example:10100"
    assert transport.decodo_url("p", session=101) == "http://u:p@dc.example:10001"
