"""How requests reach Daraz. PROXY env selects: none | liveproxies | decodo | mrscraper.

decodo: datacenter pool, one exit IP per port (DECODO_PORT_BASE..+DECODO_PORTS-1);
DECODO_HOST/USER in .env, password in Keychain (service 'decodo-proxy').

liveproxies: HOST/PORT/USER from .env (not secret); password from macOS Keychain
(service 'liveproxies-proxy'), never written to disk. USER carries the access code
(e.g. LVxxxxxxxx-lv_in); each request appends a sticky-session suffix -1..-N, so
traffic rotates over N exit IPs instead of hammering one.
"""
import gzip
import http.client
import os
import random
import subprocess
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
MODES = ("none", "liveproxies", "decodo", "mrscraper")
SESSIONS = int(os.getenv("LIVEPROXIES_SESSIONS", "200"))  # distinct exit IPs to rotate over


def proxy_url(host, port, user, password):
    q = lambda s: urllib.parse.quote(str(s), safe="")  # noqa: E731
    return f"http://{q(user)}:{q(password)}@{host}:{port}"


def keychain_password(service="liveproxies-proxy"):
    return subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def liveproxies_url(password=None, session=None):
    """Proxy URL for one sticky session (random 1..SESSIONS unless given)."""
    required = ("LIVEPROXIES_HOST", "LIVEPROXIES_PORT", "LIVEPROXIES_USER")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(
            "Set LIVEPROXIES_HOST, LIVEPROXIES_PORT, LIVEPROXIES_USER in .env "
            f"(missing: {', '.join(missing)})"
        )
    user = f"{os.environ['LIVEPROXIES_USER']}-{session or random.randint(1, SESSIONS)}"
    return proxy_url(os.environ["LIVEPROXIES_HOST"], os.environ["LIVEPROXIES_PORT"],
                     user, password or keychain_password())


def decodo_url(password=None, session=None):
    """Proxy URL for one Decodo port (= one exit IP); session 1..N maps onto the port range."""
    missing = [n for n in ("DECODO_HOST", "DECODO_USER") if not os.environ.get(n)]
    if missing:
        raise ValueError(f"Set DECODO_HOST, DECODO_USER in .env (missing: {', '.join(missing)})")
    ports = int(os.getenv("DECODO_PORTS", "100"))
    port = int(os.getenv("DECODO_PORT_BASE", "10001")) + ((session or random.randint(1, ports)) - 1) % ports
    return proxy_url(os.environ["DECODO_HOST"], port, os.environ["DECODO_USER"],
                     password or keychain_password("decodo-proxy"))


def sticky_url(m, password=None, session=None):
    """Proxy URL for a sticky-IP mode (liveproxies | decodo)."""
    return (decodo_url if m == "decodo" else liveproxies_url)(password, session)


def mrscraper_url(target):
    country = os.getenv("MRSCRAPER_PROXY_COUNTRY", "np")
    return (f"https://api.mrscraper.com/?token={os.environ['MRSCRAPER_TOKEN']}"
            f"&geoCode={country}&proxyCountry={country}&html=false"
            f"&url={urllib.parse.quote(target, safe='')}")


def mode():
    m = os.environ.get("PROXY")
    if m not in MODES:
        raise ValueError(f"PROXY must be one of {MODES}, got {m!r}")
    return m


def fetch(url, timeout=90, attempts=3):
    """One GET outside Scrapy (used by audit.py spot-checks), same transport as the crawl.
    gzip keeps proxy bandwidth ~6x lower; residential exits drop connections, so retry
    (each attempt on a fresh liveproxies session)."""
    m = mode()
    headers = {"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip"}
    if m == "mrscraper":
        headers["x-api-token"] = os.environ["MRSCRAPER_TOKEN"]
        url = mrscraper_url(url)
    for attempt in range(attempts):
        handlers = []
        if m in ("liveproxies", "decodo"):
            p = sticky_url(m)
            handlers.append(urllib.request.ProxyHandler({"http": p, "https": p}))
        try:
            with urllib.request.build_opener(*handlers).open(
                    urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except (OSError, http.client.HTTPException):  # URLError is an OSError
            if attempt == attempts - 1:
                raise
