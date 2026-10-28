import os
import zlib

from daraz import transport


class TransportMiddleware:
    """Route requests per PROXY env (see daraz/transport.py)."""

    def __init__(self):
        self.mode = transport.mode()
        if self.mode in ("liveproxies", "decodo"):
            # read once, not per request; the URL build fails fast on missing env
            self.password = transport.keychain_password(f"{self.mode}-proxy")
            transport.sticky_url(self.mode, self.password)

    def process_request(self, request, spider):
        if self.mode in ("liveproxies", "decodo"):
            # Scrapy's HttpProxyMiddleware (priority 750) turns the URL creds into Proxy-Authorization.
            # One sticky exit IP per category (its pages share IP + cookie jar, which Daraz needs
            # to paginate); a retry moves to another IP. HttpProxyMiddleware sees a changed proxy
            # URL and rebuilds Proxy-Authorization.
            key = request.meta.get("cookiejar") or request.url
            session = (zlib.crc32(str(key).encode()) + 7919 * request.meta.get("retry_times", 0)) \
                % transport.SESSIONS + 1
            request.meta["proxy"] = transport.sticky_url(self.mode, self.password, session=session)
            return None
        if self.mode == "mrscraper" and not request.meta.get("mrscraper_wrapped"):
            request.meta["mrscraper_wrapped"] = True
            request.headers["x-api-token"] = os.environ["MRSCRAPER_TOKEN"]
            return request.replace(url=transport.mrscraper_url(request.url))
        return None
