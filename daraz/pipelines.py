import json
import sqlite3
import time

from scrapy.exceptions import DropItem
from scrapy.utils.defer import deferred_from_coro

from daraz import db
from daraz.utils import parse_sold_count, to_float, to_int

PRODUCT_SQL = "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
LOG_SQL = "INSERT OR REPLACE INTO crawl_log VALUES (?,?,?,?,?,?,?,?,?)"


class SQLitePipeline:
    def open_spider(self, spider):
        self.run_id = spider.run_id  # scraped_at = RUN_ID -> one snapshot per run, even across restarts
        self.conn = db.connect()
        self.broken = False  # set once a product write fails for good -> stop logging pages

    def close_spider(self, spider):
        self.conn.commit()
        self.conn.close()

    def process_item(self, item, spider):
        if "_crawl_log" in item:
            if self.broken:
                # Don't record this page as done -- resume_targets must re-fetch it once the
                # DB is healthy again, since we don't know whether its products actually landed.
                return item
            self._write(LOG_SQL, item["_crawl_log"], spider)
            raise DropItem("crawl_log", log_level="DEBUG")

        nid = item.get("nid")
        if not nid:
            spider.logger.warning("dropping item with no nid: %r", item.get("name"))
            raise DropItem("no nid")

        price = to_float(item.get("price"))
        sold = parse_sold_count(item.get("itemSoldCntShow"))
        row = (
            nid, item.get("name"), price,
            to_float(item.get("originalPrice")), to_float(item.get("discount")),
            item.get("sellerId"), item.get("sellerName"), item.get("brandName"),
            item.get("category"), item.get("location"),
            to_float(item.get("ratingScore")), to_int(item.get("review")),
            sold, (price or 0) * sold, item.get("image"), self.run_id,
            json.dumps(item, ensure_ascii=False),  # full raw item, so no field is ever lost
        )
        ok = self._write(PRODUCT_SQL, row, spider)
        if not ok and not self.broken:
            self.broken = True
            spider.logger.error("product write failed for nid=%s; closing spider (db_error)", nid)
            engine = getattr(getattr(spider, "crawler", None), "engine", None)
            if engine is not None:
                deferred_from_coro(engine.close_spider_async(reason="db_error"))
        return item

    def _write(self, sql, row, spider):
        # Commit per row so an interrupted crawl keeps its rows. Retry transient locked/readonly
        # errors (usually a stray second writer -- run only ONE crawl per DB at a time). Returns
        # True on success, False once the row is given up on (never raised/hidden silently).
        for attempt in range(5):
            try:
                self.conn.execute(sql, row)
                self.conn.commit()
                return True
            except sqlite3.OperationalError as e:
                if "readonly" not in str(e) and "locked" not in str(e):
                    spider.logger.error("db write failed, dropping row: %s", e)
                    return False
                time.sleep(0.5 * (attempt + 1))
                try:
                    self.conn.close()
                except sqlite3.Error:
                    pass
                try:
                    self.conn = db.connect()
                except sqlite3.Error:
                    pass
        spider.logger.warning("dropping row after readonly retries: %s", row[:3])
        return False
