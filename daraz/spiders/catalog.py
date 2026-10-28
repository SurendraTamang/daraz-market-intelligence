import collections
import datetime
import json
import os
import re

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.exceptions import CloseSpider
from scrapy.spidermiddlewares.httperror import HttpError

from daraz import db
from daraz.config import CATEGORY_SLUGS, MAX_PAGES
from daraz.crawl import (
    hole_targets,
    is_error_page,
    block_rate_exceeded,
    is_block_redirect,
    is_stale,
    parse_listing,
    resume_targets,
    should_follow,
    sold_items,
)
from daraz.utils import to_int

RAW_DIR = "raw"
RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RUN_ID_HINT = "RUN_ID must be a real YYYY-MM-DD date, e.g. RUN_ID=$(cat .run_id) scrapy crawl catalog"


class CatalogSpider(scrapy.Spider):
    name = "catalog"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # One RUN_ID = one snapshot, kept across stop/restart. Use the start date -- the
        # velocity view in db.py parses days out of this, so it must be a real calendar date.
        run_id = os.environ.get("RUN_ID")
        if not run_id or not RUN_ID_RE.match(run_id):
            raise ValueError(RUN_ID_HINT)
        try:
            datetime.date.fromisoformat(run_id)
        except ValueError:
            raise ValueError(RUN_ID_HINT) from None
        self.run_id = run_id
        self.recent = collections.deque(maxlen=100)  # True = blocked/error, for the auto-stop
        self.stopping = False  # guards CloseSpider from being raised more than once
        # slug -> every nid already accepted for that category in this run (preloaded from the DB
        # in start(), so it survives restarts). Daraz sometimes re-serves an OLDER page (not just
        # the previous one) under a new page number; comparing against all seen nids catches it.
        self.seen = collections.defaultdict(set)
        self.stale_streak = collections.Counter()  # consecutive final-stale pages per category

    async def start(self):
        con = db.connect()
        log = con.execute(
            "SELECT category, page, status, items, sold_items, no_more_pages, total_results "
            "FROM crawl_log WHERE run_id = ?", (self.run_id,),
        ).fetchall()
        for cat, nid in con.execute(
                "SELECT category, nid FROM products WHERE scraped_at = ? "
                "AND json_extract(raw_json, '$._page') IS NOT NULL", (self.run_id,)):
            # Only page-tagged rows: untagged rows predate tagging and may be deep pages being
            # re-fetched now; preloading them would flag the real page as stale.
            self.seen[cat].add(nid)
        con.close()
        targets = resume_targets(CATEGORY_SLUGS, log, MAX_PAGES)
        holes = hole_targets(log)
        self.logger.info("run %s: %d pages logged, %d to request", self.run_id, len(log), len(targets))
        # Resuming deep: re-fetch page 1 first (Daraz needs its session cookie to paginate),
        # then request the resume page (which follows on) and any holes (which don't).
        resume = dict(targets)
        for slug in [s for s in CATEGORY_SLUGS if s in resume or s in holes]:
            page = resume.get(slug)
            if page == 1 and slug not in holes:
                yield self.page_request(slug, 1)
                continue
            then = [(p, False) for p in holes.get(slug, [])] + ([(page, True)] if page else [])
            yield self.page_request(slug, 1, follow=page == 1, then=then)

    def page_request(self, slug, page, follow=True, then=None):
        url = f"https://www.daraz.com.np/{slug}/?ajax=true&page={page}"
        # No redirect-following: a 30x to a captcha page must reach parse() as "blocked", and
        # its retry must re-request the listing URL, not the captcha URL. 308 added alongside
        # the other permanent/temporary redirect codes Daraz could plausibly use.
        return scrapy.Request(url, callback=self.parse, errback=self.on_error,
                              cb_kwargs={"slug": slug, "page": page, "follow": follow,
                                         **({"then": then} if then else {})},
                              meta={"cookiejar": slug, "dont_redirect": True,
                                    "handle_httpstatus_list": [301, 302, 303, 307, 308]})

    def parse(self, response, slug, page, follow=True, then=()):
        if 300 <= response.status < 400:
            location = response.headers.get("Location")
            location = location.decode("utf-8", "replace") if location else None
            if is_block_redirect(location):
                yield from self._blocked(response, slug, page)
            else:
                # A dead/renamed category (e.g. Daraz redirecting to a sibling slug or a
                # generic "not found" page) -- NOT a block. Leave it alone (resume_targets
                # treats "moved" as terminal), don't count it toward the block-rate.
                yield self.log_row(slug, page, "moved")
            return

        text = getattr(response, "text", None)
        if text is None:  # non-text body (shouldn't happen for this JSON API, but be safe)
            text = response.body.decode("utf-8", "replace")
        data = parse_listing(text)
        if data is None:
            if is_error_page(text):  # dead/landing-only slug: terminal, not a block
                yield self.log_row(slug, page, "not_found")
                return
            yield from self._blocked(response, slug, page)  # captcha / block page / non-JSON
            return
        self._record(False)
        # Archive the full page JSON for re-parsing without re-fetching. RAW_OFF=1 for big sweeps.
        if not os.getenv("RAW_OFF"):
            cat_dir = os.path.join(RAW_DIR, slug)
            os.makedirs(cat_dir, exist_ok=True)
            with open(os.path.join(cat_dir, f"page-{page}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

        info = data.get("mainInfo") or {}
        items = data["mods"].get("listItems") or []
        n_sold = sold_items(items)
        no_more = str(info.get("noMorePages")).lower() == "true"
        total = to_int(info.get("totalResults"))

        nids = {str(it.get("nid")) for it in items}
        if page > 1 and is_stale(self.seen.get(slug), nids):
            # Daraz served the previous page's content again under this page number. Retry
            # on a fresh proxy session first (TransportMiddleware rotates IP per attempt);
            # this is a lagged/stale response, not a block, so it must not feed block_rate.
            retry = get_retry_request(response.request, spider=self, reason="stale")
            if retry:
                yield retry
                return
            # Retries exhausted: log it and move on to the next page without yielding the
            # duplicate items (don't re-store what the previous page already stored).
            yield self.log_row(slug, page, "stale", total, len(items), n_sold, no_more)
            self.stale_streak[slug] += 1
            # Two stale pages in a row = Daraz is only repeating itself here; stop the category
            # rather than spend 4 attempts per page down to page 102.
            if follow and self.stale_streak[slug] < 2 and should_follow(page, n_sold, no_more, MAX_PAGES, total):
                yield self.page_request(slug, page + 1)
            return

        self.seen[slug] |= nids
        self.stale_streak[slug] = 0
        for it in items:
            it["category"] = slug
            it["_page"] = page  # kept in raw_json: lets analysis compare categories at equal depth
            yield it
        yield self.log_row(slug, page, "ok" if items else "empty", total, len(items), n_sold, no_more)
        for p, f in then:  # resume targets queued behind the page-1 cookie warm-up
            yield self.page_request(slug, p, follow=f)
        if follow and should_follow(page, n_sold, no_more, MAX_PAGES, total):
            yield self.page_request(slug, page + 1)

    def _blocked(self, response, slug, page):
        # Count only FINAL outcomes toward the auto-stop: a captcha usually clears on retry
        # (fresh proxy session = new IP), so per-attempt counting stops healthy crawls.
        retry = get_retry_request(response.request, spider=self, reason="blocked")
        if retry:
            yield retry
            return
        self._record(True)
        yield self.log_row(slug, page, "blocked")

    def on_error(self, failure):
        kw = failure.request.cb_kwargs
        if failure.check(HttpError) and failure.value.response.status in (404, 410):
            # Dead category, not a block -- don't count it toward the block-rate.
            yield self.log_row(kw["slug"], kw["page"], "not_found")
            return
        self._record(True)
        yield self.log_row(kw["slug"], kw["page"], "error")

    def _record(self, bad):
        self.recent.append(bad)
        if bad and not self.stopping and block_rate_exceeded(self.recent):
            self.stopping = True
            raise CloseSpider("blocked")

    def log_row(self, slug, page, status, total=None, items=0, n_sold=0, no_more=False):
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return {"_crawl_log": (self.run_id, slug, page, status, total, items, n_sold, int(no_more), now)}
