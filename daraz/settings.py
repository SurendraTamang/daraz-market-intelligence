BOT_NAME = "daraz"
SPIDER_MODULES = ["daraz.spiders"]
NEWSPIDER_MODULE = "daraz.spiders"

# Daraz robots.txt disallows /catalog/; personal research only (see README ToS note).
ROBOTSTXT_OBEY = False

# Low concurrency: every request costs proxy quota and raises block risk. Tune after the rate test.
CONCURRENT_REQUESTS = 4
DOWNLOAD_DELAY = 1
AUTOTHROTTLE_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429, 403]
DOWNLOAD_TIMEOUT = 120

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
DEFAULT_REQUEST_HEADERS = {"Accept": "application/json, text/plain, */*", "Accept-Language": "en"}

# Cookies ON, one jar per category (spider sets meta["cookiejar"] = slug): Daraz only honours
# ?page=N>1 for a session that already fetched page 1 -- without the cookie it re-serves page 1.
COOKIES_ENABLED = True

DOWNLOADER_MIDDLEWARES = {"daraz.middlewares.TransportMiddleware": 543}
ITEM_PIPELINES = {"daraz.pipelines.SQLitePipeline": 300}

LOG_LEVEL = "INFO"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
